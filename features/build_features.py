"""Deterministic feature computation for market calibration snapshots."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

_FEATURE_COLUMNS = [
    "returns",
    "vol",
    "volume_velocity",
    "oi_change",
    "tte_seconds",
    "liquidity_bucket",
    "liquidity_bucket_id",
]


def build_features(
    cutoff_snapshot: pd.DataFrame,
    high_freq_agg: pd.DataFrame | None = None,
    *,
    market_col: str = "market_id",
    ts_col: str = "ts",
    price_col: str = "p_yes",
    volume_col: str = "volume_24h",
    open_interest_col: str = "open_interest",
    tte_col: str = "tte_seconds",
    end_ts_columns: Sequence[str] = ("end_ts", "event_end_ts", "resolution_ts"),
    vol_window: int = 5,
    liquidity_low: float = 10_000.0,
    liquidity_high: float = 100_000.0,
) -> pd.DataFrame:
    """Build deterministic feature columns from market snapshot records."""
    if vol_window < 2:
        raise ValueError("vol_window must be >= 2.")
    if liquidity_low >= liquidity_high:
        raise ValueError("liquidity_low must be smaller than liquidity_high.")

    required = [market_col, ts_col, price_col, volume_col, open_interest_col]
    missing = [column for column in required if column not in cutoff_snapshot.columns]
    if missing:
        raise ValueError(f"cutoff_snapshot is missing required columns: {missing}")

    frame = cutoff_snapshot.copy()
    frame[ts_col] = pd.to_datetime(frame[ts_col], utc=True, errors="coerce")
    if frame[ts_col].isna().any():
        raise ValueError(f"Column '{ts_col}' contains invalid timestamps.")

    frame[price_col] = pd.to_numeric(frame[price_col], errors="coerce")
    frame[volume_col] = pd.to_numeric(frame[volume_col], errors="coerce")
    frame[open_interest_col] = pd.to_numeric(frame[open_interest_col], errors="coerce")

    frame.sort_values([market_col, ts_col], kind="mergesort", inplace=True)
    frame.reset_index(drop=True, inplace=True)

    grouped = frame.groupby(market_col, sort=False, group_keys=False)

    prev_price = grouped[price_col].shift(1)
    returns = (frame[price_col] - prev_price) / prev_price.where(prev_price != 0)
    frame["returns"] = _clean_numeric(returns, fill_value=0.0)

    rolling_vol = (
        frame.groupby(market_col, sort=False)["returns"]
        .rolling(window=vol_window, min_periods=2)
        .std(ddof=0)
        .reset_index(level=0, drop=True)
    )
    frame["vol"] = _clean_numeric(rolling_vol, fill_value=0.0)

    prev_volume = grouped[volume_col].shift(1)
    delta_volume = frame[volume_col] - prev_volume
    prev_ts = grouped[ts_col].shift(1)
    delta_seconds = (frame[ts_col] - prev_ts).dt.total_seconds()
    volume_velocity = delta_volume / delta_seconds.where(delta_seconds > 0)
    frame["volume_velocity"] = _clean_numeric(volume_velocity, fill_value=0.0)

    prev_open_interest = grouped[open_interest_col].shift(1)
    oi_change = (frame[open_interest_col] - prev_open_interest) / prev_open_interest.where(
        prev_open_interest != 0
    )
    frame["oi_change"] = _clean_numeric(oi_change, fill_value=0.0)

    frame["tte_seconds"] = _build_tte_seconds(
        frame=frame,
        ts_col=ts_col,
        tte_col=tte_col,
        end_ts_columns=end_ts_columns,
    )

    frame["liquidity_bucket"] = _build_liquidity_bucket(
        frame=frame,
        volume_col=volume_col,
        open_interest_col=open_interest_col,
        low=liquidity_low,
        high=liquidity_high,
    )
    frame["liquidity_bucket_id"] = _build_liquidity_bucket_id(frame["liquidity_bucket"])

    if high_freq_agg is not None:
        frame = _overlay_high_frequency_features(
            frame=frame,
            high_freq_agg=high_freq_agg,
            market_col=market_col,
            ts_col=ts_col,
        )

    for column in ("returns", "vol", "volume_velocity", "oi_change", "tte_seconds"):
        frame[column] = _clean_numeric(frame[column], fill_value=0.0)

    ordered_columns = [column for column in frame.columns if column not in _FEATURE_COLUMNS]
    ordered_columns.extend(_FEATURE_COLUMNS)
    return frame[ordered_columns]


def _clean_numeric(values: pd.Series, *, fill_value: float) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.replace([np.inf, -np.inf], np.nan).fillna(fill_value).astype(float)


def _build_tte_seconds(
    *,
    frame: pd.DataFrame,
    ts_col: str,
    tte_col: str,
    end_ts_columns: Sequence[str],
) -> pd.Series:
    if tte_col in frame.columns:
        tte_series = pd.to_numeric(frame[tte_col], errors="coerce")
        if tte_series.notna().any():
            return tte_series.fillna(0.0).clip(lower=0.0).astype(float)

    end_ts_column = next((column for column in end_ts_columns if column in frame.columns), None)
    if end_ts_column is None:
        return pd.Series(np.zeros(len(frame), dtype=float), index=frame.index)

    end_ts = pd.to_datetime(frame[end_ts_column], utc=True, errors="coerce")
    tte_seconds = (end_ts - frame[ts_col]).dt.total_seconds()
    return tte_seconds.fillna(0.0).clip(lower=0.0).astype(float)


def _build_liquidity_bucket(
    *,
    frame: pd.DataFrame,
    volume_col: str,
    open_interest_col: str,
    low: float,
    high: float,
) -> pd.Series:
    base_liquidity = np.maximum(
        pd.to_numeric(frame[volume_col], errors="coerce").fillna(0.0),
        pd.to_numeric(frame[open_interest_col], errors="coerce").fillna(0.0),
    )
    computed = pd.Series(
        np.where(base_liquidity < low, "LOW", np.where(base_liquidity < high, "MID", "HIGH")),
        index=frame.index,
    )

    if "liquidity_bucket" not in frame.columns:
        return computed.astype(str)

    provided = frame["liquidity_bucket"].astype("string").str.upper()
    normalized = provided.where(provided.isin({"LOW", "MID", "HIGH"}))
    return normalized.fillna(computed).astype(str)


def _build_liquidity_bucket_id(liquidity_bucket: pd.Series) -> pd.Series:
    mapping = {"LOW": 0, "MID": 1, "HIGH": 2}
    normalized = liquidity_bucket.astype("string").str.upper()
    return normalized.map(mapping).fillna(1).astype(int)


def _overlay_high_frequency_features(
    *,
    frame: pd.DataFrame,
    high_freq_agg: pd.DataFrame,
    market_col: str,
    ts_col: str,
) -> pd.DataFrame:
    if high_freq_agg.empty:
        return frame
    if market_col not in high_freq_agg.columns or ts_col not in high_freq_agg.columns:
        return frame

    overlay_columns = [column for column in ("returns", "vol", "volume_velocity", "oi_change") if column in high_freq_agg.columns]
    if not overlay_columns:
        return frame

    overlay = high_freq_agg[[market_col, ts_col] + overlay_columns].copy()
    overlay[ts_col] = pd.to_datetime(overlay[ts_col], utc=True, errors="coerce")
    overlay = overlay.dropna(subset=[ts_col])
    if overlay.empty:
        return frame

    overlay.sort_values([market_col, ts_col], kind="mergesort", inplace=True)
    overlay = overlay.drop_duplicates(subset=[market_col, ts_col], keep="last")

    merged = frame.merge(
        overlay,
        on=[market_col, ts_col],
        how="left",
        suffixes=("", "_hf"),
    )

    for column in overlay_columns:
        overlay_column = f"{column}_hf"
        override_values = pd.to_numeric(merged[overlay_column], errors="coerce")
        merged[column] = override_values.where(override_values.notna(), merged[column])
        merged.drop(columns=[overlay_column], inplace=True)

    return merged
