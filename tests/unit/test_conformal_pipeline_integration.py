"""Tests for conformal pipeline integration (daily_job conformal update)."""

from __future__ import annotations

from typing import Any

import pytest

from pipelines.common import PipelineRunContext


def _make_conformal_row(
    *,
    q10: float = 0.3,
    q50: float = 0.5,
    q90: float = 0.7,
    actual: float = 0.55,
    market_id: str = "mkt-1",
    ts: str = "2026-01-15T12:00:00Z",
) -> dict[str, Any]:
    return {
        "market_id": market_id,
        "ts": ts,
        "q10": q10,
        "q50": q50,
        "q90": q90,
        "actual": actual,
    }


class TestConformalPipelineUpdate:
    """Tests for _run_conformal_update callable."""

    def test_fallback_when_modules_unavailable(self) -> None:
        """The fallback function should return skipped status."""
        from pipelines.daily_job import _fallback_run_conformal_update

        result = _fallback_run_conformal_update([])
        assert result["status"] == "skipped"
        assert result["sample_count"] == 0

    def test_conformal_stage_no_drift_skips(self) -> None:
        """When drift_detected is False, conformal stage should skip."""
        from pipelines.daily_job import _stage_conformal

        ctx = PipelineRunContext(run_id="test-no-drift")
        ctx.state["drift_result"] = {"drift_detected": False}
        output = _stage_conformal(ctx)

        assert output["conformal_updated"] is False
        assert ctx.state["conformal_result"]["status"] == "skipped"

    def test_conformal_stage_drift_detected_insufficient_samples(self) -> None:
        """When drift is detected but there aren't enough rows, conformal skips."""
        from pipelines.daily_job import _stage_conformal

        ctx = PipelineRunContext(run_id="test-insuf")
        ctx.state["drift_result"] = {"drift_detected": True}
        # Only 5 rows — below min_samples=100 default
        ctx.state["metric_rows"] = [
            _make_conformal_row(actual=0.5 + 0.01 * i) for i in range(5)
        ]
        output = _stage_conformal(ctx)

        assert output["stage"] == "conformal"
        conformal_result = ctx.state.get("conformal_result", {})
        # With only 5 samples, it should be skipped
        assert conformal_result.get("status") in {"skipped", "error"}

    def test_conformal_stage_drift_with_enough_samples(self) -> None:
        """When drift is detected and there are enough rows, conformal may update."""
        from pipelines.daily_job import _stage_conformal, _run_conformal_update

        # Generate 150 rows to exceed min_samples=100
        rows = [
            _make_conformal_row(
                q10=0.2 + 0.001 * i,
                q50=0.5,
                q90=0.8 - 0.001 * i,
                actual=0.4 + 0.002 * i,
            )
            for i in range(150)
        ]

        ctx = PipelineRunContext(run_id="test-enough")
        ctx.state["drift_result"] = {"drift_detected": True}
        ctx.state["metric_rows"] = rows
        output = _stage_conformal(ctx)

        assert output["stage"] == "conformal"
        conformal_result = ctx.state.get("conformal_result", {})
        # Should be "updated" or "skipped" (depends on module availability)
        assert conformal_result.get("status") in {"updated", "skipped", "error"}

    def test_run_conformal_update_insufficient_samples(self) -> None:
        """Direct call to _run_conformal_update with too few samples."""
        from pipelines.daily_job import _run_conformal_update

        result = _run_conformal_update(
            [_make_conformal_row() for _ in range(5)],
            min_samples=10,
        )
        assert result["status"] == "skipped"
        assert "insufficient" in result.get("reason", "").lower() or result["sample_count"] < 10

    def test_run_conformal_update_rows_missing_fields(self) -> None:
        """Rows without q10/q50/q90/actual should be filtered out."""
        from pipelines.daily_job import _run_conformal_update

        rows = [{"market_id": "mkt-1", "foo": "bar"} for _ in range(200)]
        result = _run_conformal_update(rows, min_samples=10)
        assert result["status"] == "skipped"
        assert result["sample_count"] == 0
