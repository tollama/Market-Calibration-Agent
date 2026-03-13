"""Tests for Prometheus calibration gauges in TSFMMetricsEmitter."""

from __future__ import annotations

import pytest

from runners.tsfm_observability import TSFMMetricsEmitter


class TestCalibrationGauges:
    """Verify calibration-quality gauge registration and rendering."""

    def test_update_calibration_gauges_sets_values(self) -> None:
        emitter = TSFMMetricsEmitter()
        emitter.update_calibration_gauges(
            brier=0.15,
            ece=0.08,
            log_loss=0.45,
            conformal_coverage=0.82,
            conformal_width=0.35,
            drift_detected=True,
            low_confidence_market_count=3,
            total_market_count=50,
        )

        rendered = emitter.render_prometheus()
        assert "calibration_brier_score" in rendered
        assert "calibration_ece" in rendered
        assert "calibration_log_loss" in rendered
        assert "calibration_conformal_coverage" in rendered
        assert "calibration_conformal_width" in rendered
        assert "calibration_drift_detected" in rendered
        assert "calibration_low_confidence_markets" in rendered
        assert "calibration_total_markets" in rendered

    def test_calibration_gauges_type_declarations(self) -> None:
        emitter = TSFMMetricsEmitter()
        rendered = emitter.render_prometheus()
        assert "# TYPE calibration_brier_score gauge" in rendered
        assert "# TYPE calibration_ece gauge" in rendered
        assert "# TYPE calibration_conformal_coverage gauge" in rendered
        assert "# TYPE calibration_drift_detected gauge" in rendered

    def test_drift_detected_true_renders_as_1(self) -> None:
        emitter = TSFMMetricsEmitter()
        emitter.update_calibration_gauges(drift_detected=True)
        rendered = emitter.render_prometheus()
        assert "calibration_drift_detected 1.0" in rendered

    def test_drift_detected_false_renders_as_0(self) -> None:
        emitter = TSFMMetricsEmitter()
        emitter.update_calibration_gauges(drift_detected=False)
        rendered = emitter.render_prometheus()
        assert "calibration_drift_detected 0.0" in rendered

    def test_partial_gauge_update(self) -> None:
        """Updating only some gauges should not affect others."""
        emitter = TSFMMetricsEmitter()
        emitter.update_calibration_gauges(brier=0.20)
        rendered = emitter.render_prometheus()
        assert "calibration_brier_score 0.2" in rendered
        # Other gauges should not appear as data lines (only type declarations)
        lines = [l for l in rendered.split("\n") if l.startswith("calibration_ece ")]
        assert len(lines) == 0

    def test_gauge_update_overwrites_previous(self) -> None:
        emitter = TSFMMetricsEmitter()
        emitter.update_calibration_gauges(brier=0.10)
        emitter.update_calibration_gauges(brier=0.25)
        rendered = emitter.render_prometheus()
        assert "calibration_brier_score 0.25" in rendered
        # Should not contain the old value as a separate line
        lines = [l for l in rendered.split("\n") if l.startswith("calibration_brier_score ")]
        assert len(lines) == 1
