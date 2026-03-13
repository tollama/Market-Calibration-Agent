"""Derive trust score components from feature data.

Each component function transforms raw feature values into a [0, 1] signal.
When a required field is missing, the function returns a documented fallback
value so that the trust score pipeline never fails on incomplete data.

The ``derive_trust_components`` orchestrator calls all four functions and
returns a dict compatible with ``calibration.trust_score.compute_trust_score``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

_BUCKET_BASE: dict[str, float] = {
    "LOW": 0.2,
    "MID": 0.5,
    "HIGH": 0.8,
}


@dataclass(frozen=True)
class TrustComponentConfig:
    """Thresholds for component derivation (loadable from YAML)."""

    liquidity_high: float = 100_000.0
    volatility_ceiling: float = 0.3
    oi_spike_threshold: float = 0.30
    velocity_spike_threshold: float = 3.0


_DEFAULT_CONFIG = TrustComponentConfig()


def _safe_float(value: object, *, default: float) -> float:
    """Attempt to coerce *value* to a finite float; return *default* on failure."""
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---- individual component derivations ----


def derive_liquidity_depth(
    row: Mapping[str, object],
    *,
    config: TrustComponentConfig = _DEFAULT_CONFIG,
) -> float:
    """Derive liquidity_depth from market volume and liquidity bucket.

    Combines a coarse bucket base value (LOW=0.2, MID=0.5, HIGH=0.8) with a
    fine-grained normalized volume signal.  The blend ratio is 40% bucket base
    and 60% volume normalization.

    Returns 0.5 when required fields are missing.
    """
    bucket_str = str(row.get("liquidity_bucket", "")).upper()
    bucket_base = _BUCKET_BASE.get(bucket_str)

    volume = _safe_float(row.get("volume_24h"), default=float("nan"))
    oi = _safe_float(row.get("open_interest"), default=float("nan"))

    has_volume = not math.isnan(volume)
    has_oi = not math.isnan(oi)

    if bucket_base is None and not has_volume and not has_oi:
        return 0.5  # no information at all

    if bucket_base is None:
        bucket_base = 0.5

    if not has_volume and not has_oi:
        return _clip(bucket_base)

    raw = max(volume if has_volume else 0.0, oi if has_oi else 0.0)
    normalized = min(raw / config.liquidity_high, 1.0) if config.liquidity_high > 0 else 1.0
    return _clip(0.4 * bucket_base + 0.6 * normalized)


def derive_stability(
    row: Mapping[str, object],
    *,
    config: TrustComponentConfig = _DEFAULT_CONFIG,
) -> float:
    """Derive stability from rolling volatility.

    Low volatility means high stability.  The formula is
    ``1.0 − min(vol / volatility_ceiling, 1.0)``.

    Returns 0.5 when *vol* is missing.
    """
    vol = _safe_float(row.get("vol"), default=float("nan"))
    if math.isnan(vol):
        return 0.5
    if config.volatility_ceiling <= 0:
        return 0.5
    return _clip(1.0 - min(abs(vol) / config.volatility_ceiling, 1.0))


def derive_question_quality(
    row: Mapping[str, object],
) -> float:
    """Derive question quality from LLM evaluation scores.

    Uses ``ambiguity_score`` and ``resolution_risk_score`` (both [0, 1])
    produced by :class:`llm.schemas.QuestionQualityResult`.

    Returns 0.5 when both scores are missing.
    """
    ambiguity = _safe_float(row.get("ambiguity_score"), default=float("nan"))
    resolution_risk = _safe_float(row.get("resolution_risk_score"), default=float("nan"))

    has_ambiguity = not math.isnan(ambiguity)
    has_resolution_risk = not math.isnan(resolution_risk)

    if not has_ambiguity and not has_resolution_risk:
        return 0.5

    if has_ambiguity and has_resolution_risk:
        return _clip(1.0 - (0.6 * ambiguity + 0.4 * resolution_risk))
    if has_ambiguity:
        return _clip(1.0 - ambiguity)
    return _clip(1.0 - resolution_risk)


def derive_manipulation_suspect(
    row: Mapping[str, object],
    *,
    config: TrustComponentConfig = _DEFAULT_CONFIG,
) -> float:
    """Derive manipulation suspicion from OI change and volume velocity.

    Higher values indicate *more* suspicion of manipulation.  The formula takes
    the max anomaly signal from OI change and volume velocity, each normalised
    by its respective threshold.

    Returns 0.0 (no suspicion) when both fields are missing.
    """
    oi_change = _safe_float(row.get("oi_change"), default=float("nan"))
    volume_velocity = _safe_float(row.get("volume_velocity"), default=float("nan"))

    has_oi = not math.isnan(oi_change)
    has_vel = not math.isnan(volume_velocity)

    if not has_oi and not has_vel:
        return 0.0

    oi_anomaly = 0.0
    if has_oi and config.oi_spike_threshold > 0:
        oi_anomaly = min(abs(oi_change) / config.oi_spike_threshold, 1.0)

    vel_anomaly = 0.0
    if has_vel and config.velocity_spike_threshold > 0:
        vel_anomaly = min(abs(volume_velocity) / config.velocity_spike_threshold, 1.0)

    return _clip(max(oi_anomaly, vel_anomaly))


# ---- orchestrator ----


def derive_trust_components(
    row: Mapping[str, object],
    *,
    config: TrustComponentConfig | None = None,
) -> dict[str, float]:
    """Derive all four trust components from a single feature row.

    The returned dict is directly compatible with
    ``calibration.trust_score.compute_trust_score()``.
    """
    cfg = config if config is not None else _DEFAULT_CONFIG
    return {
        "liquidity_depth": derive_liquidity_depth(row, config=cfg),
        "stability": derive_stability(row, config=cfg),
        "question_quality": derive_question_quality(row),
        "manipulation_suspect": derive_manipulation_suspect(row, config=cfg),
    }


__all__ = [
    "TrustComponentConfig",
    "derive_liquidity_depth",
    "derive_manipulation_suspect",
    "derive_question_quality",
    "derive_stability",
    "derive_trust_components",
]
