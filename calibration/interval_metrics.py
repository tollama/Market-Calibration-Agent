from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


def _as_float(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(result) or math.isinf(result):
        raise ValueError(f"Non-finite value for {name}: {value}")
    return result


@dataclass(frozen=True)
class IntervalMetrics:
    samples: int
    coverage_80: float
    coverage_90: float | None
    mean_width_80: float
    mean_width_90: float | None
    pinball_q10: float
    pinball_q50: float
    pinball_q90: float
    pinball_mean: float


def pinball_loss(actuals: Sequence[float], preds: Sequence[float], quantile: float) -> float:
    if len(actuals) != len(preds):
        raise ValueError("actuals and preds must have equal length")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be in [0,1]")
    if not actuals:
        raise ValueError("At least one sample is required")

    total = 0.0
    for idx, (actual, pred) in enumerate(zip(actuals, preds)):
        y = _as_float(actual, name=f"actual[{idx}]")
        q = _as_float(pred, name=f"pred[{idx}]")
        err = y - q
        total += quantile * err if err >= 0 else (quantile - 1.0) * err
    return total / len(actuals)


def coverage_rate(actuals: Sequence[float], lower: Sequence[float], upper: Sequence[float]) -> float:
    if len(actuals) != len(lower) or len(actuals) != len(upper):
        raise ValueError("actuals, lower, and upper must have equal length")
    if not actuals:
        raise ValueError("At least one sample is required")

    covered = 0
    for idx, (actual, lo, hi) in enumerate(zip(actuals, lower, upper)):
        y = _as_float(actual, name=f"actual[{idx}]")
        l = _as_float(lo, name=f"lower[{idx}]")
        h = _as_float(hi, name=f"upper[{idx}]")
        if l > h:
            l, h = h, l
        if l <= y <= h:
            covered += 1
    return covered / len(actuals)


def mean_interval_width(lower: Sequence[float], upper: Sequence[float]) -> float:
    if len(lower) != len(upper):
        raise ValueError("lower and upper must have equal length")
    if not lower:
        raise ValueError("At least one sample is required")
    widths = []
    for idx, (lo, hi) in enumerate(zip(lower, upper)):
        l = _as_float(lo, name=f"lower[{idx}]")
        h = _as_float(hi, name=f"upper[{idx}]")
        if l > h:
            l, h = h, l
        widths.append(h - l)
    return sum(widths) / len(widths)


def compute_interval_metrics(rows: Iterable[Mapping[str, object]]) -> IntervalMetrics:
    actuals: list[float] = []
    q10: list[float] = []
    q50: list[float] = []
    q90: list[float] = []
    q05: list[float] = []
    q95: list[float] = []
    has_90 = True

    for idx, row in enumerate(rows):
        actuals.append(_as_float(row["actual"], name=f"actual[{idx}]"))
        q10.append(_as_float(row["q10"], name=f"q10[{idx}]"))
        q50.append(_as_float(row["q50"], name=f"q50[{idx}]"))
        q90.append(_as_float(row["q90"], name=f"q90[{idx}]"))

        if "q05" in row and "q95" in row and row["q05"] is not None and row["q95"] is not None:
            q05.append(_as_float(row["q05"], name=f"q05[{idx}]"))
            q95.append(_as_float(row["q95"], name=f"q95[{idx}]"))
        else:
            has_90 = False

    if not actuals:
        raise ValueError("At least one sample is required")

    coverage_90 = coverage_rate(actuals, q05, q95) if has_90 else None
    mean_width_90 = mean_interval_width(q05, q95) if has_90 else None

    p10 = pinball_loss(actuals, q10, 0.1)
    p50 = pinball_loss(actuals, q50, 0.5)
    p90 = pinball_loss(actuals, q90, 0.9)

    return IntervalMetrics(
        samples=len(actuals),
        coverage_80=coverage_rate(actuals, q10, q90),
        coverage_90=coverage_90,
        mean_width_80=mean_interval_width(q10, q90),
        mean_width_90=mean_width_90,
        pinball_q10=p10,
        pinball_q50=p50,
        pinball_q90=p90,
        pinball_mean=(p10 + p50 + p90) / 3.0,
    )


__all__ = [
    "IntervalMetrics",
    "pinball_loss",
    "coverage_rate",
    "mean_interval_width",
    "compute_interval_metrics",
]
