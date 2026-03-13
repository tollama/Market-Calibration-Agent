"""Trust-score explanation helpers for v3.8 evidence packaging."""

from __future__ import annotations

from typing import Any, Mapping

from calibration.trust_score import compute_trust_score


_DEFAULT_WEIGHTS: dict[str, float] = {
    "liquidity_depth": 0.35,
    "stability": 0.25,
    "question_quality": 0.25,
    "manipulation_suspect": 0.15,
}


def build_trust_explanation(payload: Mapping[str, Any]) -> dict[str, Any]:
    market_id = str(payload.get("market_id") or "").strip()
    raw_components = payload.get("components") if isinstance(payload.get("components"), Mapping) else {}
    components = {
        "liquidity_depth": _clip_unit(raw_components.get("liquidity_depth")),
        "stability": _clip_unit(raw_components.get("stability")),
        "question_quality": _clip_unit(raw_components.get("question_quality")),
        "manipulation_suspect": _clip_unit(raw_components.get("manipulation_suspect")),
    }
    weights = _normalize_weights(payload.get("weights") if isinstance(payload.get("weights"), Mapping) else None)
    trust_score = float(payload.get("trust_score")) if payload.get("trust_score") is not None else float(compute_trust_score(components, weights))

    component_breakdown = []
    for name in ("liquidity_depth", "stability", "question_quality", "manipulation_suspect"):
        raw_value = float(components[name])
        effective_value = 1.0 - raw_value if name == "manipulation_suspect" else raw_value
        weighted_contribution = 100.0 * float(weights[name]) * effective_value
        component_breakdown.append(
            {
                "name": name,
                "raw_value": round(raw_value, 4),
                "effective_value": round(effective_value, 4),
                "weight": round(float(weights[name]), 4),
                "weighted_contribution": round(weighted_contribution, 4),
                "direction": "negative" if name == "manipulation_suspect" else "positive",
                "explanation": _component_explanation(name=name, raw_value=raw_value, effective_value=effective_value),
            }
        )

    calibration_metrics = dict(payload.get("calibration_metrics") or {})
    drift_report = dict(payload.get("drift_report") or {})
    reason_codes = [str(item) for item in drift_report.get("reason_codes", []) if str(item)]

    narrative = [
        f"trust_score={trust_score:.2f} for market {market_id or '(unknown)'}",
        _metric_sentence(calibration_metrics),
    ]
    if reason_codes:
        narrative.append("drift monitor flagged: " + ", ".join(reason_codes))

    return {
        "market_id": market_id,
        "mode": "deterministic",
        "trust_score": round(trust_score, 4),
        "summary": _trust_summary(trust_score),
        "confidence_level": _trust_level(trust_score),
        "component_breakdown": component_breakdown,
        "calibration_evidence": calibration_metrics,
        "drift_evidence": drift_report,
        "reason_codes": reason_codes,
        "narrative": [item for item in narrative if item],
    }


def build_market_trust_explanation(
    *,
    market: Mapping[str, Any] | None,
    metrics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if market is None:
        raise ValueError("market is required")
    market_id = str(market.get("market_id") or "")
    trust_score = market.get("trust_score")
    latest_alert = market.get("latest_alert") if isinstance(market.get("latest_alert"), Mapping) else {}
    scoreboard_by_window = metrics.get("scoreboard_by_window") if isinstance(metrics, Mapping) else []
    alert_counts = metrics.get("alert_severity_counts") if isinstance(metrics, Mapping) else {}

    narrative: list[str] = []
    if trust_score is not None:
        narrative.append(f"current trust score is {float(trust_score):.2f}")
    if isinstance(scoreboard_by_window, list) and scoreboard_by_window:
        snapshots = []
        for item in scoreboard_by_window[:3]:
            if not isinstance(item, Mapping):
                continue
            window = item.get("window")
            score = item.get("trust_score")
            if window is not None and score is not None:
                snapshots.append(f"{window}={float(score):.2f}")
        if snapshots:
            narrative.append("scoreboard snapshots: " + ", ".join(snapshots))
    if isinstance(latest_alert, Mapping) and latest_alert:
        severity = latest_alert.get("severity")
        reason_codes = latest_alert.get("reason_codes") if isinstance(latest_alert.get("reason_codes"), list) else []
        if severity:
            narrative.append(f"latest alert severity={severity}")
        if reason_codes:
            narrative.append("latest alert reasons: " + ", ".join(str(item) for item in reason_codes[:5]))

    return {
        "market_id": market_id,
        "mode": "best_effort",
        "trust_score": float(trust_score) if trust_score is not None else None,
        "summary": _trust_summary(float(trust_score)) if trust_score is not None else "trust score unavailable",
        "confidence_level": _trust_level(float(trust_score)) if trust_score is not None else "unknown",
        "component_breakdown": [],
        "calibration_evidence": {
            "scoreboard_by_window": scoreboard_by_window if isinstance(scoreboard_by_window, list) else [],
            "alert_severity_counts": alert_counts if isinstance(alert_counts, Mapping) else {},
        },
        "drift_evidence": {
            "latest_alert": latest_alert if isinstance(latest_alert, Mapping) else {},
        },
        "reason_codes": list(latest_alert.get("reason_codes", [])) if isinstance(latest_alert, Mapping) else [],
        "narrative": narrative,
    }


def _normalize_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    merged = dict(_DEFAULT_WEIGHTS)
    if weights is not None:
        for key, value in weights.items():
            if key in merged:
                try:
                    merged[key] = max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
    total = sum(merged.values()) or 1.0
    return {key: value / total for key, value in merged.items()}


def _clip_unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number))


def _component_explanation(*, name: str, raw_value: float, effective_value: float) -> str:
    if name == "manipulation_suspect":
        return (
            f"manipulation_suspect raw={raw_value:.2f} reduces effective trust to "
            f"{effective_value:.2f}"
        )
    return f"{name} contributed positively with normalized value {raw_value:.2f}"


def _metric_sentence(metrics: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("brier", "logloss", "ece"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            parts.append(f"{key}={float(value):.4f}")
    return "calibration metrics: " + ", ".join(parts) if parts else ""


def _trust_summary(score: float) -> str:
    if score >= 80:
        return "high trust: the market signal can be used with limited escalation"
    if score >= 60:
        return "moderate trust: use the signal with explicit review and supporting evidence"
    return "low trust: use this signal cautiously and prefer human escalation"


def _trust_level(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"
