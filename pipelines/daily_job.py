"""Daily pipeline orchestrator skeleton."""

from __future__ import annotations

from typing import Any, Optional

from .build_cutoff_snapshots import stage_build_cutoff_snapshots
from .common import (
    PipelineRunContext,
    PipelineStage,
    generate_run_id,
    run_stages,
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (set, tuple, frozenset)):
        return list(value)
    return [value]


def _count_items(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _fallback_stage_build_features(context: PipelineRunContext) -> dict[str, Any]:
    feature_rows = context.state.setdefault("feature_rows", [])
    market_count = _count_items(_as_list(context.state.get("market_ids")))
    return {
        "stage": "features",
        "status": "no-op",
        "market_count": market_count,
        "feature_count": _count_items(feature_rows),
    }


try:
    from .build_feature_frame import stage_build_features
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.build_feature_frame", "build_feature_frame"}:
        raise
    stage_build_features = _fallback_stage_build_features


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
    if "market_ids" not in context.state:
        context.state["market_ids"] = []
    else:
        context.state["market_ids"] = _as_list(context.state["market_ids"])
    return {
        "stage": "discover",
        "market_count": _count_items(context.state["market_ids"]),
    }


def _stage_ingest(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("raw_records", [])
    return {
        "stage": "ingest",
        "market_count": _count_items(context.state.get("market_ids")),
        "raw_record_count": _count_items(context.state["raw_records"]),
    }


def _stage_normalize(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("normalized_records", [])
    return {
        "stage": "normalize",
        "raw_record_count": _count_items(context.state.get("raw_records")),
        "normalized_record_count": _count_items(context.state["normalized_records"]),
    }


def _stage_snapshots(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("snapshots", [])
    return {
        "stage": "snapshots",
        "normalized_record_count": _count_items(context.state.get("normalized_records")),
        "snapshot_count": _count_items(context.state["snapshots"]),
    }


def _stage_cutoff(context: PipelineRunContext) -> dict[str, Any]:
    output = dict(stage_build_cutoff_snapshots(context))
    output.setdefault("stage", "cutoff")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    output.setdefault("snapshot_count", _count_items(context.state.get("cutoff_snapshots")))
    return output


def _stage_features(context: PipelineRunContext) -> dict[str, Any]:
    output = dict(stage_build_features(context))
    output.setdefault("stage", "features")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    if "feature_count" not in output:
        feature_rows = context.state.get("features")
        if feature_rows is None:
            feature_rows = context.state.get("feature_rows")
        output["feature_count"] = _count_items(feature_rows)
    return output


def _stage_metrics(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("metrics", [])
    feature_rows = context.state.get("features")
    if feature_rows is None:
        feature_rows = context.state.get("feature_rows")
    return {
        "stage": "metrics",
        "feature_count": _count_items(feature_rows),
        "metric_count": _count_items(context.state["metrics"]),
    }


def _stage_publish(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("published_records", [])
    return {
        "stage": "publish",
        "metric_count": _count_items(context.state.get("metrics")),
        "published_count": _count_items(context.state["published_records"]),
    }


def build_daily_stages() -> list[PipelineStage]:
    """Return the canonical daily stage order."""

    return [
        PipelineStage(name="discover", handler=_stage_discover),
        PipelineStage(name="ingest", handler=_stage_ingest),
        PipelineStage(name="normalize", handler=_stage_normalize),
        PipelineStage(name="snapshots", handler=_stage_snapshots),
        PipelineStage(name="cutoff", handler=_stage_cutoff),
        PipelineStage(name="features", handler=_stage_features),
        PipelineStage(name="metrics", handler=_stage_metrics),
        PipelineStage(name="publish", handler=_stage_publish),
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
