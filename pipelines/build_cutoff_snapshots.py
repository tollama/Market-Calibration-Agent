"""Minimal cutoff snapshot builder skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .common import PipelineRunContext

CUTOFF_TYPES = ("T-24h", "T-1h", "DAILY")


@dataclass(slots=True)
class CutoffSnapshot:
    """Represents a selected cutoff row for a market."""

    market_id: str
    cutoff_type: str
    selected_ts: str
    selection_rule: str = "nearest-before"


def build_cutoff_snapshots(market_ids: list[str]) -> list[CutoffSnapshot]:
    """Build placeholder cutoff snapshots for the configured markets."""

    selected_ts = datetime.now(timezone.utc).isoformat()
    snapshots: list[CutoffSnapshot] = []
    for market_id in market_ids:
        for cutoff_type in CUTOFF_TYPES:
            snapshots.append(
                CutoffSnapshot(
                    market_id=market_id,
                    cutoff_type=cutoff_type,
                    selected_ts=selected_ts,
                )
            )
    return snapshots


def stage_build_cutoff_snapshots(context: PipelineRunContext) -> dict[str, object]:
    """Pipeline stage hook for cutoff snapshot generation."""

    market_ids = context.state.get("market_ids", [])
    snapshots = build_cutoff_snapshots(market_ids=list(market_ids))
    context.state["cutoff_snapshots"] = snapshots
    return {
        "cutoff_types": list(CUTOFF_TYPES),
        "snapshot_count": len(snapshots),
    }
