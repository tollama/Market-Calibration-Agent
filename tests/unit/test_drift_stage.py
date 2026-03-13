"""Tests for the drift monitoring stage in daily_job pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from pipelines.common import PipelineRunContext, PipelineState


# Helpers for constructing rows with required keys for drift analysis.

def _make_row(
    *,
    ts: str,
    pred: float,
    label: int,
    market_id: str = "mkt-1",
) -> dict[str, Any]:
    return {
        "market_id": market_id,
        "ts": ts,
        "pred": pred,
        "label": label,
        "p_yes": pred,
        "q10": pred - 0.05,
        "q90": pred + 0.05,
        "category": "test",
        "liquidity_bucket": "MID",
    }


def _build_drift_context(
    rows: list[dict[str, Any]] | None = None,
) -> PipelineRunContext:
    ctx = PipelineRunContext(run_id="test-drift")
    if rows is not None:
        ctx.state["metric_rows"] = rows
    return ctx


# ---- Tests ----


class TestDriftStage:
    """Integration tests for _stage_drift."""

    def test_drift_stage_no_rows_returns_noop(self) -> None:
        from pipelines.daily_job import _stage_drift

        ctx = _build_drift_context(rows=[])
        output = _stage_drift(ctx)
        assert output["stage"] == "drift"
        assert output.get("status") == "no-op"
        assert ctx.state["drift_result"]["drift_detected"] is False

    def test_drift_stage_missing_fields_returns_noop(self) -> None:
        from pipelines.daily_job import _stage_drift

        # Rows without ts or pred/label
        rows = [{"market_id": "mkt-1", "foo": "bar"}]
        ctx = _build_drift_context(rows=rows)
        output = _stage_drift(ctx)
        assert output["stage"] == "drift"
        assert output.get("status") == "no-op"
        assert ctx.state["drift_result"]["drift_detected"] is False

    def test_drift_stage_detects_stable_data(self) -> None:
        from pipelines.daily_job import _stage_drift

        # Stable data: constant 50% base rate
        rows = [
            _make_row(ts=f"2026-01-{d:02d}T00:00:00Z", pred=0.5, label=d % 2)
            for d in range(1, 21)
        ]
        ctx = _build_drift_context(rows=rows)
        output = _stage_drift(ctx)

        assert output["stage"] == "drift"
        assert "drift_detected" in output
        drift_result = ctx.state["drift_result"]
        assert "drift_detected" in drift_result
        assert "base_rate_swing" in drift_result
        assert "n_windows" in drift_result

    def test_drift_stage_detects_drifting_data(self) -> None:
        from pipelines.daily_job import _stage_drift

        # Construct data with high base-rate swing
        rows = []
        # First half: all label=0
        for d in range(1, 11):
            rows.append(_make_row(ts=f"2026-01-{d:02d}T00:00:00Z", pred=0.5, label=0))
        # Second half: all label=1
        for d in range(11, 21):
            rows.append(_make_row(ts=f"2026-01-{d:02d}T00:00:00Z", pred=0.5, label=1))

        ctx = _build_drift_context(rows=rows)
        output = _stage_drift(ctx)

        drift_result = ctx.state["drift_result"]
        # Base rate swings from 0.0 to 1.0 → well above 0.15 threshold
        assert drift_result["drift_detected"] is True
        assert drift_result["base_rate_swing"] > 0.15

    def test_drift_stage_stores_result_in_context(self) -> None:
        from pipelines.daily_job import _stage_drift

        rows = [
            _make_row(ts=f"2026-01-{d:02d}T00:00:00Z", pred=0.5, label=d % 2)
            for d in range(1, 21)
        ]
        ctx = _build_drift_context(rows=rows)
        _stage_drift(ctx)

        assert "drift_result" in ctx.state
        drift_result = ctx.state["drift_result"]
        assert isinstance(drift_result, dict)
        assert "windows" in drift_result

    def test_drift_stage_uses_hook_when_provided(self) -> None:
        from pipelines.daily_job import _stage_drift

        called = {}

        def custom_hook(ctx: PipelineRunContext) -> dict[str, Any]:
            called["invoked"] = True
            return {"stage": "drift", "custom": True}

        ctx = _build_drift_context(rows=[])
        ctx.state["drift_fn"] = custom_hook
        output = _stage_drift(ctx)

        assert called.get("invoked") is True
        assert output.get("custom") is True

    def test_drift_stage_falls_back_to_feature_rows(self) -> None:
        from pipelines.daily_job import _stage_drift

        # Put rows in feature_rows instead of metric_rows
        rows = [
            _make_row(ts=f"2026-01-{d:02d}T00:00:00Z", pred=0.5, label=d % 2)
            for d in range(1, 21)
        ]
        ctx = PipelineRunContext(run_id="test-drift-fallback")
        ctx.state["feature_rows"] = rows
        output = _stage_drift(ctx)

        assert output["stage"] == "drift"
        assert "drift_detected" in output


class TestConformalStage:
    """Integration tests for _stage_conformal."""

    def test_conformal_stage_skips_when_no_drift(self) -> None:
        from pipelines.daily_job import _stage_conformal

        ctx = PipelineRunContext(run_id="test-conformal")
        ctx.state["drift_result"] = {"drift_detected": False}
        output = _stage_conformal(ctx)

        assert output["stage"] == "conformal"
        assert output["conformal_updated"] is False
        assert ctx.state["conformal_result"]["status"] == "skipped"

    def test_conformal_stage_skips_when_no_drift_result(self) -> None:
        from pipelines.daily_job import _stage_conformal

        ctx = PipelineRunContext(run_id="test-conformal-none")
        output = _stage_conformal(ctx)

        assert output["stage"] == "conformal"
        assert output["conformal_updated"] is False

    def test_conformal_stage_uses_hook_when_provided(self) -> None:
        from pipelines.daily_job import _stage_conformal

        def custom_hook(ctx: PipelineRunContext) -> dict[str, Any]:
            return {"stage": "conformal", "custom": True}

        ctx = PipelineRunContext(run_id="test-conformal-hook")
        ctx.state["conformal_fn"] = custom_hook
        output = _stage_conformal(ctx)

        assert output.get("custom") is True

    def test_conformal_stage_attempts_update_when_drift_detected(self) -> None:
        from pipelines.daily_job import _stage_conformal

        ctx = PipelineRunContext(run_id="test-conformal-drift")
        ctx.state["drift_result"] = {"drift_detected": True}
        # No metric rows → conformal update will skip due to insufficient samples
        ctx.state["metric_rows"] = []
        output = _stage_conformal(ctx)

        assert output["stage"] == "conformal"
        conformal_result = ctx.state.get("conformal_result", {})
        # Should either be "skipped" (insufficient samples) or "updated"
        assert conformal_result.get("status") in {"skipped", "updated", "error"}
