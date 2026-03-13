"""Pipeline stage helper for building feature frames from cutoff snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Protocol
import os

import pandas as pd
import yaml

from features import build_features

DEFAULT_VOL_WINDOW = 5
DEFAULT_LIQUIDITY_LOW = 10_000.0
DEFAULT_LIQUIDITY_HIGH = 100_000.0
DEFAULT_CONFIG_PATH = Path("configs/default.yaml")
ENV_LIQUIDITY_LOW = "MCA_LIQUIDITY_LOW"
ENV_LIQUIDITY_HIGH = "MCA_LIQUIDITY_HIGH"


class _HasState(Protocol):
    state: dict[str, Any]


def stage_build_features(context: _HasState) -> dict[str, int]:
    """Build features from cutoff snapshot rows and store them in context.state."""
    cutoff_snapshot_rows = _get_cutoff_snapshot_rows(context)
    cutoff_snapshot_frame = _rows_to_frame(cutoff_snapshot_rows)

    if cutoff_snapshot_frame.empty:
        context.state["feature_frame"] = pd.DataFrame()
        return {"feature_count": 0}

    liquidity_low, liquidity_high = _resolve_liquidity_thresholds(context)
    feature_frame = build_features(
        cutoff_snapshot_frame,
        vol_window=DEFAULT_VOL_WINDOW,
        liquidity_low=liquidity_low,
        liquidity_high=liquidity_high,
    )
    context.state["feature_frame"] = feature_frame
    return {"feature_count": int(len(feature_frame))}


def _resolve_liquidity_thresholds(context: _HasState) -> tuple[float, float]:
    config = _load_feature_config(context)

    low = _coerce_positive_float(
        _first_non_none(
            context.state.get("liquidity_low"),
            os.getenv(ENV_LIQUIDITY_LOW),
            _get_mapping_value(config, "liquidity_low"),
            _get_mapping_value(_get_mapping_value(config, "liquidity_thresholds"), "low"),
            DEFAULT_LIQUIDITY_LOW,
        ),
        key="liquidity_low",
    )
    high = _coerce_positive_float(
        _first_non_none(
            context.state.get("liquidity_high"),
            os.getenv(ENV_LIQUIDITY_HIGH),
            _get_mapping_value(config, "liquidity_high"),
            _get_mapping_value(_get_mapping_value(config, "liquidity_thresholds"), "high"),
            DEFAULT_LIQUIDITY_HIGH,
        ),
        key="liquidity_high",
    )

    if low >= high:
        raise ValueError("liquidity_low must be smaller than liquidity_high.")
    return low, high


def _load_feature_config(context: _HasState) -> Mapping[str, Any]:
    config_path_raw = context.state.get("feature_config_path")
    config_path = Path(config_path_raw) if config_path_raw else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {}

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        return {}

    features = loaded.get("features")
    if isinstance(features, Mapping):
        return features
    return {}


def _first_non_none(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _coerce_positive_float(value: object, *, key: str) -> float:
    if value is None:
        raise ValueError(f"Missing required config value: {key}")
    numeric = float(value)
    if numeric <= 0:
        raise ValueError(f"{key} must be positive.")
    return numeric


def _get_mapping_value(container: object, key: str) -> object:
    if isinstance(container, Mapping):
        return container.get(key)
    return None


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
