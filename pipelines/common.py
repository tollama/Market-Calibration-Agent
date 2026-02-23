"""Common helpers for minimal pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional

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
class PipelineState(MutableMapping[str, Any]):
    """Contract-backed dictionary for run state.

    The pipeline has become sensitive to a few shared state keys (for example,
    ``market_ids``). A dedicated mapping type keeps the contract explicit while
    still allowing dynamic keys used by tests and hooks.
    """

    _values: dict[str, Any] = field(default_factory=dict)
    market_ids: list[str] = field(default_factory=list)
    trust_policy_loaded: bool | None = None
    alert_policy_loaded: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self._values, dict):
            raise TypeError("PipelineState requires a mapping-backed initial state")

        for key in tuple(self._values):
            if not isinstance(key, str):
                raise TypeError("Pipeline state keys must be strings")

        sync_keys = {
            "market_ids",
            "trust_policy_loaded",
            "alert_policy_loaded",
        }
        for key in sync_keys:
            if key in self._values:
                setattr(self, key, self._values[key])
                self._values.pop(key)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "PipelineState":
        if not isinstance(values, Mapping):
            raise TypeError("state must be a mapping")
        return cls(dict(values))

    def __getitem__(self, key: str) -> Any:  # pragma: no cover - mapping delegation
        if key == "market_ids":
            return self.market_ids
        if key == "trust_policy_loaded":
            return self.trust_policy_loaded
        if key == "alert_policy_loaded":
            return self.alert_policy_loaded
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:  # pragma: no cover - mapping delegation
        if not isinstance(key, str):
            raise TypeError("Pipeline state keys must be strings")

        if key == "market_ids":
            self.market_ids = list(value) if isinstance(value, (list, tuple, set, frozenset)) else value
            return
        if key == "trust_policy_loaded":
            self.trust_policy_loaded = bool(value)
            return
        if key == "alert_policy_loaded":
            self.alert_policy_loaded = bool(value)
            return
        self._values[key] = value

    def __delitem__(self, key: str) -> None:  # pragma: no cover - mapping delegation
        if key in ("market_ids", "trust_policy_loaded", "alert_policy_loaded"):
            raise KeyError(f"{key} is a typed state field")
        del self._values[key]

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - mapping delegation
        yielded_keys = {"market_ids", "trust_policy_loaded", "alert_policy_loaded"}
        for key in yielded_keys:
            yield key
        yield from self._values

    def __len__(self) -> int:  # pragma: no cover - mapping delegation
        return len(self._values) + 3

    def get(self, key: str, default: Any = None) -> Any:  # pragma: no cover - mapping API
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: str, default: Any) -> Any:  # pragma: no cover - mapping API
        if key in self:
            return self[key]
        self[key] = default
        return default

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self._values)
        payload["market_ids"] = list(self.market_ids)
        payload["trust_policy_loaded"] = self.trust_policy_loaded
        payload["alert_policy_loaded"] = self.alert_policy_loaded
        return payload

    def __contains__(self, key: object) -> bool:  # pragma: no cover - mapping API
        if not isinstance(key, str):
            return False
        if key in ("market_ids", "trust_policy_loaded", "alert_policy_loaded"):
            return True
        return key in self._values


@dataclass
class PipelineRunContext:
    """Execution context shared across stage handlers."""

    run_id: str
    data_interval_start: Optional[str] = None
    data_interval_end: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: PipelineState = field(default_factory=PipelineState)

    def __post_init__(self) -> None:
        if isinstance(self.state, PipelineState):
            return
        if not isinstance(self.state, Mapping):
            raise TypeError("PipelineRunContext.state must be mapping-like")
        self.state = PipelineState.from_mapping(self.state)


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
