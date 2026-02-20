from __future__ import annotations

import pytest

from calibration.interval_metrics import (
    compute_interval_metrics,
    coverage_rate,
    mean_interval_width,
    pinball_loss,
)


def test_pinball_loss_basic() -> None:
    actuals = [0.2, 0.8]
    preds = [0.1, 0.7]
    assert pinball_loss(actuals, preds, 0.5) == pytest.approx(0.05, rel=0, abs=1e-12)


def test_coverage_and_width_with_swapped_bounds() -> None:
    actuals = [0.2, 0.6, 0.9]
    lower = [0.1, 0.7, 0.8]
    upper = [0.3, 0.5, 1.0]

    assert coverage_rate(actuals, lower, upper) == pytest.approx(1.0, rel=0, abs=1e-12)
    assert mean_interval_width(lower, upper) == pytest.approx((0.2 + 0.2 + 0.2) / 3, rel=0, abs=1e-12)


def test_compute_interval_metrics_includes_80_and_90() -> None:
    rows = [
        {"actual": 0.20, "q05": 0.05, "q10": 0.10, "q50": 0.20, "q90": 0.30, "q95": 0.35},
        {"actual": 0.80, "q05": 0.60, "q10": 0.70, "q50": 0.78, "q90": 0.90, "q95": 0.95},
        {"actual": 0.45, "q05": 0.30, "q10": 0.35, "q50": 0.40, "q90": 0.55, "q95": 0.60},
    ]
    metrics = compute_interval_metrics(rows)

    assert metrics.samples == 3
    assert metrics.coverage_80 == pytest.approx(1.0, rel=0, abs=1e-12)
    assert metrics.coverage_90 == pytest.approx(1.0, rel=0, abs=1e-12)
    assert metrics.mean_width_80 > 0
    assert metrics.mean_width_90 > metrics.mean_width_80
    assert metrics.pinball_mean >= 0


def test_compute_interval_metrics_90_optional() -> None:
    rows = [
        {"actual": 0.2, "q10": 0.1, "q50": 0.2, "q90": 0.3},
        {"actual": 0.7, "q10": 0.6, "q50": 0.7, "q90": 0.8},
    ]
    metrics = compute_interval_metrics(rows)

    assert metrics.coverage_90 is None
    assert metrics.mean_width_90 is None
