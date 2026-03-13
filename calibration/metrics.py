from __future__ import annotations

import math
from typing import Mapping, Sequence

DEFAULT_BINS = 10
DEFAULT_EPS = 1e-6
DEFAULT_MIN_CONFIDENCE_SAMPLES = 30

_PREDICTION_KEYS = ("pred", "prediction", "p_yes", "probability", "prob", "score")
_LABEL_KEYS = ("label", "target", "y")


def _as_finite_float(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(result) or math.isinf(result):
        raise ValueError(f"Non-finite numeric value for {name}: {value}")
    return result


def _validate_binary_label(value: object, *, index: int) -> int:
    label = _as_finite_float(value, name=f"labels[{index}]")
    if label not in (0.0, 1.0):
        raise ValueError(f"labels[{index}] must be 0 or 1, got: {value}")
    return int(label)


def _validate_probability(value: object, *, name: str) -> float:
    pred = _as_finite_float(value, name=name)
    if pred < 0.0 or pred > 1.0:
        raise ValueError(f"{name} must be in [0, 1], got: {value}")
    return pred


def _validate_inputs(
    preds: Sequence[object],
    labels: Sequence[object],
) -> tuple[list[float], list[int]]:
    if len(preds) != len(labels):
        raise ValueError("preds and labels must have equal length")
    if not preds:
        raise ValueError("preds and labels must be non-empty")

    norm_preds: list[float] = []
    norm_labels: list[int] = []
    for idx, (pred, label) in enumerate(zip(preds, labels)):
        norm_preds.append(_validate_probability(pred, name=f"preds[{idx}]"))
        norm_labels.append(_validate_binary_label(label, index=idx))
    return norm_preds, norm_labels


def _validate_eps(eps: float) -> float:
    clipped_eps = _as_finite_float(eps, name="eps")
    if clipped_eps <= 0.0 or clipped_eps >= 0.5:
        raise ValueError("eps must be in (0, 0.5)")
    return clipped_eps


def _validate_bins(bins: int) -> int:
    if isinstance(bins, bool) or not isinstance(bins, int) or bins <= 0:
        raise ValueError("bins must be a positive integer")
    return bins


def _extract_row_value(
    row: Mapping[str, object],
    *,
    keys: Sequence[str],
    row_index: int,
    value_name: str,
) -> object:
    for key in keys:
        if key in row:
            return row[key]
    expected = ", ".join(keys)
    raise ValueError(f"rows[{row_index}] missing {value_name}; expected one of: {expected}")


def brier_score(preds: Sequence[object], labels: Sequence[object]) -> float:
    """Return mean squared error between predicted probabilities and binary labels."""
    norm_preds, norm_labels = _validate_inputs(preds, labels)
    n = len(norm_preds)
    return sum((pred - label) ** 2 for pred, label in zip(norm_preds, norm_labels)) / n


def log_loss(
    preds: Sequence[object],
    labels: Sequence[object],
    eps: float = DEFAULT_EPS,
) -> float:
    """Return binary cross-entropy for probability predictions."""
    norm_preds, norm_labels = _validate_inputs(preds, labels)
    clipped_eps = _validate_eps(eps)
    n = len(norm_preds)
    total = 0.0
    for pred, label in zip(norm_preds, norm_labels):
        clipped = min(max(pred, clipped_eps), 1.0 - clipped_eps)
        total -= label * math.log(clipped) + (1 - label) * math.log(1.0 - clipped)
    return total / n


def expected_calibration_error(
    preds: Sequence[object],
    labels: Sequence[object],
    bins: int = DEFAULT_BINS,
) -> float:
    """
    Return ECE using deterministic equal-width bins on [0, 1].

    Bin index is computed as min(int(pred * bins), bins - 1), which ensures 1.0
    is always assigned to the final bin.
    """
    norm_preds, norm_labels = _validate_inputs(preds, labels)
    n_bins = _validate_bins(bins)

    counts = [0] * n_bins
    pred_sums = [0.0] * n_bins
    label_sums = [0.0] * n_bins
    total_count = len(norm_preds)

    for pred, label in zip(norm_preds, norm_labels):
        idx = min(int(pred * n_bins), n_bins - 1)
        counts[idx] += 1
        pred_sums[idx] += pred
        label_sums[idx] += label

    ece = 0.0
    for idx, count in enumerate(counts):
        if count == 0:
            continue
        avg_pred = pred_sums[idx] / count
        avg_label = label_sums[idx] / count
        ece += abs(avg_pred - avg_label) * (count / total_count)
    return ece


def calibration_slope_intercept(
    preds: Sequence[object],
    labels: Sequence[object],
) -> dict[str, float]:
    """Return least-squares slope/intercept for label ~ pred."""
    norm_preds, norm_labels = _validate_inputs(preds, labels)

    n = len(norm_preds)
    mean_pred = sum(norm_preds) / n
    mean_label = sum(norm_labels) / n

    ss_xx = sum((pred - mean_pred) ** 2 for pred in norm_preds)
    if ss_xx == 0.0:
        return {"slope": 0.0, "intercept": mean_label}

    ss_xy = sum(
        (pred - mean_pred) * (label - mean_label)
        for pred, label in zip(norm_preds, norm_labels)
    )
    slope = ss_xy / ss_xx
    intercept = mean_label - slope * mean_pred
    return {"slope": slope, "intercept": intercept}


def assess_confidence(
    sample_size: int,
    min_samples: int = DEFAULT_MIN_CONFIDENCE_SAMPLES,
) -> dict[str, object]:
    """Return confidence metadata for a metric set based on sample size.

    When ``sample_size`` < ``min_samples`` the metrics are flagged as
    ``low_confidence`` to warn consumers that the computed values may be
    unreliable due to insufficient data (e.g. thin markets).
    """
    return {
        "sample_size": sample_size,
        "low_confidence": sample_size < min_samples,
        "min_confidence_samples": min_samples,
    }


def summarize_metrics(
    preds: Sequence[object],
    labels: Sequence[object],
) -> dict[str, float]:
    """Return the standard calibration metric bundle for one prediction set."""
    return {
        "brier": brier_score(preds, labels),
        "log_loss": log_loss(preds, labels, eps=DEFAULT_EPS),
        "ece": expected_calibration_error(preds, labels, bins=DEFAULT_BINS),
    }


def summarize_metrics_extended(
    preds: Sequence[object],
    labels: Sequence[object],
) -> dict[str, float]:
    """Return standard calibration metrics plus slope/intercept."""
    return {
        "brier": brier_score(preds, labels),
        "log_loss": log_loss(preds, labels, eps=DEFAULT_EPS),
        "ece": expected_calibration_error(preds, labels, bins=DEFAULT_BINS),
        **calibration_slope_intercept(preds, labels),
    }


def segment_metrics(
    rows: Sequence[Mapping[str, object]],
    segment_key: str,
) -> dict[object, dict[str, float]]:
    """
    Compute summary metrics per segment.

    Each row must include `segment_key`, plus one prediction key in
    (`pred`, `prediction`, `p_yes`, `probability`, `prob`, `score`)
    and one label key in (`label`, `target`, `y`).
    """
    if not rows:
        raise ValueError("rows must be non-empty")
    if not isinstance(segment_key, str) or not segment_key:
        raise ValueError("segment_key must be a non-empty string")

    grouped_preds: dict[object, list[object]] = {}
    grouped_labels: dict[object, list[object]] = {}

    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{idx}] must be a mapping")
        if segment_key not in row:
            raise ValueError(f"rows[{idx}] missing segment key: {segment_key}")

        segment_value = row[segment_key]
        try:
            hash(segment_value)
        except TypeError as exc:
            raise ValueError(
                f"rows[{idx}] segment value for '{segment_key}' must be hashable"
            ) from exc

        pred = _extract_row_value(
            row,
            keys=_PREDICTION_KEYS,
            row_index=idx,
            value_name="prediction field",
        )
        label = _extract_row_value(
            row,
            keys=_LABEL_KEYS,
            row_index=idx,
            value_name="label field",
        )

        grouped_preds.setdefault(segment_value, []).append(pred)
        grouped_labels.setdefault(segment_value, []).append(label)

    return {
        segment_value: summarize_metrics(grouped_preds[segment_value], grouped_labels[segment_value])
        for segment_value in grouped_preds
    }


def base_rate_drift(
    rows: Sequence[Mapping[str, object]],
    time_key: str = "ts",
    n_windows: int = 4,
) -> dict[str, object]:
    """Detect time-varying base rate drift across chronological windows.

    Splits *rows* into ``n_windows`` equal-sized buckets ordered by
    ``time_key``, computes per-window base rate and calibration metrics,
    and flags ``drift_detected`` when the base rate swing (max - min)
    exceeds ``0.15`` or the per-window Brier score trend is increasing.

    Returns a dict with per-window summaries and an overall drift flag that
    downstream consumers can use to decide whether adaptive recalibration
    is needed.
    """
    if not rows:
        raise ValueError("rows must be non-empty")
    if n_windows < 2:
        raise ValueError("n_windows must be >= 2")

    decorated: list[tuple[object, object, object]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{idx}] must be a mapping")
        if time_key not in row:
            raise ValueError(f"rows[{idx}] missing time key: {time_key}")
        pred = _extract_row_value(
            row, keys=_PREDICTION_KEYS, row_index=idx, value_name="prediction field",
        )
        label = _extract_row_value(
            row, keys=_LABEL_KEYS, row_index=idx, value_name="label field",
        )
        decorated.append((row[time_key], pred, label))

    decorated.sort(key=lambda t: t[0])

    total = len(decorated)
    window_size = max(1, total // n_windows)
    windows: list[dict[str, object]] = []

    for i in range(n_windows):
        start = i * window_size
        end = start + window_size if i < n_windows - 1 else total
        chunk = decorated[start:end]
        if not chunk:
            continue

        w_preds = [c[1] for c in chunk]
        w_labels = [c[2] for c in chunk]
        norm_preds, norm_labels = _validate_inputs(w_preds, w_labels)

        base_rate = sum(norm_labels) / len(norm_labels)
        mean_pred = sum(norm_preds) / len(norm_preds)
        w_brier = brier_score(w_preds, w_labels)

        windows.append({
            "window_index": i,
            "sample_size": len(chunk),
            "base_rate": base_rate,
            "mean_pred": mean_pred,
            "pred_base_gap": abs(mean_pred - base_rate),
            "brier": w_brier,
            "ts_min": chunk[0][0],
            "ts_max": chunk[-1][0],
        })

    base_rates = [float(w["base_rate"]) for w in windows]  # type: ignore[arg-type]
    brier_values = [float(w["brier"]) for w in windows]  # type: ignore[arg-type]

    base_rate_swing = max(base_rates) - min(base_rates) if base_rates else 0.0

    # Detect monotonically increasing Brier (degradation over time)
    brier_increasing = all(
        brier_values[j] <= brier_values[j + 1]
        for j in range(len(brier_values) - 1)
    ) if len(brier_values) >= 2 else False

    drift_detected = base_rate_swing > 0.15 or (brier_increasing and base_rate_swing > 0.05)

    return {
        "n_windows": len(windows),
        "windows": windows,
        "base_rate_swing": base_rate_swing,
        "brier_trend_increasing": brier_increasing,
        "drift_detected": drift_detected,
    }


def recalibrate_predictions(
    preds: Sequence[object],
    labels: Sequence[object],
    *,
    recent_base_rate: float | None = None,
    recent_n: int = 0,
) -> list[float]:
    """Apply simple base-rate shift recalibration to predictions.

    When a ``recent_base_rate`` is provided (e.g. from the latest window of
    :func:`base_rate_drift`), predictions are shifted toward the recent base
    rate using a log-odds adjustment.  This compensates for time-varying base
    rates without re-training the underlying model.

    If ``recent_base_rate`` is None or ``recent_n`` < 10, the original
    predictions are returned unchanged (insufficient evidence for correction).
    """
    norm_preds, _ = _validate_inputs(preds, labels)

    if recent_base_rate is None or recent_n < 10:
        return norm_preds

    overall_base_rate = sum(_validate_binary_label(l, index=i) for i, l in enumerate(labels)) / len(labels)

    # Avoid division by zero / extreme log-odds
    eps = 1e-6
    clamp = lambda x: min(max(x, eps), 1.0 - eps)  # noqa: E731

    overall_logit = math.log(clamp(overall_base_rate) / (1.0 - clamp(overall_base_rate)))
    recent_logit = math.log(clamp(recent_base_rate) / (1.0 - clamp(recent_base_rate)))
    shift = recent_logit - overall_logit

    adjusted: list[float] = []
    for pred in norm_preds:
        p = clamp(pred)
        logit_p = math.log(p / (1.0 - p))
        adjusted_logit = logit_p + shift
        adjusted_p = 1.0 / (1.0 + math.exp(-adjusted_logit))
        adjusted.append(adjusted_p)

    return adjusted


__all__ = [
    "DEFAULT_MIN_CONFIDENCE_SAMPLES",
    "assess_confidence",
    "base_rate_drift",
    "brier_score",
    "log_loss",
    "expected_calibration_error",
    "calibration_slope_intercept",
    "recalibrate_predictions",
    "segment_metrics",
    "summarize_metrics",
    "summarize_metrics_extended",
]
