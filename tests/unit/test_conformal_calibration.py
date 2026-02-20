from __future__ import annotations

import pytest

from calibration.conformal import (
    ConformalAdjustment,
    apply_conformal_adjustment,
    coverage_report,
    fit_conformal_adjustment,
)


def test_fit_conformal_adjustment_nominal_path() -> None:
    historical_bands = [
        {"q10": -1.0, "q50": 0.0, "q90": 1.0},
        {"q10": -1.0, "q50": 0.0, "q90": 1.0},
        {"q10": -1.0, "q50": 0.0, "q90": 1.0},
    ]
    actuals = [0.0, 1.0, -2.0]

    adjustment = fit_conformal_adjustment(
        historical_bands,
        actuals,
        target_coverage=0.5,
    )

    assert adjustment.target_coverage == pytest.approx(0.5, rel=0, abs=1e-12)
    assert adjustment.quantile_level == pytest.approx(2.0 / 3.0, rel=0, abs=1e-12)
    assert adjustment.center_shift == pytest.approx(0.0, rel=0, abs=1e-12)
    assert adjustment.width_scale == pytest.approx(4.0 / 3.0, rel=0, abs=1e-12)
    assert adjustment.sample_size == 3


def test_apply_conformal_adjustment_clipping_behavior() -> None:
    band = {"q10": 0.2, "q50": 0.5, "q90": 0.8, "series": "A"}
    adjustment = ConformalAdjustment(
        target_coverage=0.8,
        quantile_level=1.0,
        center_shift=0.6,
        width_scale=4.0,
        sample_size=12,
    )

    adjusted = apply_conformal_adjustment(band, adjustment, clip_range=(0.0, 1.0))

    assert adjusted["q10"] == pytest.approx(0.0, rel=0, abs=1e-12)
    assert adjusted["q50"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert adjusted["q90"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert adjusted["series"] == "A"
    assert adjusted["band_calibration"] == "conformal"
    assert adjusted["conformal_target_coverage"] == pytest.approx(0.8, rel=0, abs=1e-12)
    assert adjusted["conformal_quantile_level"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert adjusted["conformal_center_shift"] == pytest.approx(0.6, rel=0, abs=1e-12)
    assert adjusted["conformal_width_scale"] == pytest.approx(4.0, rel=0, abs=1e-12)


def test_coverage_report_correctness() -> None:
    bands = [
        {"q10": 0.1, "q90": 0.3},
        {"q10": 0.4, "q90": 0.2},
        {"q10": 0.0, "q90": 0.8},
    ]
    actuals = [0.2, 0.35, 0.9]

    report = coverage_report(bands, actuals)

    assert set(report) == {
        "samples",
        "empirical_coverage",
        "mean_interval_width",
        "median_interval_width",
    }
    assert report["samples"] == pytest.approx(3.0, rel=0, abs=1e-12)
    assert report["empirical_coverage"] == pytest.approx(2.0 / 3.0, rel=0, abs=1e-12)
    assert report["mean_interval_width"] == pytest.approx(0.4, rel=0, abs=1e-12)
    assert report["median_interval_width"] == pytest.approx(0.2, rel=0, abs=1e-12)


@pytest.mark.parametrize(
    ("historical_bands", "actuals", "target_coverage"),
    [
        ([{"q10": 0.1, "q50": 0.2, "q90": 0.3}], [0.2, 0.3], 0.8),  # length mismatch
        ([], [], 0.8),  # empty
        ([{"q10": 0.1, "q50": 0.2, "q90": 0.3}], [0.2], 0.0),  # invalid coverage
        ([{"q10": 0.1, "q50": 0.2, "q90": 0.3}], [0.2], 1.1),  # invalid coverage
    ],
)
def test_fit_conformal_adjustment_validation_errors(
    historical_bands: list[dict[str, float]],
    actuals: list[float],
    target_coverage: float,
) -> None:
    with pytest.raises(ValueError):
        fit_conformal_adjustment(
            historical_bands,
            actuals,
            target_coverage=target_coverage,
        )


def test_coverage_report_validation_errors() -> None:
    with pytest.raises(ValueError):
        coverage_report([{"q10": 0.1, "q90": 0.2}], [0.1, 0.2])  # length mismatch

    with pytest.raises(ValueError):
        coverage_report([], [])  # empty
