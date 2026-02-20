"""Pipeline stage helper for building feature frames from cutoff snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol

import pandas as pd

from features import build_features

DEFAULT_VOL_WINDOW = 5
DEFAULT_LIQUIDITY_LOW = 10_000.0
DEFAULT_LIQUIDITY_HIGH = 100_000.0


class _HasState(Protocol):
    state: dict[str, Any]


def stage_build_features(context: _HasState) -> dict[str, int]:
    """Build features from cutoff snapshot rows and store them in context.state."""
    cutoff_snapshot_rows = _get_cutoff_snapshot_rows(context)
    cutoff_snapshot_frame = _rows_to_frame(cutoff_snapshot_rows)

    if cutoff_snapshot_frame.empty:
        context.state["feature_frame"] = pd.DataFrame()
        return {"feature_count": 0}

    feature_frame = build_features(
        cutoff_snapshot_frame,
        vol_window=DEFAULT_VOL_WINDOW,
        liquidity_low=DEFAULT_LIQUIDITY_LOW,
        liquidity_high=DEFAULT_LIQUIDITY_HIGH,
    )
    context.state["feature_frame"] = feature_frame
    return {"feature_count": int(len(feature_frame))}


def _get_cutoff_snapshot_rows(context: _HasState) -> list[Any]:
    if "cutoff_snapshot_rows" in context.state:
        source = context.state.get("cutoff_snapshot_rows")
    else:
        source = context.state.get("cutoff_snapshots")

    if source is None:
        return []
    if isinstance(source, pd.DataFrame):
        return source.to_dict(orient="records")
    if isinstance(source, Mapping):
        return [dict(source)]
    if isinstance(source, (list, tuple)):
        return list(source)
    return [source]


def _rows_to_frame(rows: list[Any]) -> pd.DataFrame:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if row is None:
            continue
        normalized_rows.append(_row_to_dict(row))
    if not normalized_rows:
        return pd.DataFrame()
    return pd.DataFrame.from_records(normalized_rows)


def _row_to_dict(row: Any) -> dict[str, Any]:
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

    raise TypeError(f"Unsupported cutoff snapshot row type: {type(row)!r}")
