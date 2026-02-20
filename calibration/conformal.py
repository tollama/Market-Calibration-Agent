from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple


def _empirical_quantile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot compute quantiles from an empty sequence")
    if quantile <= 0:
        return min(values)
    if quantile >= 1:
        return max(values)

    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    weight = rank - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def _conformal_quantile_level(n: int, target_coverage: float) -> float:
    # Split-conformal finite-sample level: ceil((n+1)*(1-alpha))/n where coverage=1-alpha.
    level = math.ceil((n + 1) * target_coverage) / n
    return max(0.0, min(1.0, level))


def _as_float(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(result) or math.isinf(result):
        raise ValueError(f"Non-finite value for {name}: {value}")
    return result


@dataclass(frozen=True)
class ConformalAdjustment:
    """Quantile interval adjustment parameters learned from calibration data."""

    target_coverage: float
    quantile_level: float
    center_shift: float
    width_scale: float
    sample_size: int


def fit_conformal_adjustment(
    historical_bands: Sequence[Mapping[str, object]],
    actuals: Sequence[float],
    *,
    target_coverage: float = 0.8,
    lower_key: str = "q10",
    median_key: str = "q50",
    upper_key: str = "q90",
    min_half_width: float = 1e-6,
) -> ConformalAdjustment:
    """
    Fit center-shift and width-scale adjustment from historical forecast bands.

    `target_coverage` is the desired empirical interval coverage (e.g. 0.8 or 0.9).
    """
    if not 0 < target_coverage <= 1:
        raise ValueError("target_coverage must be in (0, 1]")
    if len(historical_bands) != len(actuals):
        raise ValueError("historical_bands and actuals must have equal length")
    if not historical_bands:
        raise ValueError("At least one calibration sample is required")

    centers: list[float] = []
    half_widths: list[float] = []
    observations: list[float] = []

    for idx, (band, actual) in enumerate(zip(historical_bands, actuals)):
        low = _as_float(band[lower_key], name=f"{lower_key}[{idx}]")
        high = _as_float(band[upper_key], name=f"{upper_key}[{idx}]")
        if low > high:
            low, high = high, low

        if median_key in band:
            center = _as_float(band[median_key], name=f"{median_key}[{idx}]")
        else:
            center = (low + high) / 2

        centers.append(center)
        half_widths.append(max((high - low) / 2, min_half_width))
        observations.append(_as_float(actual, name=f"actual[{idx}]"))

    residuals = [obs - center for obs, center in zip(observations, centers)]
    center_shift = _empirical_quantile(residuals, 0.5)

    normalized_errors = [
        abs(obs - (center + center_shift)) / width
        for obs, center, width in zip(observations, centers, half_widths)
    ]
    quantile_level = _conformal_quantile_level(len(normalized_errors), target_coverage)
    width_scale = _empirical_quantile(normalized_errors, quantile_level)

    return ConformalAdjustment(
        target_coverage=float(target_coverage),
        quantile_level=float(quantile_level),
        center_shift=float(center_shift),
        width_scale=float(width_scale),
        sample_size=len(normalized_errors),
    )


def apply_conformal_adjustment(
    band: Mapping[str, object],
    adjustment: ConformalAdjustment,
    *,
    lower_key: str = "q10",
    median_key: str = "q50",
    upper_key: str = "q90",
    clip_range: Optional[Tuple[float, float]] = (0.0, 1.0),
) -> dict[str, object]:
    """Apply conformal center-shift/width-scale adjustment to one forecast band."""
    low = _as_float(band[lower_key], name=lower_key)
    high = _as_float(band[upper_key], name=upper_key)
    if low > high:
        low, high = high, low
    if median_key in band:
        center = _as_float(band[median_key], name=median_key)
    else:
        center = (low + high) / 2

    half_width = (high - low) / 2
    adjusted_center = center + adjustment.center_shift
    adjusted_half_width = half_width * adjustment.width_scale
    adjusted_low = adjusted_center - adjusted_half_width
    adjusted_high = adjusted_center + adjusted_half_width

    if clip_range is not None:
        lower_clip, upper_clip = clip_range
        adjusted_low = max(lower_clip, min(upper_clip, adjusted_low))
        adjusted_center = max(lower_clip, min(upper_clip, adjusted_center))
        adjusted_high = max(lower_clip, min(upper_clip, adjusted_high))

    adjusted = dict(band)
    adjusted[lower_key] = adjusted_low
    adjusted[median_key] = adjusted_center
    adjusted[upper_key] = adjusted_high
    adjusted["band_calibration"] = "conformal"
    adjusted["conformal_target_coverage"] = adjustment.target_coverage
    adjusted["conformal_quantile_level"] = adjustment.quantile_level
    adjusted["conformal_center_shift"] = adjustment.center_shift
    adjusted["conformal_width_scale"] = adjustment.width_scale
    return adjusted


def apply_conformal_adjustment_many(
    bands: Sequence[Mapping[str, object]],
    adjustment: ConformalAdjustment,
    *,
    lower_key: str = "q10",
    median_key: str = "q50",
    upper_key: str = "q90",
    clip_range: Optional[Tuple[float, float]] = (0.0, 1.0),
) -> list[dict[str, object]]:
    return [
        apply_conformal_adjustment(
            band,
            adjustment,
            lower_key=lower_key,
            median_key=median_key,
            upper_key=upper_key,
            clip_range=clip_range,
        )
        for band in bands
    ]


def coverage_report(
    bands: Sequence[Mapping[str, object]],
    actuals: Sequence[float],
    *,
    lower_key: str = "q10",
    upper_key: str = "q90",
) -> dict[str, float]:
    """Return simple interval diagnostics for a band set."""
    if len(bands) != len(actuals):
        raise ValueError("bands and actuals must have equal length")
    if not bands:
        raise ValueError("At least one sample is required")

    covered = 0
    widths: list[float] = []
    for idx, (band, actual) in enumerate(zip(bands, actuals)):
        low = _as_float(band[lower_key], name=f"{lower_key}[{idx}]")
        high = _as_float(band[upper_key], name=f"{upper_key}[{idx}]")
        if low > high:
            low, high = high, low
        observed = _as_float(actual, name=f"actual[{idx}]")
        if low <= observed <= high:
            covered += 1
        widths.append(high - low)

    n = len(bands)
    return {
        "samples": float(n),
        "empirical_coverage": covered / n,
        "mean_interval_width": sum(widths) / n,
        "median_interval_width": _empirical_quantile(widths, 0.5),
    }


__all__ = [
    "ConformalAdjustment",
    "fit_conformal_adjustment",
    "apply_conformal_adjustment",
    "apply_conformal_adjustment_many",
    "coverage_report",
]
