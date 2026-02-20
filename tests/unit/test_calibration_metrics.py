from __future__ import annotations

import math

import pytest

from calibration.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
    segment_metrics,
    summarize_metrics,
)


def test_point_metrics_nominal_values() -> None:
    preds = [0.1, 0.4, 0.8, 0.9]
    labels = [0, 0, 1, 1]

    assert brier_score(preds, labels) == pytest.approx(0.055, rel=0, abs=1e-12)

    expected_logloss = -(
        math.log(0.9) + math.log(0.6) + math.log(0.8) + math.log(0.9)
    ) / 4.0
    assert log_loss(preds, labels) == pytest.approx(expected_logloss, rel=0, abs=1e-12)

    assert expected_calibration_error(preds, labels) == pytest.approx(0.2, rel=0, abs=1e-12)


def test_ece_handles_boundary_probabilities_deterministically() -> None:
    preds = [0.0, 1.0]
    labels = [0, 1]
    assert expected_calibration_error(preds, labels, bins=10) == pytest.approx(
        0.0, rel=0, abs=1e-12
    )


def test_summarize_metrics_uses_default_parameters() -> None:
    preds = [0.2, 0.7, 0.9, 0.4]
    labels = [0, 1, 1, 0]

    summary = summarize_metrics(preds, labels)

    assert set(summary) == {"brier", "log_loss", "ece"}
    assert summary["brier"] == pytest.approx(brier_score(preds, labels), rel=0, abs=1e-12)
    assert summary["log_loss"] == pytest.approx(log_loss(preds, labels), rel=0, abs=1e-12)
    assert summary["ece"] == pytest.approx(
        expected_calibration_error(preds, labels, bins=10), rel=0, abs=1e-12
    )


def test_segment_metrics_nominal_computation() -> None:
    rows = [
        {"segment": "A", "pred": 0.1, "label": 0},
        {"segment": "A", "pred": 0.9, "label": 1},
        {"segment": "B", "p_yes": 0.8, "label": 0},
        {"segment": "B", "p_yes": 0.2, "label": 1},
    ]

    result = segment_metrics(rows, "segment")

    assert set(result) == {"A", "B"}
    assert result["A"]["brier"] == pytest.approx(0.01, rel=0, abs=1e-12)
    assert result["A"]["log_loss"] == pytest.approx(-math.log(0.9), rel=0, abs=1e-12)
    assert result["A"]["ece"] == pytest.approx(0.1, rel=0, abs=1e-12)

    assert result["B"]["brier"] == pytest.approx(0.64, rel=0, abs=1e-12)
    assert result["B"]["log_loss"] == pytest.approx(-math.log(0.2), rel=0, abs=1e-12)
    assert result["B"]["ece"] == pytest.approx(0.8, rel=0, abs=1e-12)


@pytest.mark.parametrize(
    ("preds", "labels"),
    [
        ([0.1], [0, 1]),  # length mismatch
        ([], []),  # empty
        ([1.1, 0.2], [1, 0]),  # prediction out of range
        ([0.8, 0.1], [1, 2]),  # label not in {0, 1}
    ],
)
def test_metric_input_validation_errors(preds: list[float], labels: list[int]) -> None:
    with pytest.raises(ValueError):
        brier_score(preds, labels)
    with pytest.raises(ValueError):
        log_loss(preds, labels)
    with pytest.raises(ValueError):
        expected_calibration_error(preds, labels)


def test_log_loss_validates_eps() -> None:
    preds = [0.2, 0.8]
    labels = [0, 1]
    with pytest.raises(ValueError):
        log_loss(preds, labels, eps=0.0)
    with pytest.raises(ValueError):
        log_loss(preds, labels, eps=0.5)


def test_ece_validates_bins() -> None:
    preds = [0.2, 0.8]
    labels = [0, 1]
    with pytest.raises(ValueError):
        expected_calibration_error(preds, labels, bins=0)
    with pytest.raises(ValueError):
        expected_calibration_error(preds, labels, bins=-3)
    with pytest.raises(ValueError):
        expected_calibration_error(preds, labels, bins=True)  # type: ignore[arg-type]


def test_segment_metrics_validation_errors() -> None:
    with pytest.raises(ValueError):
        segment_metrics([], "segment")

    with pytest.raises(ValueError):
        segment_metrics([{"pred": 0.2, "label": 0}], "segment")

    with pytest.raises(ValueError):
        segment_metrics([{"segment": "A", "label": 1}], "segment")

    with pytest.raises(ValueError):
        segment_metrics([{"segment": "A", "pred": 0.2}], "segment")
