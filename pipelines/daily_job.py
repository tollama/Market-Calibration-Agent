"""Daily pipeline orchestrator skeleton."""

from __future__ import annotations

from typing import Any, Optional

from .build_cutoff_snapshots import stage_build_cutoff_snapshots
from .common import (
    PipelineRunContext,
    PipelineStage,
    generate_run_id,
    no_op_stage,
    run_stages,
)

DAILY_STAGE_NAMES = (
    "discover",
    "ingest",
    "normalize",
    "snapshots",
    "cutoff",
    "features",
    "metrics",
    "publish",
)


def _stage_discover(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("market_ids", [])
    return {"stage": "discover", "market_count": len(context.state["market_ids"])}


def build_daily_stages() -> list[PipelineStage]:
    """Return the canonical daily stage order."""

    return [
        PipelineStage(name="discover", handler=_stage_discover),
        PipelineStage(name="ingest", handler=no_op_stage),
        PipelineStage(name="normalize", handler=no_op_stage),
        PipelineStage(name="snapshots", handler=no_op_stage),
        PipelineStage(name="cutoff", handler=stage_build_cutoff_snapshots),
        PipelineStage(name="features", handler=no_op_stage),
        PipelineStage(name="metrics", handler=no_op_stage),
        PipelineStage(name="publish", handler=no_op_stage),
    ]


def run_daily_job(
    *,
    run_id: Optional[str] = None,
    data_interval_start: Optional[str] = None,
    data_interval_end: Optional[str] = None,
) -> dict[str, Any]:
    """Execute the minimal daily orchestrator skeleton."""

    context = PipelineRunContext(
        run_id=run_id or generate_run_id(prefix="daily"),
        data_interval_start=data_interval_start,
        data_interval_end=data_interval_end,
    )
    result = run_stages(context=context, stages=build_daily_stages())
    return {
        "run_id": result.run_id,
        "success": result.success,
        "stage_order": [stage.name for stage in result.stages],
        "stages": [
            {
                "name": stage.name,
                "status": stage.status,
                "output": stage.output,
                "error": stage.error,
            }
            for stage in result.stages
        ],
    }
