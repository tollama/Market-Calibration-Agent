"""Adapter bridging MCA data structures to Trust Intelligence Pipeline inputs.

Converts scoreboard rows and feature data into the format expected by
``trust_intelligence.pipeline.trust_pipeline.TrustIntelligencePipeline.run()``.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Mapping

logger = logging.getLogger(__name__)

try:
    from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline
    from trust_intelligence.schemas import PipelineResult

    HAS_TRUST_INTELLIGENCE = True
except ImportError:
    HAS_TRUST_INTELLIGENCE = False

# Map MCA row fields → Trust Intelligence Pipeline feature names
_FEATURE_MAP: dict[str, str] = {
    "volume_24h": "volume_change_24h",
    "vol": "volume_change_24h",
    "liquidity_depth": "liquidity_depth",
    "historical_accuracy": "historical_accuracy",
    "days_to_resolution": "time_to_resolution",
    "tte_days": "time_to_resolution",
    "sentiment_score": "sentiment_score",
    "related_market_correlation": "related_market_correlation",
    "max_open_correlation": "related_market_correlation",
    "macro_event_flag": "macro_event_flag",
}

# Map MCA row fields → Trust Intelligence constraint context fields
_CONTEXT_MAP: dict[str, str] = {
    "trust_score": "trust_score",
    "volume_24h": "market_volume_24h",
    "days_to_resolution": "days_to_resolution",
    "tte_days": "days_to_resolution",
    "max_open_correlation": "max_open_correlation",
    "is_restricted_category": "is_restricted_category",
}


def _safe_float(value: object) -> float | None:
    """Coerce to float or return None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def extract_features(row: Mapping[str, object]) -> dict[str, float]:
    """Extract SHAP feature values from an MCA row."""
    features: dict[str, float] = {}
    for src_key, dst_key in _FEATURE_MAP.items():
        val = _safe_float(row.get(src_key))
        if val is not None and dst_key not in features:
            features[dst_key] = val
    return features


def extract_context(
    row: Mapping[str, object],
    *,
    v1_trust_score: float | None = None,
) -> dict[str, float]:
    """Extract constraint verification context from an MCA row."""
    context: dict[str, float] = {}
    for src_key, dst_key in _CONTEXT_MAP.items():
        val = _safe_float(row.get(src_key))
        if val is not None and dst_key not in context:
            context[dst_key] = val

    # Use v1 trust score as context if not already present
    if "trust_score" not in context and v1_trust_score is not None:
        context["trust_score"] = v1_trust_score / 100.0  # v1 is [0, 100]

    return context


def extract_prediction_probability(row: Mapping[str, object]) -> float | None:
    """Extract prediction probability from an MCA row."""
    for key in ("pred", "prediction", "p_yes", "probability"):
        val = _safe_float(row.get(key))
        if val is not None:
            return max(0.0, min(1.0, val))
    return None


def run_trust_intelligence_for_market(
    pipeline: Any,
    *,
    market_rows: list[Mapping[str, object]],
    v1_trust_score: float | None = None,
    conformal_bands: list[dict[str, object]] | None = None,
    conformal_actuals: list[float] | None = None,
    current_band: dict[str, object] | None = None,
) -> Any | None:
    """Run Trust Intelligence Pipeline for a single market.

    Parameters
    ----------
    pipeline
        A ``TrustIntelligencePipeline`` instance.
    market_rows
        All rows for this market (from feature frame).
    v1_trust_score
        The v1 trust score (0-100) for this market.
    conformal_bands, conformal_actuals, current_band
        Optional conformal calibration data.

    Returns
    -------
    PipelineResult or None
        Full pipeline output, or None if pipeline unavailable.
    """
    if not HAS_TRUST_INTELLIGENCE:
        return None

    if not market_rows:
        return None

    # Use the most recent row's prediction probability
    prediction_prob = None
    for row in reversed(market_rows):
        prediction_prob = extract_prediction_probability(row)
        if prediction_prob is not None:
            break

    if prediction_prob is None:
        # Fall back to average pred across rows
        preds = []
        for row in market_rows:
            p = extract_prediction_probability(row)
            if p is not None:
                preds.append(p)
        if preds:
            prediction_prob = sum(preds) / len(preds)
        else:
            prediction_prob = 0.5  # absolute fallback

    # Average features across rows
    feature_sums: dict[str, float] = {}
    feature_counts: dict[str, int] = {}
    for row in market_rows:
        for key, val in extract_features(row).items():
            feature_sums[key] = feature_sums.get(key, 0.0) + val
            feature_counts[key] = feature_counts.get(key, 0) + 1
    features = {
        key: feature_sums[key] / feature_counts[key]
        for key in feature_sums
    }

    # Use last row for context (most recent state)
    context = extract_context(market_rows[-1], v1_trust_score=v1_trust_score)

    try:
        result = pipeline.run(
            prediction_probability=prediction_prob,
            features=features if features else None,
            historical_bands=conformal_bands,
            actuals=conformal_actuals,
            current_band=current_band,
            context=context if context else None,
        )
        return result
    except Exception:
        logger.exception("Trust Intelligence Pipeline failed for market")
        return None


__all__ = [
    "HAS_TRUST_INTELLIGENCE",
    "extract_context",
    "extract_features",
    "extract_prediction_probability",
    "run_trust_intelligence_for_market",
]
