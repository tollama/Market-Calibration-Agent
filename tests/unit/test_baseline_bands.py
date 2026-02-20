from __future__ import annotations

import math

import pytest

from runners.baselines import ewma_band, forecast_baseline_band, rolling_quantile_band


def test_ewma_band_schema_and_bounds() -> None:
    series = [0.31, 0.34, 0.37, 0.39, 0.42, 0.44]

    band = ewma_band(
        series,
        horizon_steps=4,
        step_seconds=300,
        alpha=0.3,
        market_id="mkt-1",
        ts="2026-02-20T12:00:00Z",
    )

    assert band["method"] == "EWMA"
    assert band["market_id"] == "mkt-1"
    assert band["horizon_steps"] == 4
    assert band["step_seconds"] == 300
    assert band["band_calibration"] == "raw"
    assert band["ts"] == "2026-02-20T12:00:00Z"
    assert 0 <= band["q10"] <= band["q50"] <= band["q90"] <= 1


def test_rolling_quantile_band_matches_window_quantiles() -> None:
    series = [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]
    band = rolling_quantile_band(series, window=5)

    # Window is [0.10, 0.20, 0.30, 0.40, 0.50]
    assert math.isclose(band["q10"], 0.14, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(band["q50"], 0.30, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(band["q90"], 0.46, rel_tol=0, abs_tol=1e-12)
    assert band["method"] == "ROLLING_QUANTILE"


def test_forecast_baseline_band_dispatch_and_validation() -> None:
    series = [0.2, 0.3, 0.4, 0.5]

    ewma = forecast_baseline_band(series, method="ewma")
    rolling = forecast_baseline_band(series, method="rolling_quantile", window=3)

    assert ewma["method"] == "EWMA"
    assert rolling["method"] == "ROLLING_QUANTILE"
    with pytest.raises(ValueError):
        forecast_baseline_band(series, method="unsupported")


def test_logit_mode_handles_boundary_values() -> None:
    series = [0.0, 1.0, 0.99, 0.01, 0.5]

    band = ewma_band(series, use_logit=True)

    assert 0 <= band["q10"] <= band["q50"] <= band["q90"] <= 1

