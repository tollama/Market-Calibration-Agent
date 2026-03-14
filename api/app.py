"""Read-only FastAPI application for derived artifacts."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any, Deque, Mapping, Optional

import hmac
import os
import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

_PLACEHOLDER_TOKENS = {
    "changemeplease",
    "your-token",
    "demo-token",
    "dev-token",
    "tsfm-dev-token",
    "example",
    "changeme",
    "placeholder",
}


def _is_placeholder_token(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    if not normalized:
        return True
    return normalized in _PLACEHOLDER_TOKENS


from fastapi.responses import PlainTextResponse

from .dependencies import LocalDerivedStore, get_derived_store
from calibration.explainability import (
    build_market_trust_explanation,
    build_trust_explanation,
)
from .schemas import (
    AlertItem,
    AlertsResponse,
    CalibrationQualityResponse,
    MarketComparisonRequest,
    MarketComparisonResponse,
    MarketDetailResponse,
    MarketMetricsResponse,
    MarketsResponse,
    PostmortemResponse,
    ScoreboardItem,
    ScoreboardResponse,
    _validate_scoreboard_window,
    TSFMForecastRequest,
    TSFMForecastResponse,
)
from .xai_schemas import (
    TrustExplanationRequest,
    TrustExplanationResponse,
    TrustIntelligenceResponse,
    SHAPFeatureItem,
    ConstraintViolationItem,
)
from runners.tsfm_service import TSFMRunnerService, TSFMServiceInputError


class _TSFMInboundGuard:
    def __init__(
        self,
        *,
        require_auth: bool = True,
        token_env_var: str = "TSFM_FORECAST_API_TOKEN",
        rate_limit_per_minute: int = 6,
    ) -> None:
        self.require_auth = require_auth
        self.token_env_var = token_env_var
        self.rate_limit_per_minute = rate_limit_per_minute
        self._calls: dict[str, Deque[float]] = defaultdict(deque)

    @classmethod
    def from_default_config(cls, *, path: str | Path = "configs/default.yaml") -> "_TSFMInboundGuard":
        cfg_path = Path(path)
        if not cfg_path.exists():
            return cls()
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        tsfm_cfg = ((raw.get("api") or {}).get("tsfm_forecast") or {})
        return cls(
            require_auth=bool(tsfm_cfg.get("require_auth", True)),
            token_env_var=str(tsfm_cfg.get("token_env_var", "TSFM_FORECAST_API_TOKEN")),
            rate_limit_per_minute=int(tsfm_cfg.get("rate_limit_per_minute", 6)),
        )

    def _extract_presented_token(self, request: Request) -> str | None:
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip()
        x_api_key = request.headers.get("X-API-Key")
        if x_api_key:
            return x_api_key.strip()
        return None

    def _identity(self, request: Request, presented_token: str | None) -> str:
        if presented_token:
            return f"token:{presented_token}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    def enforce(self, request: Request) -> None:
        presented_token = self._extract_presented_token(request)
        expected_token = os.getenv(self.token_env_var)

        if self.require_auth:
            if not expected_token or _is_placeholder_token(expected_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized",
                )
            if not presented_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized",
                )
            if not hmac.compare_digest(presented_token.encode(), expected_token.encode()):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized",
                )

        rpm = int(self.rate_limit_per_minute)
        if rpm > 0:
            now = datetime.now(timezone.utc).timestamp()
            identity = self._identity(request, presented_token)
            window = self._calls[identity]
            threshold = now - 60.0
            while window and window[0] < threshold:
                window.popleft()

            if len(window) >= rpm:
                retry_after = max(1, ceil((window[0] + 60.0) - now)) if window else 60
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for /tsfm/forecast",
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)


app = FastAPI(title="Market Calibration Read-Only API", version="0.1.0")
try:
    _tsfm_service = TSFMRunnerService.from_runtime_config()
except FileNotFoundError:
    _tsfm_service = TSFMRunnerService()
_tsfm_guard = _TSFMInboundGuard.from_default_config()


def _is_calibrated_market_id(market_id: str) -> bool:
    return str(market_id or "").strip().lower().startswith("mkt-")


def _build_postmortem_fallback(*, market_id: str) -> PostmortemResponse:
    now = datetime.now(timezone.utc)
    title = f"Postmortem {market_id}"
    summary = "No explicit postmortem artifact was found; returning calibrated fallback for demo continuity."
    reasons = [
        "POSTMORTEM_MISSING",
        "CALIBRATED_MARKET_FALLBACK",
    ]
    content = "\n".join(
        [
            f"# {title}",
            "",
            f"- source: fallback",
            f"- generated_at: {now.isoformat()}",
            "",
            "## Summary",
            summary,
            "",
            "## Reason Codes",
            *(f"- {reason}" for reason in reasons),
            "",
        ]
    )
    return PostmortemResponse(
        market_id=market_id,
        content=content,
        source_path="fallback://postmortem-missing",
        source="fallback",
        title=title,
        summary=summary,
        reasons=reasons,
        generated_at=now,
    )


def _select_latest_postmortem_path(
    *,
    store: LocalDerivedStore,
    market_id: str,
) -> Optional[Path]:
    prefix = f"{market_id}_"
    latest_path: Optional[Path] = None
    latest_key: Optional[tuple[int, date, str]] = None

    for path in store.postmortem_dir.glob("*.md"):
        if not path.is_file():
            continue
        if not path.name.startswith(prefix):
            continue

        resolved_date_token = path.stem[len(prefix) :]
        try:
            resolved_date = date.fromisoformat(resolved_date_token)
            candidate_key = (1, resolved_date, resolved_date_token)
        except ValueError:
            candidate_key = (0, date.min, resolved_date_token)

        if latest_key is None or candidate_key > latest_key:
            latest_key = candidate_key
            latest_path = path

    return latest_path


@app.get("/scoreboard", response_model=ScoreboardResponse)
def get_scoreboard(
    window: str = Query(default="90d"),
    tag: Optional[str] = Query(default=None),
    liquidity_bucket: Optional[str] = Query(default=None),
    min_trust_score: Optional[float] = Query(default=None),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> ScoreboardResponse:
    try:
        window = _validate_scoreboard_window(window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    records = store.load_scoreboard(window=window)

    if tag:
        records = [record for record in records if record.get("category") == tag]
    if liquidity_bucket:
        records = [
            record
            for record in records
            if record.get("liquidity_bucket") == liquidity_bucket
        ]
    if min_trust_score is not None:
        records = [
            record
            for record in records
            if isinstance(record.get("trust_score"), (int, float))
            and float(record["trust_score"]) >= min_trust_score
        ]

    items = [ScoreboardItem(**record) for record in records]
    return ScoreboardResponse(items=items, total=len(items))


@app.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    severity: Optional[str] = Query(default=None),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> AlertsResponse:
    if severity is None:
        records, total = store.load_alerts(since=since, limit=limit, offset=offset)
    else:
        normalized_severity = severity.upper()
        allowed_severities = {"HIGH", "MED", "FYI"}
        if normalized_severity not in allowed_severities:
            raise HTTPException(
                status_code=422,
                detail="Invalid severity. Expected one of: HIGH, MED, FYI.",
            )

        all_records, _ = store.load_alerts(since=since, limit=10**9, offset=0)
        filtered = [
            record
            for record in all_records
            if str(record.get("severity", "")).upper() == normalized_severity
        ]
        total = len(filtered)
        records = filtered[offset : offset + limit]

    items = [AlertItem(**record) for record in records]
    return AlertsResponse(items=items, total=total, limit=limit, offset=offset)


@app.post("/trust/explain", response_model=TrustExplanationResponse)
def explain_trust(payload: TrustExplanationRequest) -> TrustExplanationResponse:
    return TrustExplanationResponse(
        **build_trust_explanation(payload.model_dump(mode="python", exclude_none=True))
    )


@app.get("/markets/{market_id}/trust-explanation", response_model=TrustExplanationResponse)
def get_market_trust_explanation(
    market_id: str,
    store: LocalDerivedStore = Depends(get_derived_store),
) -> TrustExplanationResponse:
    market = store.load_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")
    metrics = store.load_market_metrics(market_id)
    explanation = build_market_trust_explanation(market=market, metrics=metrics)
    return TrustExplanationResponse(**explanation)


@app.get(
    "/trust-intelligence/{market_id}",
    response_model=TrustIntelligenceResponse,
)
def get_trust_intelligence(
    market_id: str,
    store: LocalDerivedStore = Depends(get_derived_store),
) -> TrustIntelligenceResponse:
    """Return Trust Intelligence Pipeline v3.0 output for a market.

    Falls back to running the pipeline on-demand if persisted results
    are not available but the trust_intelligence package is installed.
    """
    # Try loading persisted result first
    persisted = store.load_trust_intelligence(market_id)
    if persisted is not None:
        return _build_ti_response(market_id, persisted)

    # Fall back to on-demand computation
    try:
        from calibration.trust_intelligence_adapter import (
            HAS_TRUST_INTELLIGENCE,
            run_trust_intelligence_for_market,
        )
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="trust_intelligence package not installed",
        )

    if not HAS_TRUST_INTELLIGENCE:
        raise HTTPException(
            status_code=501,
            detail="trust_intelligence package not installed",
        )

    market = store.load_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")

    # Build a minimal row from scoreboard data
    scoreboard = store.load_scoreboard(window="90d")
    market_row = next(
        (r for r in scoreboard if str(r.get("market_id", "")) == market_id),
        None,
    )
    if market_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No scoreboard data for market: {market_id}",
        )

    from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

    pipeline = TrustIntelligencePipeline()
    ti_result = run_trust_intelligence_for_market(
        pipeline,
        market_rows=[market_row],
        v1_trust_score=market_row.get("trust_score"),
    )
    if ti_result is None:
        raise HTTPException(
            status_code=500,
            detail="Trust Intelligence Pipeline execution failed",
        )

    result_dict = ti_result.model_dump() if hasattr(ti_result, "model_dump") else {}
    result_dict["market_id"] = market_id
    result_dict["trust_score_v1"] = market_row.get("trust_score")
    return _build_ti_response(market_id, result_dict)


def _build_ti_response(
    market_id: str,
    data: Mapping[str, Any],
) -> TrustIntelligenceResponse:
    """Build TrustIntelligenceResponse from pipeline result dict."""
    uncertainty = data.get("uncertainty") or {}
    conformal = data.get("conformal") or {}
    shap = data.get("shap") or {}
    constraints = data.get("constraints") or {}
    trust = data.get("trust") or {}

    top_features = []
    for fc in (shap.get("feature_contributions") or [])[:5]:
        if isinstance(fc, Mapping):
            top_features.append(SHAPFeatureItem(
                feature_name=str(fc.get("feature_name", "")),
                shap_value=float(fc.get("shap_value", 0)),
                rank=int(fc.get("rank", 0)),
                direction=str(fc.get("direction", "positive")),
            ))

    violations = []
    for v in constraints.get("violations") or []:
        if isinstance(v, Mapping):
            violations.append(ConstraintViolationItem(
                constraint_name=str(v.get("constraint_name", "")),
                constraint_type=str(v.get("constraint_type", "")),
                expected=str(v.get("expected", "")),
                actual=str(v.get("actual", "")),
                severity=str(v.get("severity", "")),
            ))

    risk_cat = constraints.get("risk_category", "GREEN")
    if isinstance(risk_cat, Mapping):
        risk_cat = "GREEN"
    risk_cat_str = str(risk_cat)

    return TrustIntelligenceResponse(
        market_id=market_id,
        trust_score=float(trust.get("trust_score", 0.5)),
        trust_score_v1=data.get("trust_score_v1"),
        entropy=float(uncertainty.get("entropy", 0)),
        normalized_uncertainty=float(uncertainty.get("normalized_uncertainty", 0.5)),
        prediction_probability=float(uncertainty.get("prediction_probability", 0.5)),
        conformal_method=str(conformal.get("method", "none")),
        conformal_p_low=float(conformal.get("p_low", 0)),
        conformal_p_high=float(conformal.get("p_high", 1)),
        coverage_validity=bool(conformal.get("coverage_validity", False)),
        coverage_tightness=float(conformal.get("coverage_tightness", 0.5)),
        shap_stability=float(shap.get("shap_stability", 0.5)),
        shap_iterations=int(shap.get("iterations_used", 0)),
        top_features=top_features,
        constraint_satisfied=bool(constraints.get("constraint_satisfied", True)),
        risk_category=risk_cat_str,
        violations=violations,
        constraints_checked=int(constraints.get("constraints_checked", 0)),
        weights=trust.get("weights") or {},
        component_scores=trust.get("component_scores") or {},
        calibration_status=str(trust.get("calibration_status", "well_calibrated")),
        ece=float(trust.get("ece", 0)),
        ocr=float(trust.get("ocr", 0)),
        chain_of_trust_entries=len(data.get("chain_of_trust") or []),
    )


@app.get("/markets", response_model=MarketsResponse)
def get_markets(store: LocalDerivedStore = Depends(get_derived_store)) -> MarketsResponse:
    items = store.load_markets()
    return MarketsResponse(items=items, total=len(items))


@app.get("/markets/{market_id}", response_model=MarketDetailResponse)
def get_market(market_id: str, store: LocalDerivedStore = Depends(get_derived_store)) -> MarketDetailResponse:
    market = store.load_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")
    return market


@app.get("/markets/{market_id}/metrics", response_model=MarketMetricsResponse)
def get_market_metrics(
    market_id: str,
    store: LocalDerivedStore = Depends(get_derived_store),
) -> MarketMetricsResponse:
    metrics = store.load_market_metrics(market_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")
    return metrics


def _warn(meta: dict[str, Any], code: str) -> None:
    warnings = meta.setdefault("warnings", [])
    if isinstance(warnings, list) and code not in warnings:
        warnings.append(code)


def _quantile_key(value: float) -> str:
    return str(value)


def _sanitize_forecast_payload(
    *,
    raw: Mapping[str, Any] | None,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    src: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}

    out: dict[str, Any] = {}
    meta_raw = src.get("meta")
    meta = dict(meta_raw) if isinstance(meta_raw, dict) else {}
    if meta_raw is not None and not isinstance(meta_raw, dict):
        _warn(meta, "COMPARE_SANITIZED_META_CONTAINER")

    fallback_fields = ["market_id", "as_of_ts", "freq", "horizon_steps", "quantiles"]
    for field in fallback_fields:
        value = src.get(field)
        if value is None:
            value = request_payload.get(field)
            _warn(meta, f"COMPARE_SANITIZED_MISSING_FIELD_{field.upper()}")
        out[field] = value

    quantiles = out.get("quantiles")
    if not isinstance(quantiles, list) or not quantiles:
        out["quantiles"] = request_payload.get("quantiles", [0.1, 0.5, 0.9])
        _warn(meta, "COMPARE_SANITIZED_QUANTILES")
    else:
        clean_quantiles: list[float] = []
        for item in quantiles:
            try:
                clean_quantiles.append(float(item))
            except (TypeError, ValueError):
                _warn(meta, "COMPARE_SANITIZED_QUANTILES")
        if not clean_quantiles:
            clean_quantiles = request_payload.get("quantiles", [0.1, 0.5, 0.9])
            _warn(meta, "COMPARE_SANITIZED_QUANTILES")
        out["quantiles"] = clean_quantiles

    yhat_q_raw = src.get("yhat_q")
    clean_yhat_q: dict[str, list[float]] = {}
    if not isinstance(yhat_q_raw, dict):
        _warn(meta, "COMPARE_SANITIZED_YHAT_Q_CONTAINER")
        yhat_q_raw = {}

    for q in out["quantiles"]:
        q_key = _quantile_key(float(q))
        series = yhat_q_raw.get(q_key)
        if not isinstance(series, list):
            if series is not None:
                _warn(meta, f"COMPARE_SANITIZED_QUANTILE_SERIES_{q_key}")
            clean_yhat_q[q_key] = []
            continue

        clean_series: list[float] = []
        saw_bad_value = False
        for item in series:
            try:
                clean_series.append(float(item))
            except (TypeError, ValueError):
                saw_bad_value = True
        if saw_bad_value:
            _warn(meta, f"COMPARE_SANITIZED_QUANTILE_VALUE_{q_key}")
        clean_yhat_q[q_key] = clean_series

    out["yhat_q"] = clean_yhat_q
    out["meta"] = meta

    conformal = src.get("conformal_last_step")
    out["conformal_last_step"] = conformal if isinstance(conformal, dict) else None
    if conformal is not None and not isinstance(conformal, dict):
        _warn(meta, "COMPARE_SANITIZED_CONFORMAL_LAST_STEP")

    return out


@app.post("/markets/{market_id}/comparison", response_model=MarketComparisonResponse)
def post_market_comparison(
    market_id: str,
    payload: MarketComparisonRequest,
) -> MarketComparisonResponse:
    if payload.forecast.market_id != market_id:
        raise HTTPException(status_code=400, detail="market_id in path/body mismatch")

    base_req = payload.forecast.model_dump(mode="json")
    tollama_raw = _tsfm_service.forecast(base_req)

    baseline_req = dict(base_req)
    baseline_req["liquidity_bucket"] = payload.baseline_liquidity_bucket
    baseline_raw = _tsfm_service.forecast(baseline_req)

    tollama = _sanitize_forecast_payload(raw=tollama_raw, request_payload=base_req)
    baseline = _sanitize_forecast_payload(raw=baseline_raw, request_payload=baseline_req)

    t50 = (tollama.get("yhat_q") or {}).get("0.5") or []
    b50 = (baseline.get("yhat_q") or {}).get("0.5") or []
    delta_last_q50 = None
    if t50 and b50 and isinstance(t50[-1], (int, float)) and isinstance(b50[-1], (int, float)):
        delta_last_q50 = float(t50[-1]) - float(b50[-1])

    return MarketComparisonResponse(
        market_id=market_id,
        baseline=TSFMForecastResponse(**baseline),
        tollama=TSFMForecastResponse(**tollama),
        delta_last_q50=delta_last_q50,
    )


@app.get("/postmortem/{market_id}", response_model=PostmortemResponse)
def get_postmortem(
    market_id: str,
    store: LocalDerivedStore = Depends(get_derived_store),
) -> PostmortemResponse:
    try:
        content, source_path = store.load_postmortem(market_id=market_id)
    except FileNotFoundError:
        latest_path = _select_latest_postmortem_path(store=store, market_id=market_id)
        if latest_path is None:
            if _is_calibrated_market_id(market_id):
                return _build_postmortem_fallback(market_id=market_id)
            raise HTTPException(
                status_code=404,
                detail=f"Postmortem not found: {market_id}",
            )
        content = latest_path.read_text(encoding="utf-8")
        source_path = latest_path

    return PostmortemResponse(
        market_id=market_id,
        content=content,
        source_path=str(source_path),
        source="artifact",
    )


@app.get("/metrics/calibration_quality", response_model=CalibrationQualityResponse)
def get_calibration_quality(
    window: str = Query(default="90d"),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> CalibrationQualityResponse:
    """Return aggregated calibration quality metrics for operational monitoring.

    Combines global calibration scores (Brier, log-loss, ECE), conformal
    coverage and width, drift detection status, and low-confidence market
    counts into a single response.
    """
    try:
        window = _validate_scoreboard_window(window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    records = store.load_scoreboard(window=window)
    now = datetime.now(timezone.utc)

    if not records:
        return CalibrationQualityResponse(
            total_market_count=0,
            low_confidence_market_count=0,
            as_of=now,
        )

    # Aggregate calibration metrics across all markets
    brier_values: list[float] = []
    log_loss_values: list[float] = []
    ece_values: list[float] = []
    low_confidence_count = 0
    total_count = len(records)

    for record in records:
        b = record.get("brier")
        if isinstance(b, (int, float)):
            brier_values.append(float(b))
        ll = record.get("log_loss") or record.get("logloss")
        if isinstance(ll, (int, float)):
            log_loss_values.append(float(ll))
        e = record.get("ece")
        if isinstance(e, (int, float)):
            ece_values.append(float(e))
        if record.get("low_confidence") is True:
            low_confidence_count += 1

    avg_brier = sum(brier_values) / len(brier_values) if brier_values else None
    avg_log_loss = sum(log_loss_values) / len(log_loss_values) if log_loss_values else None
    avg_ece = sum(ece_values) / len(ece_values) if ece_values else None

    # Attempt to load drift and conformal state from store (best-effort)
    drift_detected: bool | None = None
    base_rate_swing: float | None = None
    conformal_coverage: float | None = None
    conformal_width: float | None = None

    try:
        drift_state = store.load_drift_state() if hasattr(store, "load_drift_state") else None
        if isinstance(drift_state, Mapping):
            drift_detected = bool(drift_state.get("drift_detected"))
            swing = drift_state.get("base_rate_swing")
            if isinstance(swing, (int, float)):
                base_rate_swing = float(swing)
    except Exception:  # pragma: no cover - best effort
        pass

    try:
        conformal_state = store.load_conformal_state() if hasattr(store, "load_conformal_state") else None
        if isinstance(conformal_state, Mapping):
            cov = conformal_state.get("post_coverage") or conformal_state.get("coverage")
            if isinstance(cov, (int, float)):
                conformal_coverage = float(cov)
            width = conformal_state.get("width_scale") or conformal_state.get("width")
            if isinstance(width, (int, float)):
                conformal_width = float(width)
    except Exception:  # pragma: no cover - best effort
        pass

    return CalibrationQualityResponse(
        brier=avg_brier,
        log_loss=avg_log_loss,
        ece=avg_ece,
        conformal_coverage=conformal_coverage,
        conformal_width=conformal_width,
        drift_detected=drift_detected,
        base_rate_swing=base_rate_swing,
        low_confidence_market_count=low_confidence_count,
        total_market_count=total_count,
        as_of=now,
    )


@app.post("/tsfm/forecast", response_model=TSFMForecastResponse)
def post_tsfm_forecast(payload: TSFMForecastRequest, request: Request) -> TSFMForecastResponse:
    _tsfm_guard.enforce(request)
    try:
        result = _tsfm_service.forecast(payload.model_dump(mode="json"))
    except (TSFMServiceInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TSFMForecastResponse(**result)


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    return _tsfm_service.render_prometheus_metrics()


@app.get("/tsfm/metrics", response_class=PlainTextResponse)
def get_tsfm_metrics() -> str:
    return get_metrics()
