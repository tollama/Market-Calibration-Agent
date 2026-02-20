"""Daily pipeline orchestrator skeleton."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .build_cutoff_snapshots import build_cutoff_snapshots, stage_build_cutoff_snapshots
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


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_stage_hook(context: PipelineRunContext, key: str) -> Any:
    hook = context.state.get(key)
    if callable(hook):
        return hook
    return None


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if isinstance(row, Mapping):
        return dict(row)

    if is_dataclass(row) and not isinstance(row, type):
        return asdict(row)

    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)

    attributes = getattr(row, "__dict__", None)
    if isinstance(attributes, dict):
        return {key: value for key, value in attributes.items() if not key.startswith("_")}
    return None


def _rows_to_dicts(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
        except TypeError:
            try:
                records = to_dict()
            except Exception:  # pragma: no cover - defensive conversion fallback
                records = None
        except Exception:  # pragma: no cover - defensive conversion fallback
            records = None
        if isinstance(records, list):
            return [row for row in (_row_to_dict(item) for item in records) if row is not None]

    if isinstance(value, Mapping):
        row = _row_to_dict(value)
        return [row] if row is not None else []

    if isinstance(value, (list, tuple, set, frozenset)):
        return [row for row in (_row_to_dict(item) for item in value) if row is not None]

    row = _row_to_dict(value)
    return [row] if row is not None else []


def _normalize_market_ids(value: Any) -> list[str]:
    market_ids: list[str] = []
    seen: set[str] = set()
    for raw_market_id in _as_list(value):
        market_id = str(raw_market_id).strip()
        if not market_id or market_id in seen:
            continue
        market_ids.append(market_id)
        seen.add(market_id)
    return market_ids


def _infer_market_ids(rows: Any) -> list[str]:
    return _normalize_market_ids([row.get("market_id") for row in _rows_to_dicts(rows)])


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


def _fallback_link_registry_to_snapshots(
    snapshot_rows: list[dict[str, Any]],
    registry_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    _ = registry_rows
    return list(snapshot_rows)


try:
    from .registry_linker import link_registry_to_snapshots
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.registry_linker", "registry_linker"}:
        raise
    link_registry_to_snapshots = _fallback_link_registry_to_snapshots


def _fallback_build_scoreboard_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _ = rows
    return [], {}


try:
    from .build_scoreboard_artifacts import build_scoreboard_rows
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.build_scoreboard_artifacts", "build_scoreboard_artifacts"}:
        raise
    build_scoreboard_rows = _fallback_build_scoreboard_rows


def _fallback_build_alert_feed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _ = rows
    return []


try:
    from .build_alert_feed import build_alert_feed_rows
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.build_alert_feed", "build_alert_feed"}:
        raise
    build_alert_feed_rows = _fallback_build_alert_feed_rows


def _fallback_load_trust_weights(config_path: str | None = None) -> Mapping[str, object] | None:
    _ = config_path
    return None


try:
    from .trust_policy_loader import load_trust_weights
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.trust_policy_loader", "trust_policy_loader"}:
        raise
    load_trust_weights = _fallback_load_trust_weights


def _fallback_load_alert_thresholds(config_path: str | None = None) -> Any:
    _ = config_path
    return None


def _fallback_load_alert_min_trust_score(config_path: str | None = None) -> float | None:
    _ = config_path
    return None


try:
    from .alert_policy_loader import load_alert_min_trust_score, load_alert_thresholds
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.alert_policy_loader", "alert_policy_loader"}:
        raise
    load_alert_thresholds = _fallback_load_alert_thresholds
    load_alert_min_trust_score = _fallback_load_alert_min_trust_score


def _load_policy_with_optional_path(loader: Any, config_path: str | None) -> Any:
    if not callable(loader):
        return None
    try:
        return loader(config_path)
    except TypeError:
        return loader()


def _fallback_build_and_write_postmortems(
    events: list[dict[str, Any]],
    *,
    root: str,
) -> dict[str, Any]:
    _ = root
    return {
        "written_count": 0,
        "skipped_count": _count_items(events),
        "output_paths": [],
    }


try:
    from .build_postmortem_batch import build_and_write_postmortems
except ModuleNotFoundError as exc:
    if exc.name not in {"pipelines.build_postmortem_batch", "build_postmortem_batch"}:
        raise
    build_and_write_postmortems = _fallback_build_and_write_postmortems


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
    context.state["market_ids"] = _normalize_market_ids(context.state.get("market_ids"))
    return {
        "stage": "discover",
        "market_count": _count_items(context.state["market_ids"]),
    }


def _stage_ingest(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "ingest_fn")
    if hook is None:
        raw_records = context.state.get("raw_records")
        if raw_records is None:
            raw_records = context.state.get("ingest_rows")
        if raw_records is None:
            raw_records = context.state.get("gamma_markets")
        normalized_raw_records = _rows_to_dicts(raw_records)
        if normalized_raw_records:
            context.state["raw_records"] = normalized_raw_records
        else:
            context.state.setdefault("raw_records", [])

        events = context.state.get("events")
        if events is None:
            events = context.state.get("event_rows")
        if events is None:
            events = context.state.get("gamma_events")
        if events is not None:
            context.state["events"] = _rows_to_dicts(events)

        if _count_items(context.state.get("market_ids")) == 0:
            inferred_market_ids = _infer_market_ids(context.state.get("raw_records"))
            if inferred_market_ids:
                context.state["market_ids"] = inferred_market_ids
        output = {}
    else:
        output = dict(hook(context))
    output.setdefault("stage", "ingest")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    output.setdefault("raw_record_count", _count_items(context.state.get("raw_records")))
    output.setdefault("event_count", _count_items(context.state.get("events")))
    return output


def _stage_normalize(context: PipelineRunContext) -> dict[str, Any]:
    normalized_records = context.state.get("normalized_records")
    if normalized_records is None:
        normalized_records = _rows_to_dicts(context.state.get("raw_records"))
    else:
        normalized_records = _rows_to_dicts(normalized_records)
    context.state["normalized_records"] = normalized_records

    if _count_items(context.state.get("market_ids")) == 0:
        inferred_market_ids = _infer_market_ids(normalized_records)
        if inferred_market_ids:
            context.state["market_ids"] = inferred_market_ids
    return {
        "stage": "normalize",
        "raw_record_count": _count_items(context.state.get("raw_records")),
        "normalized_record_count": _count_items(normalized_records),
    }


def _stage_snapshots(context: PipelineRunContext) -> dict[str, Any]:
    snapshot_rows = _rows_to_dicts(context.state.get("snapshots"))
    if not snapshot_rows:
        snapshot_rows = _rows_to_dicts(context.state.get("normalized_records"))

    registry_rows = _rows_to_dicts(context.state.get("registry_rows"))
    enriched_snapshot_rows = snapshot_rows
    if snapshot_rows and registry_rows:
        try:
            enriched_snapshot_rows = _rows_to_dicts(
                link_registry_to_snapshots(snapshot_rows, registry_rows)
            )
        except Exception:  # pragma: no cover - optional integration fallback
            enriched_snapshot_rows = snapshot_rows

    context.state["snapshots"] = enriched_snapshot_rows
    return {
        "stage": "snapshots",
        "normalized_record_count": _count_items(context.state.get("normalized_records")),
        "registry_row_count": _count_items(registry_rows),
        "snapshot_count": _count_items(enriched_snapshot_rows),
    }


def _stage_cutoff(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "cutoff_fn")
    source_snapshot_rows = _rows_to_dicts(context.state.get("snapshots"))
    market_ids = _normalize_market_ids(context.state.get("market_ids"))
    if not market_ids:
        market_ids = _infer_market_ids(source_snapshot_rows)
        if market_ids:
            context.state["market_ids"] = market_ids

    if hook is not None:
        output = dict(hook(context))
    elif source_snapshot_rows:
        try:
            cutoff_snapshots = build_cutoff_snapshots(
                market_ids=market_ids,
                source_rows=source_snapshot_rows,
            )
            context.state["cutoff_snapshots"] = cutoff_snapshots
            context.state["cutoff_snapshot_rows"] = _rows_to_dicts(cutoff_snapshots)
            output = {"source_snapshot_count": _count_items(source_snapshot_rows)}
        except Exception:  # pragma: no cover - optional integration fallback
            output = dict(stage_build_cutoff_snapshots(context))
    else:
        output = dict(stage_build_cutoff_snapshots(context))

    if "cutoff_snapshot_rows" not in context.state:
        context.state["cutoff_snapshot_rows"] = _rows_to_dicts(context.state.get("cutoff_snapshots"))

    output.setdefault("stage", "cutoff")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    output.setdefault("source_snapshot_count", _count_items(source_snapshot_rows))
    output.setdefault("snapshot_count", _count_items(context.state.get("cutoff_snapshots")))
    return output


def _stage_features(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "feature_fn")
    handler = hook if hook is not None else stage_build_features
    output = dict(handler(context))

    feature_rows = context.state.get("features")
    if feature_rows is None:
        feature_rows = context.state.get("feature_rows")
    if feature_rows is None:
        feature_rows = _rows_to_dicts(context.state.get("feature_frame"))
        if feature_rows:
            context.state["feature_rows"] = feature_rows

    if feature_rows is None:
        feature_rows = []
    else:
        feature_rows = _rows_to_dicts(feature_rows)
        if "feature_rows" not in context.state:
            context.state["feature_rows"] = feature_rows
    if "features" not in context.state:
        context.state["features"] = feature_rows

    output.setdefault("stage", "features")
    output.setdefault("market_count", _count_items(context.state.get("market_ids")))
    if "feature_count" not in output:
        output["feature_count"] = _count_items(feature_rows)
    return output


def _stage_metrics(context: PipelineRunContext) -> dict[str, Any]:
    context.state.setdefault("trust_policy_loaded", False)
    context.state.setdefault("alert_policy_loaded", False)
    hook = _resolve_stage_hook(context, "metric_fn")
    if hook is None:
        metric_source_rows = _rows_to_dicts(context.state.get("metric_rows"))
        if not metric_source_rows:
            feature_rows = context.state.get("features")
            if feature_rows is None:
                feature_rows = context.state.get("feature_rows")
            if feature_rows is None:
                feature_rows = _rows_to_dicts(context.state.get("feature_frame"))
                if feature_rows:
                    context.state["feature_rows"] = feature_rows
            metric_source_rows = _rows_to_dicts(feature_rows)

        trust_config_path_raw = context.state.get("trust_config_path")
        trust_config_path = (
            str(trust_config_path_raw) if trust_config_path_raw is not None else None
        )
        trust_weights: Any = None
        trust_policy_loaded = False
        try:
            trust_weights = _load_policy_with_optional_path(load_trust_weights, trust_config_path)
            trust_policy_loaded = trust_weights is not None
        except Exception:  # pragma: no cover - optional integration fallback
            trust_weights = None
            trust_policy_loaded = False
        context.state["trust_policy_loaded"] = trust_policy_loaded

        alert_config_path_raw = context.state.get("alert_config_path")
        alert_config_path = (
            str(alert_config_path_raw) if alert_config_path_raw is not None else None
        )
        thresholds: Any = None
        min_trust_score: float | None = None
        try:
            thresholds = _load_policy_with_optional_path(
                load_alert_thresholds,
                alert_config_path,
            )
        except Exception:  # pragma: no cover - optional integration fallback
            thresholds = None
        try:
            min_trust_score = _load_policy_with_optional_path(
                load_alert_min_trust_score,
                alert_config_path,
            )
        except Exception:  # pragma: no cover - optional integration fallback
            min_trust_score = None
        context.state["alert_policy_loaded"] = (
            thresholds is not None or min_trust_score is not None
        )

        scoreboard_rows: list[dict[str, Any]] = []
        summary_metrics: dict[str, Any] = {}
        if metric_source_rows:
            try:
                try:
                    raw_scoreboard_rows, raw_summary_metrics = build_scoreboard_rows(
                        metric_source_rows,
                        trust_weights=trust_weights,
                    )
                except TypeError:
                    raw_scoreboard_rows, raw_summary_metrics = build_scoreboard_rows(
                        metric_source_rows
                    )
                scoreboard_rows = _rows_to_dicts(raw_scoreboard_rows)
                if isinstance(raw_summary_metrics, Mapping):
                    summary_metrics = dict(raw_summary_metrics)
            except Exception:  # pragma: no cover - optional integration fallback
                scoreboard_rows = []
                summary_metrics = {}
        context.state["scoreboard_rows"] = scoreboard_rows
        context.state["summary_metrics"] = summary_metrics

        alert_feed_rows: list[dict[str, Any]] = []
        if metric_source_rows:
            try:
                try:
                    raw_alert_feed_rows = build_alert_feed_rows(
                        metric_source_rows,
                        thresholds=thresholds,
                        min_trust_score=min_trust_score,
                    )
                except TypeError:
                    raw_alert_feed_rows = build_alert_feed_rows(metric_source_rows)
                alert_feed_rows = _rows_to_dicts(raw_alert_feed_rows)
            except Exception:  # pragma: no cover - optional integration fallback
                alert_feed_rows = []
        context.state["alert_feed_rows"] = alert_feed_rows

        if "metrics" not in context.state:
            context.state["metrics"] = scoreboard_rows
        output = {}
    else:
        output = dict(hook(context))

    feature_rows = context.state.get("features")
    if feature_rows is None:
        feature_rows = context.state.get("feature_rows")
    output.setdefault("stage", "metrics")
    output.setdefault("feature_count", _count_items(feature_rows))
    output.setdefault("metric_count", _count_items(context.state.get("metrics")))
    output.setdefault("scoreboard_count", _count_items(context.state.get("scoreboard_rows")))
    output.setdefault("alert_count", _count_items(context.state.get("alert_feed_rows")))
    output.setdefault("trust_policy_loaded", bool(context.state.get("trust_policy_loaded")))
    output.setdefault("alert_policy_loaded", bool(context.state.get("alert_policy_loaded")))
    return output


def _stage_publish(context: PipelineRunContext) -> dict[str, Any]:
    hook = _resolve_stage_hook(context, "publish_fn")
    if hook is None:
        if "published_records" not in context.state:
            published_records = _rows_to_dicts(context.state.get("metrics"))
            if not published_records:
                published_records = _rows_to_dicts(context.state.get("scoreboard_rows"))
            context.state["published_records"] = published_records

        events = context.state.get("events")
        if events is None:
            events = context.state.get("event_rows")
        postmortem_payload: dict[str, Any] | None = None
        event_rows = _rows_to_dicts(events)
        if event_rows:
            root = context.state.get("postmortem_root")
            if root is None:
                root = context.state.get("root_path")
            if root is None:
                root = "."
            try:
                maybe_postmortem_payload = build_and_write_postmortems(
                    event_rows,
                    root=str(root),
                )
                if isinstance(maybe_postmortem_payload, Mapping):
                    postmortem_payload = dict(maybe_postmortem_payload)
            except Exception:  # pragma: no cover - optional integration fallback
                postmortem_payload = _fallback_build_and_write_postmortems(
                    event_rows,
                    root=str(root),
                )
            if postmortem_payload is not None:
                context.state["postmortem_artifacts"] = postmortem_payload
        output = {}
    else:
        output = dict(hook(context))

    postmortem_artifacts = context.state.get("postmortem_artifacts")
    if isinstance(postmortem_artifacts, Mapping):
        postmortem_written_count = _to_int(postmortem_artifacts.get("written_count"))
        postmortem_skipped_count = _to_int(postmortem_artifacts.get("skipped_count"))
    else:
        postmortem_written_count = 0
        postmortem_skipped_count = 0

    output.setdefault("stage", "publish")
    output.setdefault("metric_count", _count_items(context.state.get("metrics")))
    output.setdefault("alert_count", _count_items(context.state.get("alert_feed_rows")))
    output.setdefault("postmortem_written_count", postmortem_written_count)
    output.setdefault("postmortem_skipped_count", postmortem_skipped_count)
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
    stage_retry_limit: int,
    continue_on_stage_failure: bool,
) -> PipelineResult:
    checkpoint_stages = _checkpoint_stage_lookup(checkpoint_path, resume_from_checkpoint)
    stage_results: list[StageResult] = []
    retry_limit = max(0, stage_retry_limit)

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

        stage_result: StageResult | None = None
        for attempt in range(retry_limit + 1):
            try:
                output = stage.handler(context)
                if attempt > 0:
                    if isinstance(output, Mapping):
                        output = dict(output)
                    else:
                        output = {}
                    output["retry_count"] = attempt
                stage_result = StageResult(name=stage.name, status="success", output=output)
                break
            except Exception as exc:  # pragma: no cover - defensive skeleton behavior
                if attempt < retry_limit:
                    continue
                failed_output: dict[str, Any] = {}
                if attempt > 0:
                    failed_output["retry_count"] = attempt
                stage_result = StageResult(
                    name=stage.name,
                    status="failed",
                    output=failed_output,
                    error=str(exc),
                )
                break

        if stage_result is None:  # pragma: no cover - defensive guard
            stage_result = StageResult(
                name=stage.name,
                status="failed",
                output={},
                error="stage execution did not produce a result",
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
        if stage_result.status == "failed" and not continue_on_stage_failure:
            break

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
    stage_retry_limit: int = 0,
    continue_on_stage_failure: bool = False,
    trust_config_path: str | None = None,
    alert_config_path: str | None = None,
) -> dict[str, Any]:
    """Execute the minimal daily orchestrator skeleton."""

    context = PipelineRunContext(
        run_id=run_id or generate_run_id(prefix="daily"),
        data_interval_start=data_interval_start,
        data_interval_end=data_interval_end,
    )
    context.state["trust_config_path"] = trust_config_path
    context.state["alert_config_path"] = alert_config_path
    if backfill_days > 0:
        context.state["backfill_days"] = backfill_days

    result = _run_daily_stages(
        context=context,
        checkpoint_path=checkpoint_path,
        resume_from_checkpoint=resume_from_checkpoint,
        backfill_days=backfill_days,
        stage_retry_limit=stage_retry_limit,
        continue_on_stage_failure=continue_on_stage_failure,
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
