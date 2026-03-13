from __future__ import annotations

import math

import pytest

from calibration.metrics import (
    assess_confidence,
    base_rate_drift,
    brier_score,
    expected_calibration_error,
    log_loss,
    recalibrate_predictions,
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


def test_assess_confidence_flags_small_samples() -> None:
    result = assess_confidence(10)
    assert result["low_confidence"] is True
    assert result["sample_size"] == 10
    assert result["min_confidence_samples"] == 30


def test_assess_confidence_passes_sufficient_samples() -> None:
    result = assess_confidence(30)
    assert result["low_confidence"] is False

    result = assess_confidence(100)
    assert result["low_confidence"] is False


def test_assess_confidence_custom_threshold() -> None:
    result = assess_confidence(50, min_samples=100)
    assert result["low_confidence"] is True
    assert result["min_confidence_samples"] == 100

    result = assess_confidence(100, min_samples=100)
    assert result["low_confidence"] is False


# --- base_rate_drift ---


def test_base_rate_drift_detects_stable_base_rate() -> None:
    # Uniform base rate across all windows → no drift
    rows = [
        {"ts": i, "pred": 0.5, "label": i % 2} for i in range(40)
    ]
    result = base_rate_drift(rows, n_windows=4)

    assert result["n_windows"] == 4
    assert result["drift_detected"] is False
    assert result["base_rate_swing"] == pytest.approx(0.0, abs=0.05)


def test_base_rate_drift_detects_shift() -> None:
    # First half: base_rate ~ 0.0, second half: base_rate ~ 1.0
    rows = []
    for i in range(20):
        rows.append({"ts": i, "pred": 0.5, "label": 0})
    for i in range(20, 40):
        rows.append({"ts": i, "pred": 0.5, "label": 1})

    result = base_rate_drift(rows, n_windows=4)

    assert result["drift_detected"] is True
    assert result["base_rate_swing"] >= 0.9  # Swing from 0 to 1


def test_base_rate_drift_returns_window_details() -> None:
    rows = [{"ts": i, "pred": 0.5, "label": i % 2} for i in range(20)]
    result = base_rate_drift(rows, n_windows=2)

    assert len(result["windows"]) == 2
    for window in result["windows"]:
        assert "base_rate" in window
        assert "mean_pred" in window
        assert "brier" in window
        assert "sample_size" in window


def test_base_rate_drift_validates_inputs() -> None:
    with pytest.raises(ValueError):
        base_rate_drift([])

    with pytest.raises(ValueError):
        base_rate_drift([{"ts": 1, "pred": 0.5, "label": 0}], n_windows=1)


# --- recalibrate_predictions ---


def test_recalibrate_returns_original_when_no_recent_base_rate() -> None:
    preds = [0.3, 0.5, 0.7]
    labels = [0, 1, 1]

    result = recalibrate_predictions(preds, labels)
    assert result == pytest.approx(preds, abs=1e-12)


def test_recalibrate_returns_original_when_insufficient_recent_n() -> None:
    preds = [0.3, 0.5, 0.7]
    labels = [0, 1, 1]

    result = recalibrate_predictions(preds, labels, recent_base_rate=0.8, recent_n=5)
    assert result == pytest.approx(preds, abs=1e-12)


def test_recalibrate_shifts_predictions_toward_recent_base_rate() -> None:
    # Overall base rate: 0.5, recent base rate: 0.8
    # Predictions should shift upward
    preds = [0.3, 0.5, 0.7]
    labels = [0, 0, 1, 1, 0, 0, 1, 1, 0, 1]  # 5/10 = 0.5 base rate
    padded_preds = [0.5] * 7 + preds

    result = recalibrate_predictions(padded_preds, labels, recent_base_rate=0.8, recent_n=20)

    # All predictions should shift upward
    for orig, recal in zip(padded_preds, result):
        assert recal > orig


def test_recalibrate_preserves_ordering() -> None:
    preds = [0.1, 0.3, 0.5, 0.7, 0.9]
    labels = [0, 0, 1, 1, 1, 0, 0, 1, 1, 1]
    padded_preds = [0.5] * 5 + preds

    result = recalibrate_predictions(padded_preds, labels, recent_base_rate=0.7, recent_n=30)

    # Ordering must be preserved
    recal_tail = result[-5:]
    for j in range(len(recal_tail) - 1):
        assert recal_tail[j] < recal_tail[j + 1]
