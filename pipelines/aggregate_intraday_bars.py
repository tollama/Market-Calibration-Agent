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

    parsed_rows: list[tuple[str, int, int, float, float, int]] = []
    for row_index, row in enumerate(rows):
        market_id = row.get("market_id")
        ts = _coerce_epoch_seconds(row.get("ts"))
        price = _coerce_float(row.get("p_yes"))
        volume = _coerce_volume(
            row,
            candidates=("volume_sum", "volume", "size", "qty", "quantity", "amount"),
        )
        if not isinstance(market_id, str) or ts is None or price is None:
            continue

        bucket_start = _bucket_start(ts, interval_seconds)
        parsed_rows.append((market_id, bucket_start, ts, price, volume, row_index))

    parsed_rows.sort(key=lambda item: (item[0], item[1], item[2], item[5]))

    bars: list[dict[str, Any]] = []
    active_key: tuple[str, int] | None = None
    active_bar: dict[str, Any] | None = None

    for market_id, bucket_start, _, price, volume, _ in parsed_rows:
        key = (market_id, bucket_start)
        if key != active_key:
            if active_bar is not None:
                bars.append(_finalize_1m_bar(active_bar))
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
                "trade_count": 1,
                "volume_sum": volume,
                "_rv_sq_sum": 0.0,
            }
            continue

        assert active_bar is not None
        previous_price = active_bar["close"]
        if previous_price > 0.0 and price > 0.0:
            log_return = math.log(price / previous_price)
            active_bar["_rv_sq_sum"] += log_return * log_return
        active_bar["high"] = max(active_bar["high"], price)
        active_bar["low"] = min(active_bar["low"], price)
        active_bar["close"] = price
        active_bar["count"] += 1
        active_bar["trade_count"] += 1
        active_bar["volume_sum"] += volume

    if active_bar is not None:
        bars.append(_finalize_1m_bar(active_bar))

    return bars


def resample_to_5m(bars_1m: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll up 1-minute bars into deterministic 5-minute OHLC bars."""
    interval_seconds = 300
    parsed_rows: list[tuple[str, int, int, float, float, float, float, int, float, float, int]] = []

    for row_index, bar in enumerate(bars_1m):
        market_id = bar.get("market_id")
        start_ts = _coerce_epoch_seconds(bar.get("start_ts"))
        open_price = _coerce_float(bar.get("open"))
        high_price = _coerce_float(bar.get("high"))
        low_price = _coerce_float(bar.get("low"))
        close_price = _coerce_float(bar.get("close"))
        trade_count = _coerce_int(bar.get("trade_count"))
        if trade_count is None:
            trade_count = _coerce_int(bar.get("count"))
        volume_sum = _coerce_volume(bar, candidates=("volume_sum", "volume"))
        realized_vol = _coerce_float(bar.get("realized_vol"))
        if realized_vol is None:
            realized_vol = 0.0

        if (
            not isinstance(market_id, str)
            or start_ts is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
            or trade_count is None
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
                trade_count,
                volume_sum,
                realized_vol,
                row_index,
            )
        )

    parsed_rows.sort(key=lambda item: (item[0], item[1], item[2], item[10]))

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
        trade_count,
        volume_sum,
        realized_vol,
        _row_index,
    ) in parsed_rows:
        key = (market_id, bucket_start)
        if key != active_key:
            if active_bar is not None:
                bars.append(_finalize_5m_bar(active_bar))
            active_key = key
            active_bar = {
                "market_id": market_id,
                "start_ts": bucket_start,
                "end_ts": bucket_start + interval_seconds - 1,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "count": trade_count,
                "trade_count": trade_count,
                "volume_sum": volume_sum,
                "_rv_sq_sum": realized_vol * realized_vol,
            }
            continue

        assert active_bar is not None
        active_bar["high"] = max(active_bar["high"], high_price)
        active_bar["low"] = min(active_bar["low"], low_price)
        active_bar["close"] = close_price
        active_bar["count"] += trade_count
        active_bar["trade_count"] += trade_count
        active_bar["volume_sum"] += volume_sum
        active_bar["_rv_sq_sum"] += realized_vol * realized_vol

    if active_bar is not None:
        bars.append(_finalize_5m_bar(active_bar))

    return bars


def _finalize_1m_bar(bar: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(bar)
    rv_sq_sum = _coerce_float(finalized.pop("_rv_sq_sum"))
    finalized["realized_vol"] = math.sqrt(rv_sq_sum) if rv_sq_sum is not None and rv_sq_sum > 0.0 else 0.0
    return finalized


def _finalize_5m_bar(bar: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(bar)
    rv_sq_sum = _coerce_float(finalized.pop("_rv_sq_sum"))
    finalized["realized_vol"] = math.sqrt(rv_sq_sum) if rv_sq_sum is not None and rv_sq_sum > 0.0 else 0.0
    return finalized


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


def _coerce_volume(row: dict[str, Any], *, candidates: tuple[str, ...]) -> float:
    for key in candidates:
        volume = _coerce_float(row.get(key))
        if volume is not None:
            return volume
    return 0.0
