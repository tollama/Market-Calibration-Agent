"""Top-N alert orchestration for PRD1 I-15 + PRD2 selective inference.

This module keeps selection and decision outputs deterministic:
- stable market ranking with explicit tie-breaks
- conservative defaults for missing trust/gate inputs
- explicit per-market decision records (emit/suppress)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pipelines.build_alert_feed import build_alert_feed_rows

_TOP_N_DEFAULT = 50


def rank_top_n_markets(
    candidates: Sequence[Mapping[str, Any]],
    *,
    top_n: int = _TOP_N_DEFAULT,
    watchlist_market_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Rank candidate markets for TSFM/alert processing.

    Priority order:
    1) watchlist markets
    2) explicit alert candidates
    3) composite liquidity/importance score
    """

    normalized_top_n = max(int(top_n), 0)
    if normalized_top_n == 0:
        return []

    watchlist = {str(market_id).strip() for market_id in (watchlist_market_ids or []) if str(market_id).strip()}

    ranked_rows: list[tuple[tuple[int, int, float, str], dict[str, Any]]] = []
    for row in candidates:
        market_id = str(row.get("market_id", "")).strip()
        if not market_id:
            continue

        watch_rank = 0 if market_id in watchlist else 1
        alert_candidate_rank = 0 if _coerce_bool(row.get("is_alert_candidate"), default=False) else 1
        score = _importance_score(row)
        sort_key = (watch_rank, alert_candidate_rank, -score, market_id)
        ranked_rows.append((sort_key, dict(row)))

    ranked_rows.sort(key=lambda item: item[0])

    selected: list[dict[str, Any]] = []
    for rank_idx, (_, row) in enumerate(ranked_rows[:normalized_top_n], start=1):
        row["top_n_rank"] = rank_idx
        row["selected_top_n"] = True
        selected.append(row)
    return selected


def orchestrate_top_n_alert_decisions(
    candidates: Sequence[Mapping[str, Any]],
    *,
    tsfm_service: Any,
    top_n: int = _TOP_N_DEFAULT,
    watchlist_market_ids: Sequence[str] | None = None,
    include_fyi: bool = False,
    min_trust_score: float | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Produce explicit per-market alert decisions for selected top-N markets."""

    selected = rank_top_n_markets(
        candidates,
        top_n=top_n,
        watchlist_market_ids=watchlist_market_ids,
    )
    selected_ids = {str(row["market_id"]) for row in selected}

    decisions: list[dict[str, Any]] = []

    # First, non-selected markets => deterministic suppression decision
    for row in candidates:
        market_id = str(row.get("market_id", "")).strip()
        if not market_id or market_id in selected_ids:
            continue
        decisions.append(
            {
                "market_id": market_id,
                "selected_top_n": False,
                "decision": "SUPPRESS",
                "suppression_reason": "TOP_N_EXCLUDED",
            }
        )

    # Selected markets => forecast + gate decision
    for row in selected:
        market_id = str(row["market_id"])
        trust_score = _optional_float(row.get("trust_score"))
        if min_trust_score is not None:
            required = float(min_trust_score)
            # Conservative deterministic default: missing trust fails threshold.
            if trust_score is None or trust_score < required:
                decisions.append(
                    {
                        "market_id": market_id,
                        "selected_top_n": True,
                        "top_n_rank": row.get("top_n_rank"),
                        "decision": "SUPPRESS",
                        "suppression_reason": "TRUST_GATE",
                        "trust_score": trust_score,
                        "required_min_trust_score": required,
                    }
                )
                continue

        forecast_request = dict(_ensure_mapping(row.get("forecast_request")))
        forecast_request.setdefault("market_id", market_id)
        forecast_response = tsfm_service.forecast(forecast_request)
        yhat_q = _ensure_mapping(forecast_response.get("yhat_q"))

        q10_path = _ensure_sequence(yhat_q.get("0.1"))
        q50_path = _ensure_sequence(yhat_q.get("0.5"))
        q90_path = _ensure_sequence(yhat_q.get("0.9"))
        if not q10_path or not q90_path:
            decisions.append(
                {
                    "market_id": market_id,
                    "selected_top_n": True,
                    "top_n_rank": row.get("top_n_rank"),
                    "decision": "SUPPRESS",
                    "suppression_reason": "FORECAST_PAYLOAD_INVALID",
                    "forecast_meta": dict(_ensure_mapping(forecast_response.get("meta"))),
                }
            )
            continue

        p_yes = _optional_float(row.get("p_yes"))
        if p_yes is None:
            p_yes = float(q50_path[-1]) if q50_path else float(q10_path[-1])

        alert_row = {
            "market_id": market_id,
            "ts": row.get("ts") or forecast_response.get("as_of_ts"),
            "p_yes": p_yes,
            "q10": float(q10_path[-1]),
            "q90": float(q90_path[-1]),
            "open_interest_change_1h": row.get("open_interest_change_1h"),
            "ambiguity_score": row.get("ambiguity_score"),
            "volume_velocity": row.get("volume_velocity"),
            "trust_score": trust_score,
            "strict_gate_passed": row.get("strict_gate_passed"),
        }

        alerts = build_alert_feed_rows(
            [alert_row],
            thresholds=thresholds,
            include_fyi=include_fyi,
            min_trust_score=None,
        )
        forecast_meta = dict(_ensure_mapping(forecast_response.get("meta")))
        if alerts:
            alert = alerts[0]
            decisions.append(
                {
                    "market_id": market_id,
                    "selected_top_n": True,
                    "top_n_rank": row.get("top_n_rank"),
                    "decision": "EMIT",
                    "severity": alert.get("severity"),
                    "reason_codes": list(alert.get("reason_codes", [])),
                    "alert": alert,
                    "forecast_meta": forecast_meta,
                }
            )
        else:
            decisions.append(
                {
                    "market_id": market_id,
                    "selected_top_n": True,
                    "top_n_rank": row.get("top_n_rank"),
                    "decision": "SUPPRESS",
                    "suppression_reason": "ALERT_GATE",
                    "forecast_meta": forecast_meta,
                }
            )

    decisions.sort(key=lambda row: (0 if row.get("selected_top_n") else 1, int(row.get("top_n_rank") or 10**9), str(row.get("market_id", ""))))
    return decisions


def _importance_score(row: Mapping[str, Any]) -> float:
    volume_24h = _optional_float(row.get("volume_24h")) or 0.0
    open_interest = _optional_float(row.get("open_interest")) or 0.0
    trust_score = _optional_float(row.get("trust_score")) or 0.0
    return volume_24h * 0.5 + open_interest * 0.3 + trust_score * 0.2


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _ensure_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []
