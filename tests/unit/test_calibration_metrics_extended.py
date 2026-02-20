from __future__ import annotations

import pytest

from calibration.metrics import (
    brier_score,
    calibration_slope_intercept,
    expected_calibration_error,
    log_loss,
    summarize_metrics_extended,
)


def test_calibration_slope_intercept_deterministic_values() -> None:
    preds = [0.1, 0.4, 0.8, 0.9]
    labels = [0, 0, 1, 1]

    result = calibration_slope_intercept(preds, labels)

    assert set(result) == {"slope", "intercept"}
    assert result["slope"] == pytest.approx(1.4634146341463414, rel=0, abs=1e-12)
    assert result["intercept"] == pytest.approx(-0.30487804878048785, rel=0, abs=1e-12)


def test_summarize_metrics_extended_contains_expected_fields() -> None:
    preds = [0.2, 0.7, 0.9, 0.4]
    labels = [0, 1, 1, 0]

    summary = summarize_metrics_extended(preds, labels)
    slope_intercept = calibration_slope_intercept(preds, labels)

    assert set(summary) == {"brier", "log_loss", "ece", "slope", "intercept"}
    assert summary["brier"] == pytest.approx(brier_score(preds, labels), rel=0, abs=1e-12)
    assert summary["log_loss"] == pytest.approx(log_loss(preds, labels), rel=0, abs=1e-12)
    assert summary["ece"] == pytest.approx(
        expected_calibration_error(preds, labels, bins=10), rel=0, abs=1e-12
    )
    assert summary["slope"] == pytest.approx(slope_intercept["slope"], rel=0, abs=1e-12)
    assert summary["intercept"] == pytest.approx(
        slope_intercept["intercept"], rel=0, abs=1e-12
    )


@pytest.mark.parametrize(
    ("preds", "labels"),
    [
        ([0.1], [0, 1]),  # length mismatch
        ([], []),  # empty
        ([1.1, 0.2], [1, 0]),  # prediction out of range
        ([0.8, 0.1], [1, 2]),  # label not in {0, 1}
    ],
)
def test_extended_metrics_validation_errors(preds: list[float], labels: list[int]) -> None:
    with pytest.raises(ValueError):
        calibration_slope_intercept(preds, labels)
    with pytest.raises(ValueError):
        summarize_metrics_extended(preds, labels)
