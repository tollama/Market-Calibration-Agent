"""Minimal cutoff snapshot builder skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .common import PipelineRunContext

DEFAULT_CUTOFF_TYPES = ("T-24h", "T-1h", "DAILY")
DEFAULT_SELECTION_RULE = "nearest-before"
DEFAULT_MAX_LOOKBACK_SECONDS = 900

# Backward-compatible alias for callers that referenced the old constant.
CUTOFF_TYPES = DEFAULT_CUTOFF_TYPES

_DEFAULT_PLACEHOLDER_SELECTED_TS = "1970-01-01T00:00:00+00:00"


@dataclass
class CutoffSnapshot:
    """Represents a selected cutoff row for a market."""

    market_id: str
    cutoff_type: str
    selected_ts: str
    selection_rule: str = DEFAULT_SELECTION_RULE


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _select_nearest_before(
    *,
    market_ids: list[str],
    cutoff_types: tuple[str, ...],
    source_rows: list[dict[str, Any]],
    max_lookback_seconds: int,
) -> dict[tuple[str, str], datetime]:
    selected: dict[tuple[str, str], datetime] = {}
    market_id_set = set(market_ids)
    cutoff_type_set = set(cutoff_types)

    for row in source_rows:
        market_id = row.get("market_id")
        cutoff_type = row.get("cutoff_type")
        if not isinstance(market_id, str) or not isinstance(cutoff_type, str):
            continue
        if market_id not in market_id_set or cutoff_type not in cutoff_type_set:
            continue

        source_ts = _parse_timestamp(row.get("ts"))
        cutoff_ts = _parse_timestamp(row.get("cutoff_ts"))
        if source_ts is None or cutoff_ts is None:
            continue

        if source_ts > cutoff_ts:
            continue

        lookback_seconds = (cutoff_ts - source_ts).total_seconds()
        if lookback_seconds > max_lookback_seconds:
            continue

        key = (market_id, cutoff_type)
        previous = selected.get(key)
        if previous is None or source_ts > previous:
            selected[key] = source_ts

    return selected


def build_cutoff_snapshots(
    market_ids: list[str],
    *,
    source_rows: list[dict[str, Any]] | None = None,
    cutoff_types: tuple[str, ...] = DEFAULT_CUTOFF_TYPES,
    selection_rule: str = DEFAULT_SELECTION_RULE,
    max_lookback_seconds: int = DEFAULT_MAX_LOOKBACK_SECONDS,
) -> list[CutoffSnapshot]:
    """Build cutoff snapshots for the configured markets."""

    if selection_rule != DEFAULT_SELECTION_RULE:
        raise ValueError(f"Unsupported selection_rule: {selection_rule}")

    snapshots: list[CutoffSnapshot] = []

    # Backward-compatible placeholder mode when source rows are not provided.
    if source_rows is None:
        for market_id in market_ids:
            for cutoff_type in cutoff_types:
                snapshots.append(
                    CutoffSnapshot(
                        market_id=market_id,
                        cutoff_type=cutoff_type,
                        selected_ts=_DEFAULT_PLACEHOLDER_SELECTED_TS,
                        selection_rule=selection_rule,
                    )
                )
        return snapshots

    selected_ts_by_key = _select_nearest_before(
        market_ids=market_ids,
        cutoff_types=cutoff_types,
        source_rows=source_rows,
        max_lookback_seconds=max_lookback_seconds,
    )
    for market_id in market_ids:
        for cutoff_type in cutoff_types:
            selected_ts = selected_ts_by_key.get((market_id, cutoff_type))
            if selected_ts is None:
                continue
            snapshots.append(
                CutoffSnapshot(
                    market_id=market_id,
                    cutoff_type=cutoff_type,
                    selected_ts=selected_ts.isoformat(),
                    selection_rule=selection_rule,
                )
            )
    return snapshots


def stage_build_cutoff_snapshots(context: PipelineRunContext) -> dict[str, object]:
    """Pipeline stage hook for cutoff snapshot generation."""

    market_ids = context.state.get("market_ids", [])
    snapshots = build_cutoff_snapshots(market_ids=list(market_ids))
    context.state["cutoff_snapshots"] = snapshots
    return {
        "cutoff_types": list(DEFAULT_CUTOFF_TYPES),
        "snapshot_count": len(snapshots),
    }
