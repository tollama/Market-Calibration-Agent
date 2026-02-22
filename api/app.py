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
from fastapi.responses import PlainTextResponse

from .dependencies import LocalDerivedStore, get_derived_store
from .schemas import (
    AlertItem,
    AlertsResponse,
    MarketComparisonRequest,
    MarketComparisonResponse,
    MarketDetailResponse,
    MarketMetricsResponse,
    MarketsResponse,
    PostmortemResponse,
    ScoreboardItem,
    ScoreboardResponse,
    TSFMForecastRequest,
    TSFMForecastResponse,
)
from runners.tsfm_service import TSFMRunnerService


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
            if not expected_token:
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


@app.post("/tsfm/forecast", response_model=TSFMForecastResponse)
def post_tsfm_forecast(payload: TSFMForecastRequest, request: Request) -> TSFMForecastResponse:
    _tsfm_guard.enforce(request)
    result = _tsfm_service.forecast(payload.model_dump(mode="json"))
    return TSFMForecastResponse(**result)


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    return _tsfm_service.render_prometheus_metrics()


@app.get("/tsfm/metrics", response_class=PlainTextResponse)
def get_tsfm_metrics() -> str:
    return get_metrics()
