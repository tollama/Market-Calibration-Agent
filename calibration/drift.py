from __future__ import annotations

import math
from typing import Mapping

DEFAULT_TARGET_COVERAGE = 0.80
DEFAULT_MIN_SAMPLES = 200
DEFAULT_COVERAGE_TOLERANCE = 0.05
DEFAULT_WIDTH_EXPANSION_THRESHOLD = 1.5

REASON_LOW_COVERAGE = "LOW_COVERAGE"
REASON_WIDTH_EXPANSION = "WIDTH_EXPANSION"
REASON_INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"

_SAMPLES_KEYS = ("samples", "sample_size", "n")
_COVERAGE_KEYS = ("empirical_coverage", "coverage")
_MEAN_WIDTH_KEYS = ("mean_interval_width", "mean_width")


def _as_finite_float(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(result) or math.isinf(result):
        raise ValueError(f"Non-finite numeric value for {name}: {value}")
    return result


def _extract_metric(
    report: Mapping[str, object],
    *,
    keys: tuple[str, ...],
    report_name: str,
    metric_name: str,
) -> float:
    for key in keys:
        if key in report:
            return _as_finite_float(report[key], name=f"{report_name}.{key}")
    expected = ", ".join(keys)
    raise ValueError(
        f"{report_name} missing {metric_name}; expected one of: {expected}"
    )


def _validate_target_coverage(value: object) -> float:
    target = _as_finite_float(value, name="target_coverage")
    if target <= 0.0 or target > 1.0:
        raise ValueError("target_coverage must be in (0, 1]")
    return target


def _validate_min_samples(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("min_samples must be a positive integer")
    return value


def _validate_coverage_tolerance(value: object) -> float:
    tolerance = _as_finite_float(value, name="coverage_tolerance")
    if tolerance < 0.0 or tolerance >= 1.0:
        raise ValueError("coverage_tolerance must be in [0, 1)")
    return tolerance


def _validate_width_threshold(value: object) -> float:
    threshold = _as_finite_float(value, name="width_expansion_threshold")
    if threshold <= 0.0:
        raise ValueError("width_expansion_threshold must be positive")
    return threshold


def evaluate_retraining_need(
    current_report: Mapping[str, object],
    baseline_report: Mapping[str, object] | None = None,
    *,
    target_coverage: float = DEFAULT_TARGET_COVERAGE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    coverage_tolerance: float = DEFAULT_COVERAGE_TOLERANCE,
    width_expansion_threshold: float = DEFAULT_WIDTH_EXPANSION_THRESHOLD,
) -> dict[str, object]:
    if not isinstance(current_report, Mapping):
        raise ValueError("current_report must be a mapping")
    if baseline_report is not None and not isinstance(baseline_report, Mapping):
        raise ValueError("baseline_report must be a mapping when provided")

    normalized_target = _validate_target_coverage(target_coverage)
    normalized_min_samples = _validate_min_samples(min_samples)
    normalized_tolerance = _validate_coverage_tolerance(coverage_tolerance)
    normalized_width_threshold = _validate_width_threshold(width_expansion_threshold)

    current_samples = _extract_metric(
        current_report,
        keys=_SAMPLES_KEYS,
        report_name="current_report",
        metric_name="sample count",
    )
    current_coverage = _extract_metric(
        current_report,
        keys=_COVERAGE_KEYS,
        report_name="current_report",
        metric_name="empirical coverage",
    )
    current_mean_width = _extract_metric(
        current_report,
        keys=_MEAN_WIDTH_KEYS,
        report_name="current_report",
        metric_name="mean interval width",
    )

    if current_samples < 0:
        raise ValueError("current_report sample count must be non-negative")
    if current_coverage < 0.0 or current_coverage > 1.0:
        raise ValueError("current_report empirical coverage must be in [0, 1]")
    if current_mean_width < 0.0:
        raise ValueError("current_report mean interval width must be non-negative")

    coverage_floor = normalized_target - normalized_tolerance
    low_coverage = current_coverage < coverage_floor

    baseline_mean_width: float | None = None
    width_expansion_ratio: float | None = None
    width_expansion = False
    if baseline_report is not None:
        baseline_mean_width = _extract_metric(
            baseline_report,
            keys=_MEAN_WIDTH_KEYS,
            report_name="baseline_report",
            metric_name="mean interval width",
        )
        if baseline_mean_width < 0.0:
            raise ValueError("baseline_report mean interval width must be non-negative")

        if baseline_mean_width == 0.0:
            width_expansion_ratio = math.inf if current_mean_width > 0.0 else 1.0
        else:
            width_expansion_ratio = current_mean_width / baseline_mean_width
        width_expansion = width_expansion_ratio > normalized_width_threshold

    drift_reasons: list[str] = []
    if low_coverage:
        drift_reasons.append(REASON_LOW_COVERAGE)
    if width_expansion:
        drift_reasons.append(REASON_WIDTH_EXPANSION)

    sample_floor_met = current_samples >= float(normalized_min_samples)
    should_retrain = bool(drift_reasons) and sample_floor_met

    reason_codes = list(drift_reasons)
    if drift_reasons and not sample_floor_met:
        reason_codes.append(REASON_INSUFFICIENT_SAMPLES)

    diagnostics = {
        "current_samples": current_samples,
        "min_samples": normalized_min_samples,
        "sample_floor_met": sample_floor_met,
        "current_coverage": current_coverage,
        "target_coverage": normalized_target,
        "coverage_tolerance": normalized_tolerance,
        "coverage_floor": coverage_floor,
        "low_coverage": low_coverage,
        "current_mean_interval_width": current_mean_width,
        "baseline_mean_interval_width": baseline_mean_width,
        "width_expansion_ratio": width_expansion_ratio,
        "width_expansion_threshold": normalized_width_threshold,
        "width_expansion": width_expansion,
    }

    return {
        "should_retrain": should_retrain,
        "reason_codes": reason_codes,
        "diagnostics": diagnostics,
    }


__all__ = [
    "DEFAULT_TARGET_COVERAGE",
    "DEFAULT_MIN_SAMPLES",
    "DEFAULT_COVERAGE_TOLERANCE",
    "DEFAULT_WIDTH_EXPANSION_THRESHOLD",
    "REASON_LOW_COVERAGE",
    "REASON_WIDTH_EXPANSION",
    "REASON_INSUFFICIENT_SAMPLES",
    "evaluate_retraining_need",
]
