"""Daily pipeline orchestrator skeleton."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .build_cutoff_snapshots import stage_build_cutoff_snapshots
from .common import (
    PipelineResult,
    PipelineRunContext,
    PipelineStage,
    StageResult,
    generate_run_id,
    load_checkpoint,
    save_checkpoint,
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


def _resolve_stage_hook(context: PipelineRunContext, key: str) -> Any:
    hook = context.state.get(key)
    if callable(hook):
        return hook
    return None


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
    hook = _resolve_stage_hook(context, "ingest_fn")
    if hook is None:
        context.state.setdefault("raw_records", [])
        output = {}
    else:
        output = dict(hook(context))
    output.setdefault("stage", "ingest")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    output.setdefault("raw_record_count", _count_items(context.state.get("raw_records")))
    return output


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
    hook = _resolve_stage_hook(context, "cutoff_fn")
    handler = hook if hook is not None else stage_build_cutoff_snapshots
    output = dict(handler(context))
    output.setdefault("stage", "cutoff")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    output.setdefault("snapshot_count", _count_items(context.state.get("cutoff_snapshots")))
    return output


def _stage_features(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "feature_fn")
    handler = hook if hook is not None else stage_build_features
    output = dict(handler(context))
    output.setdefault("stage", "features")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    if "feature_count" not in output:
        feature_rows = context.state.get("features")
        if feature_rows is None:
            feature_rows = context.state.get("feature_rows")
        output["feature_count"] = _count_items(feature_rows)
    return output


def _stage_metrics(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "metric_fn")
    if hook is None:
        context.state.setdefault("metrics", [])
        output = {}
    else:
        output = dict(hook(context))
    feature_rows = context.state.get("features")
    if feature_rows is None:
        feature_rows = context.state.get("feature_rows")
    output.setdefault("stage", "metrics")
    output.setdefault("feature_count", _count_items(feature_rows))
    output.setdefault("metric_count", _count_items(context.state.get("metrics")))
    return output


def _stage_publish(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "publish_fn")
    if hook is None:
        context.state.setdefault("published_records", [])
        output = {}
    else:
        output = dict(hook(context))
    output.setdefault("stage", "publish")
    output.setdefault("metric_count", _count_items(context.state.get("metrics")))
    output.setdefault("published_count", _count_items(context.state.get("published_records")))
    return output


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


def _checkpoint_stage_payload(
    *,
    context: PipelineRunContext,
    stage_results: list[StageResult],
    backfill_days: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": context.run_id,
        "stages": {
            stage.name: {
                "status": stage.status,
                "output": stage.output,
                "error": stage.error,
            }
            for stage in stage_results
        },
    }
    if context.data_interval_start is not None:
        payload["data_interval_start"] = context.data_interval_start
    if context.data_interval_end is not None:
        payload["data_interval_end"] = context.data_interval_end
    if backfill_days > 0:
        payload["backfill_days"] = backfill_days
    return payload


def _checkpoint_stage_lookup(path: str | None, resume_from_checkpoint: bool) -> dict[str, dict[str, Any]]:
    if path is None or not resume_from_checkpoint:
        return {}

    payload = load_checkpoint(path)
    raw_stages = payload.get("stages")
    if not isinstance(raw_stages, dict):
        return {}

    stages: dict[str, dict[str, Any]] = {}
    for stage_name, stage_payload in raw_stages.items():
        if not isinstance(stage_name, str):
            continue
        if not isinstance(stage_payload, dict):
            continue
        output = stage_payload.get("output")
        stages[stage_name] = {
            "status": stage_payload.get("status"),
            "output": dict(output) if isinstance(output, dict) else {},
            "error": stage_payload.get("error"),
        }
    return stages


def _run_daily_stages(
    *,
    context: PipelineRunContext,
    checkpoint_path: str | None,
    resume_from_checkpoint: bool,
    backfill_days: int,
) -> PipelineResult:
    checkpoint_stages = _checkpoint_stage_lookup(checkpoint_path, resume_from_checkpoint)
    stage_results: list[StageResult] = []

    for stage in build_daily_stages():
        checkpoint_stage = checkpoint_stages.get(stage.name)
        if (
            checkpoint_stage is not None
            and resume_from_checkpoint
            and checkpoint_stage.get("status") == "success"
        ):
            stage_results.append(
                StageResult(
                    name=stage.name,
                    status="success",
                    output=checkpoint_stage.get("output", {}),
                    error=None,
                )
            )
            continue

        try:
            output = stage.handler(context)
            stage_result = StageResult(name=stage.name, status="success", output=output)
        except Exception as exc:  # pragma: no cover - defensive skeleton behavior
            stage_result = StageResult(
                name=stage.name,
                status="failed",
                output={},
                error=str(exc),
            )
            stage_results.append(stage_result)
            if checkpoint_path is not None:
                save_checkpoint(
                    checkpoint_path,
                    _checkpoint_stage_payload(
                        context=context,
                        stage_results=stage_results,
                        backfill_days=backfill_days,
                    ),
                )
            break

        stage_results.append(stage_result)
        if checkpoint_path is not None:
            save_checkpoint(
                checkpoint_path,
                _checkpoint_stage_payload(
                    context=context,
                    stage_results=stage_results,
                    backfill_days=backfill_days,
                ),
            )

    return PipelineResult(
        run_id=context.run_id,
        started_at=context.started_at,
        finished_at=datetime.now(timezone.utc),
        stages=stage_results,
    )


def run_daily_job(
    *,
    run_id: Optional[str] = None,
    data_interval_start: Optional[str] = None,
    data_interval_end: Optional[str] = None,
    checkpoint_path: str | None = None,
    resume_from_checkpoint: bool = False,
    backfill_days: int = 0,
) -> dict[str, Any]:
    """Execute the minimal daily orchestrator skeleton."""

    context = PipelineRunContext(
        run_id=run_id or generate_run_id(prefix="daily"),
        data_interval_start=data_interval_start,
        data_interval_end=data_interval_end,
    )
    if backfill_days > 0:
        context.state["backfill_days"] = backfill_days

    result = _run_daily_stages(
        context=context,
        checkpoint_path=checkpoint_path,
        resume_from_checkpoint=resume_from_checkpoint,
        backfill_days=backfill_days,
    )
    payload = {
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
    if checkpoint_path is not None:
        payload["checkpoint_path"] = checkpoint_path
    if resume_from_checkpoint:
        payload["resume_from_checkpoint"] = True
    if backfill_days > 0:
        payload["backfill_days"] = backfill_days
    return payload
