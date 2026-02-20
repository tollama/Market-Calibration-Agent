"""Common helpers for minimal pipeline orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

StageName = Literal[
    "discover",
    "ingest",
    "normalize",
    "snapshots",
    "cutoff",
    "features",
    "metrics",
    "publish",
]
StageStatus = Literal["success", "failed"]
StageHandler = Callable[["PipelineRunContext"], dict[str, Any]]


@dataclass
class PipelineRunContext:
    """Execution context shared across stage handlers."""

    run_id: str
    data_interval_start: Optional[str] = None
    data_interval_end: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStage:
    """A single named pipeline stage."""

    name: StageName
    handler: StageHandler


@dataclass
class StageResult:
    """Structured result for a single stage execution."""

    name: StageName
    status: StageStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Pipeline run summary."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    stages: list[StageResult]

    @property
    def success(self) -> bool:
        return all(stage.status == "success" for stage in self.stages)


def generate_run_id(prefix: str = "daily") -> str:
    """Generate a deterministic-looking timestamped run id."""

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}"


def save_checkpoint(path: str, payload: dict[str, Any]) -> None:
    """Persist a checkpoint payload as JSON."""

    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)


def load_checkpoint(path: str) -> dict[str, Any]:
    """Load a checkpoint payload from disk if it exists."""

    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {}

    try:
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}
    return payload


def run_stages(
    *,
    context: PipelineRunContext,
    stages: Iterable[PipelineStage],
) -> PipelineResult:
    """Run stages in order and stop on the first failure."""

    results: list[StageResult] = []
    for stage in stages:
        try:
            output = stage.handler(context)
            results.append(StageResult(name=stage.name, status="success", output=output))
        except Exception as exc:  # pragma: no cover - defensive skeleton behavior
            results.append(
                StageResult(name=stage.name, status="failed", output={}, error=str(exc))
            )
            break

    return PipelineResult(
        run_id=context.run_id,
        started_at=context.started_at,
        finished_at=datetime.now(timezone.utc),
        stages=results,
    )


def no_op_stage(context: PipelineRunContext) -> dict[str, Any]:
    """Default no-op stage implementation for skeleton orchestration."""

    return {"run_id": context.run_id, "status": "no-op"}
