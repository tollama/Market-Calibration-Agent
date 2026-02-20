"""Deterministic intraday OHLC aggregation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


def build_time_bars(
    rows: list[dict[str, Any]],
    *,
    interval_seconds: int = 60,
) -> list[dict[str, Any]]:
    """Aggregate raw intraday rows into time-bucketed OHLC bars."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    parsed_rows: list[tuple[str, int, int, float, int]] = []
    for row_index, row in enumerate(rows):
        market_id = row.get("market_id")
        ts = _coerce_epoch_seconds(row.get("ts"))
        price = _coerce_float(row.get("p_yes"))
        if not isinstance(market_id, str) or ts is None or price is None:
            continue

        bucket_start = _bucket_start(ts, interval_seconds)
        parsed_rows.append((market_id, bucket_start, ts, price, row_index))

    parsed_rows.sort(key=lambda item: (item[0], item[1], item[2], item[4]))

    bars: list[dict[str, Any]] = []
    active_key: tuple[str, int] | None = None
    active_bar: dict[str, Any] | None = None

    for market_id, bucket_start, _, price, _ in parsed_rows:
        key = (market_id, bucket_start)
        if key != active_key:
            if active_bar is not None:
                bars.append(active_bar)
            active_key = key
            active_bar = {
                "market_id": market_id,
                "start_ts": bucket_start,
                "end_ts": bucket_start + interval_seconds - 1,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "count": 1,
            }
            continue

        assert active_bar is not None
        active_bar["high"] = max(active_bar["high"], price)
        active_bar["low"] = min(active_bar["low"], price)
        active_bar["close"] = price
        active_bar["count"] += 1

    if active_bar is not None:
        bars.append(active_bar)

    return bars


def resample_to_5m(bars_1m: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll up 1-minute bars into deterministic 5-minute OHLC bars."""
    interval_seconds = 300
    parsed_rows: list[tuple[str, int, int, float, float, float, float, int, int]] = []

    for row_index, bar in enumerate(bars_1m):
        market_id = bar.get("market_id")
        start_ts = _coerce_epoch_seconds(bar.get("start_ts"))
        open_price = _coerce_float(bar.get("open"))
        high_price = _coerce_float(bar.get("high"))
        low_price = _coerce_float(bar.get("low"))
        close_price = _coerce_float(bar.get("close"))
        count = _coerce_int(bar.get("count"))

        if (
            not isinstance(market_id, str)
            or start_ts is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
            or count is None
        ):
            continue

        bucket_start = _bucket_start(start_ts, interval_seconds)
        parsed_rows.append(
            (
                market_id,
                bucket_start,
                start_ts,
                open_price,
                high_price,
                low_price,
                close_price,
                count,
                row_index,
            )
        )

    parsed_rows.sort(key=lambda item: (item[0], item[1], item[2], item[8]))

    bars: list[dict[str, Any]] = []
    active_key: tuple[str, int] | None = None
    active_bar: dict[str, Any] | None = None

    for (
        market_id,
        bucket_start,
        _start_ts,
        open_price,
        high_price,
        low_price,
        close_price,
        count,
        _row_index,
    ) in parsed_rows:
        key = (market_id, bucket_start)
        if key != active_key:
            if active_bar is not None:
                bars.append(active_bar)
            active_key = key
            active_bar = {
                "market_id": market_id,
                "start_ts": bucket_start,
                "end_ts": bucket_start + interval_seconds - 1,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "count": count,
            }
            continue

        assert active_bar is not None
        active_bar["high"] = max(active_bar["high"], high_price)
        active_bar["low"] = min(active_bar["low"], low_price)
        active_bar["close"] = close_price
        active_bar["count"] += count

    if active_bar is not None:
        bars.append(active_bar)

    return bars


def _bucket_start(ts_seconds: int, interval_seconds: int) -> int:
    return (ts_seconds // interval_seconds) * interval_seconds


def _coerce_epoch_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return math.floor(parsed.astimezone(timezone.utc).timestamp())

    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return math.floor(numeric)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None

        try:
            numeric = float(stripped)
        except ValueError:
            normalized = stripped
            if normalized.endswith("Z"):
                normalized = f"{normalized[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return math.floor(parsed.astimezone(timezone.utc).timestamp())

        if not math.isfinite(numeric):
            return None
        return math.floor(numeric)

    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if not math.isfinite(numeric):
        return None
    return numeric


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
        if not math.isfinite(numeric):
            return None
        return int(numeric)

    return None
