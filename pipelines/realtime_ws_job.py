from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import date, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


class _WSConnector(Protocol):
    def stream_messages(
        self,
        *,
        url: str,
        subscribe_message: Mapping[str, Any] | None = None,
        message_limit: int = 1000,
    ) -> AsyncIterator[Mapping[str, Any]] | Iterable[Mapping[str, Any]] | Any:
        ...


class _RawWriter(Protocol):
    def write(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.jsonl",
        dedupe_key: str | None = None,
    ) -> Path:
        ...


def _dedupe_rows(rows: list[dict[str, Any]], dedupe_key: str) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for row in rows:
        key = row.get(dedupe_key)
        if key is None:
            deduped.append(dict(row))
            continue
        normalized_key = str(key)
        if normalized_key in index_by_key:
            deduped[index_by_key[normalized_key]] = dict(row)
            continue
        index_by_key[normalized_key] = len(deduped)
        deduped.append(dict(row))
    return deduped


def _make_bar_id(
    *,
    bar_start_iso: str,
    minutes: int,
    symbol_key: str | None = None,
    symbol_value: Any | None = None,
) -> str:
    if symbol_key is None or symbol_value is None:
        return f"{bar_start_iso}|{minutes}m"
    return f"{symbol_key}={symbol_value}|{bar_start_iso}|{minutes}m"


def _pick_column(columns: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def _parse_datetime_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any() and series.dtype != "O":
        median = float(numeric.dropna().abs().median())
        unit = "ms" if median > 10_000_000_000 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(series, utc=True, errors="coerce")


def _fallback_build_time_bars(ticks: Iterable[Mapping[str, Any]], *_: Any, **__: Any) -> list[dict[str, Any]]:
    frame = pd.DataFrame(list(ticks))
    if frame.empty:
        return []

    ts_col = _pick_column(
        frame.columns,
        ("timestamp", "ts", "time", "event_time", "created_at"),
    )
    price_col = _pick_column(
        frame.columns,
        ("price", "last_price", "trade_price", "mid_price", "p"),
    )
    volume_col = _pick_column(
        frame.columns,
        ("size", "qty", "quantity", "volume", "amount"),
    )
    symbol_col = _pick_column(
        frame.columns,
        ("market_id", "token_id", "symbol", "asset_id"),
    )
    if ts_col is None or price_col is None:
        return []

    working = frame.copy()
    working["_ts"] = _parse_datetime_series(working[ts_col])
    working["_price"] = pd.to_numeric(working[price_col], errors="coerce")
    if volume_col is None:
        working["_volume"] = 1.0
    else:
        working["_volume"] = pd.to_numeric(working[volume_col], errors="coerce").fillna(0.0)

    working = working.dropna(subset=["_ts", "_price"]).sort_values("_ts")
    if working.empty:
        return []

    working["_bucket"] = working["_ts"].dt.floor("min")
    group_cols = ["_bucket"]
    if symbol_col is not None:
        group_cols.append(symbol_col)

    bars: list[dict[str, Any]] = []
    for group_key, group_frame in working.groupby(group_cols, dropna=False, sort=True):
        if symbol_col is None:
            bar_start = group_key
            symbol_value = None
        else:
            bucket, symbol_value = group_key
            bar_start = bucket

        bar_start_iso = bar_start.isoformat().replace("+00:00", "Z")
        bar_end_iso = (bar_start + pd.Timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        row: dict[str, Any] = {
            "bar_start": bar_start_iso,
            "bar_end": bar_end_iso,
            "open": float(group_frame["_price"].iloc[0]),
            "high": float(group_frame["_price"].max()),
            "low": float(group_frame["_price"].min()),
            "close": float(group_frame["_price"].iloc[-1]),
            "volume": float(group_frame["_volume"].sum()),
            "tick_count": int(group_frame.shape[0]),
        }
        if symbol_col is not None:
            row[symbol_col] = symbol_value
        row["bar_id"] = _make_bar_id(
            bar_start_iso=bar_start_iso,
            minutes=1,
            symbol_key=symbol_col,
            symbol_value=symbol_value,
        )
        bars.append(row)

    return bars


def _fallback_resample_to_5m(
    bars_1m: Iterable[Mapping[str, Any]],
    *_: Any,
    **__: Any,
) -> list[dict[str, Any]]:
    frame = pd.DataFrame(list(bars_1m))
    if frame.empty:
        return []

    start_col = _pick_column(
        frame.columns,
        ("bar_start", "timestamp", "start", "bucket_start"),
    )
    symbol_col = _pick_column(
        frame.columns,
        ("market_id", "token_id", "symbol", "asset_id"),
    )
    if start_col is None:
        return []

    working = frame.copy()
    working["_bar_start"] = _parse_datetime_series(working[start_col])
    working = working.dropna(subset=["_bar_start"])
    if working.empty:
        return []

    for column in ("open", "high", "low", "close"):
        if column not in working.columns:
            return []
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if "volume" in working.columns:
        working["volume"] = pd.to_numeric(working["volume"], errors="coerce").fillna(0.0)
    else:
        working["volume"] = 0.0
    if "tick_count" in working.columns:
        working["tick_count"] = pd.to_numeric(working["tick_count"], errors="coerce").fillna(0).astype(int)
    else:
        working["tick_count"] = 0

    working = working.sort_values("_bar_start")
    working["_bucket_5m"] = working["_bar_start"].dt.floor("5min")
    group_cols = ["_bucket_5m"]
    if symbol_col is not None:
        group_cols.append(symbol_col)

    bars_5m: list[dict[str, Any]] = []
    for group_key, group_frame in working.groupby(group_cols, dropna=False, sort=True):
        if symbol_col is None:
            bar_start = group_key
            symbol_value = None
        else:
            bucket, symbol_value = group_key
            bar_start = bucket

        bar_start_iso = bar_start.isoformat().replace("+00:00", "Z")
        bar_end_iso = (bar_start + pd.Timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        row: dict[str, Any] = {
            "bar_start": bar_start_iso,
            "bar_end": bar_end_iso,
            "open": float(group_frame["open"].iloc[0]),
            "high": float(group_frame["high"].max()),
            "low": float(group_frame["low"].min()),
            "close": float(group_frame["close"].iloc[-1]),
            "volume": float(group_frame["volume"].sum()),
            "tick_count": int(group_frame["tick_count"].sum()),
        }
        if symbol_col is not None:
            row[symbol_col] = symbol_value
        row["bar_id"] = _make_bar_id(
            bar_start_iso=bar_start_iso,
            minutes=5,
            symbol_key=symbol_col,
            symbol_value=symbol_value,
        )
        bars_5m.append(row)

    return bars_5m


def _load_bar_builders() -> tuple[Any, Any]:
    try:
        module = import_module("pipelines.aggregate_intraday_bars")
    except ModuleNotFoundError as exc:
        if exc.name not in {"pipelines.aggregate_intraday_bars", "aggregate_intraday_bars"}:
            raise
        return _fallback_build_time_bars, _fallback_resample_to_5m

    build_time_bars = getattr(module, "build_time_bars", None)
    resample_to_5m = getattr(module, "resample_to_5m", None)
    if not callable(build_time_bars) or not callable(resample_to_5m):
        return _fallback_build_time_bars, _fallback_resample_to_5m
    return build_time_bars, resample_to_5m


def _call_build_time_bars(builder: Any, ticks: list[dict[str, Any]]) -> Any:
    attempts = [
        ((ticks,), {}),
        ((), {"ticks": ticks}),
        ((), {"records": ticks}),
        ((ticks,), {"interval": "1m"}),
        ((ticks,), {"timeframe": "1m"}),
        ((ticks,), {"freq": "1min"}),
        ((), {"ticks": ticks, "interval": "1m"}),
    ]
    last_type_error: TypeError | None = None
    for args, kwargs in attempts:
        try:
            return builder(*args, **kwargs)
        except TypeError as exc:
            last_type_error = exc
    if last_type_error is not None:
        raise last_type_error
    return builder(ticks)


def _call_resample_to_5m(
    resampler: Any,
    bars_1m: list[dict[str, Any]],
    ticks: list[dict[str, Any]],
) -> Any:
    attempts = [
        ((bars_1m,), {}),
        ((), {"bars_1m": bars_1m}),
        ((), {"bars": bars_1m}),
        ((bars_1m,), {"interval": "5m"}),
        ((), {"bars_1m": bars_1m, "interval": "5m"}),
        ((ticks,), {}),
        ((), {"ticks": ticks}),
    ]
    last_type_error: TypeError | None = None
    for args, kwargs in attempts:
        try:
            return resampler(*args, **kwargs)
        except TypeError as exc:
            last_type_error = exc
    if last_type_error is not None:
        raise last_type_error
    return resampler(bars_1m)


def _to_records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        return [dict(row) for row in data.to_dict(orient="records")]
    if isinstance(data, Mapping):
        return [dict(data)]
    if isinstance(data, tuple) and data:
        return _to_records(data[0])
    if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
        rows: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, Mapping):
                raise TypeError("Bar builders must return mappings or DataFrame-like records.")
            rows.append(dict(row))
        return rows
    raise TypeError("Bar builders must return mappings or DataFrame-like records.")


def _normalize_message(message: Any) -> dict[str, Any]:
    if isinstance(message, Mapping):
        return dict(message)
    return {"event": message}


async def _collect_stream_messages(
    *,
    ws_connector: _WSConnector,
    url: str,
    subscribe_message: Mapping[str, Any] | None,
    message_limit: int,
) -> list[dict[str, Any]]:
    if message_limit <= 0:
        return []

    stream = ws_connector.stream_messages(
        url=url,
        subscribe_message=subscribe_message,
        message_limit=message_limit,
    )
    if asyncio.iscoroutine(stream):
        stream = await stream

    messages: list[dict[str, Any]] = []
    if hasattr(stream, "__aiter__"):
        async for message in stream:  # type: ignore[union-attr]
            messages.append(_normalize_message(message))
            if len(messages) >= message_limit:
                break
        return messages

    if isinstance(stream, Iterable):
        for message in stream:
            messages.append(_normalize_message(message))
            if len(messages) >= message_limit:
                break
        return messages

    raise TypeError("ws_connector.stream_messages(...) must return an iterable or async iterable.")


async def run_realtime_ws_job(
    *,
    ws_connector: _WSConnector,
    raw_writer: _RawWriter,
    url: str,
    dt: date | datetime | str | None = None,
    subscribe_message: Mapping[str, Any] | None = None,
    message_limit: int = 1000,
) -> dict[str, Any]:
    messages = await _collect_stream_messages(
        ws_connector=ws_connector,
        url=url,
        subscribe_message=subscribe_message,
        message_limit=message_limit,
    )

    ticks_path = raw_writer.write(
        messages,
        dataset="realtime_ticks",
        dt=dt,
        dedupe_key="event_id",
    )
    deduped_ticks = _dedupe_rows(messages, dedupe_key="event_id")

    build_time_bars, resample_to_5m = _load_bar_builders()
    bars_1m = _to_records(_call_build_time_bars(build_time_bars, deduped_ticks))
    bars_5m = _to_records(_call_resample_to_5m(resample_to_5m, bars_1m, deduped_ticks))

    bars_1m_path = raw_writer.write(
        bars_1m,
        dataset="realtime_bars_1m",
        dt=dt,
        dedupe_key="bar_id",
    )
    bars_5m_path = raw_writer.write(
        bars_5m,
        dataset="realtime_bars_5m",
        dt=dt,
        dedupe_key="bar_id",
    )

    return {
        "message_count": len(messages),
        "tick_count": len(messages),
        "deduped_tick_count": len(deduped_ticks),
        "bar_1m_count": len(bars_1m),
        "bar_5m_count": len(bars_5m),
        "output_paths": {
            "realtime_ticks": str(ticks_path),
            "realtime_bars_1m": str(bars_1m_path),
            "realtime_bars_5m": str(bars_5m_path),
        },
    }


def run_realtime_ws_job_sync(
    *,
    ws_connector: _WSConnector,
    raw_writer: _RawWriter,
    url: str,
    dt: date | datetime | str | None = None,
    subscribe_message: Mapping[str, Any] | None = None,
    message_limit: int = 1000,
) -> dict[str, Any]:
    return asyncio.run(
        run_realtime_ws_job(
            ws_connector=ws_connector,
            raw_writer=raw_writer,
            url=url,
            dt=dt,
            subscribe_message=subscribe_message,
            message_limit=message_limit,
        )
    )
