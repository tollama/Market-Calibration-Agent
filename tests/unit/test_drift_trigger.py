from __future__ import annotations

import pytest

from calibration.drift import (
    DEFAULT_COVERAGE_TOLERANCE,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_TARGET_COVERAGE,
    DEFAULT_WIDTH_EXPANSION_THRESHOLD,
    REASON_INSUFFICIENT_SAMPLES,
    REASON_LOW_COVERAGE,
    REASON_WIDTH_EXPANSION,
    evaluate_retraining_need,
)


def test_defaults_are_stable() -> None:
    assert DEFAULT_TARGET_COVERAGE == 0.80
    assert DEFAULT_MIN_SAMPLES == 200
    assert DEFAULT_COVERAGE_TOLERANCE == 0.05
    assert DEFAULT_WIDTH_EXPANSION_THRESHOLD == 1.5


def test_retrain_triggers_on_low_coverage_with_sample_floor_met() -> None:
    current_report = {
        "samples": 250,
        "empirical_coverage": 0.70,
        "mean_interval_width": 0.12,
    }

    result = evaluate_retraining_need(current_report)

    assert result["should_retrain"] is True
    assert result["reason_codes"] == [REASON_LOW_COVERAGE]
    diagnostics = result["diagnostics"]
    assert diagnostics["sample_floor_met"] is True
    assert diagnostics["low_coverage"] is True
    assert diagnostics["coverage_floor"] == pytest.approx(0.75, rel=0.0, abs=1e-12)
    assert diagnostics["width_expansion"] is False
    assert diagnostics["width_expansion_ratio"] is None


def test_retrain_triggers_on_width_expansion_against_baseline() -> None:
    current_report = {
        "samples": 260,
        "empirical_coverage": 0.84,
        "mean_interval_width": 0.30,
    }
    baseline_report = {
        "samples": 300,
        "empirical_coverage": 0.83,
        "mean_interval_width": 0.15,
    }

    result = evaluate_retraining_need(current_report, baseline_report)

    assert result["should_retrain"] is True
    assert result["reason_codes"] == [REASON_WIDTH_EXPANSION]
    diagnostics = result["diagnostics"]
    assert diagnostics["low_coverage"] is False
    assert diagnostics["width_expansion"] is True
    assert diagnostics["width_expansion_ratio"] == pytest.approx(
        2.0, rel=0.0, abs=1e-12
    )


def test_no_retrain_when_metrics_within_thresholds() -> None:
    current_report = {
        "samples": 280,
        "empirical_coverage": 0.79,
        "mean_interval_width": 0.18,
    }
    baseline_report = {
        "samples": 320,
        "empirical_coverage": 0.81,
        "mean_interval_width": 0.15,
    }

    result = evaluate_retraining_need(current_report, baseline_report)

    assert result["should_retrain"] is False
    assert result["reason_codes"] == []
    diagnostics = result["diagnostics"]
    assert diagnostics["sample_floor_met"] is True
    assert diagnostics["low_coverage"] is False
    assert diagnostics["width_expansion"] is False
    assert diagnostics["width_expansion_ratio"] == pytest.approx(
        1.2, rel=0.0, abs=1e-12
    )


def test_sample_floor_blocks_retraining_even_when_drift_triggers() -> None:
    current_report = {
        "samples": 120,
        "empirical_coverage": 0.60,
        "mean_interval_width": 0.45,
    }
    baseline_report = {
        "samples": 320,
        "empirical_coverage": 0.82,
        "mean_interval_width": 0.20,
    }

    result = evaluate_retraining_need(current_report, baseline_report)

    assert result["should_retrain"] is False
    assert result["reason_codes"] == [
        REASON_LOW_COVERAGE,
        REASON_WIDTH_EXPANSION,
        REASON_INSUFFICIENT_SAMPLES,
    ]
    diagnostics = result["diagnostics"]
    assert diagnostics["sample_floor_met"] is False
