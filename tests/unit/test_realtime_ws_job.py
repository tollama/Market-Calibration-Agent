from __future__ import annotations

import asyncio
import json
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pipelines.realtime_ws_job as realtime_ws_job
from pipelines.realtime_ws_job import run_realtime_ws_job, run_realtime_ws_job_sync
from storage.writers import RawWriter


class FakeWSConnector:
    def __init__(
        self,
        messages: list[dict[str, Any]],
        *,
        last_stats: Mapping[str, Any] | None = None,
    ) -> None:
        self._messages = messages
        self.calls: list[dict[str, Any]] = []
        if last_stats is not None:
            self.last_stats = dict(last_stats)

    async def stream_messages(
        self,
        *,
        url: str,
        subscribe_message: Mapping[str, Any] | None = None,
        message_limit: int = 1000,
    ):
        self.calls.append(
            {
                "url": url,
                "subscribe_message": subscribe_message,
                "message_limit": message_limit,
            }
        )
        for message in self._messages:
            yield dict(message)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(row) for row in rows]


def test_run_realtime_ws_job_writes_ticks_and_bars(monkeypatch, tmp_path: Path) -> None:
    aggregate_calls: dict[str, Any] = {}
    aggregate_module = types.ModuleType("pipelines.aggregate_intraday_bars")

    def fake_build_time_bars(ticks: list[dict[str, Any]], *args: Any, **kwargs: Any):
        aggregate_calls["build_ticks"] = [dict(row) for row in ticks]
        aggregate_calls["build_args"] = args
        aggregate_calls["build_kwargs"] = kwargs
        return [
            {
                "bar_id": "mkt-1|2026-02-20T12:00:00Z|1m",
                "market_id": "mkt-1",
                "bar_start": "2026-02-20T12:00:00Z",
                "bar_end": "2026-02-20T12:01:00Z",
                "open": 0.42,
                "high": 0.50,
                "low": 0.42,
                "close": 0.50,
                "volume": 12.0,
                "tick_count": 2,
            }
        ]

    def fake_resample_to_5m(bars_1m: list[dict[str, Any]], *args: Any, **kwargs: Any):
        aggregate_calls["resample_bars"] = [dict(row) for row in bars_1m]
        aggregate_calls["resample_args"] = args
        aggregate_calls["resample_kwargs"] = kwargs
        return [
            {
                "bar_id": "mkt-1|2026-02-20T12:00:00Z|5m",
                "market_id": "mkt-1",
                "bar_start": "2026-02-20T12:00:00Z",
                "bar_end": "2026-02-20T12:05:00Z",
                "open": 0.42,
                "high": 0.50,
                "low": 0.42,
                "close": 0.50,
                "volume": 12.0,
                "tick_count": 2,
            }
        ]

    aggregate_module.build_time_bars = fake_build_time_bars
    aggregate_module.resample_to_5m = fake_resample_to_5m
    monkeypatch.setitem(sys.modules, "pipelines.aggregate_intraday_bars", aggregate_module)

    connector = FakeWSConnector(
        [
            {
                "event_id": "e-1",
                "market_id": "mkt-1",
                "timestamp": "2026-02-20T12:00:10Z",
                "price": 0.40,
                "size": 5.0,
            },
            {
                "event_id": "e-1",
                "market_id": "mkt-1",
                "timestamp": "2026-02-20T12:00:20Z",
                "price": 0.42,
                "size": 5.0,
            },
            {
                "event_id": "e-2",
                "market_id": "mkt-1",
                "timestamp": "2026-02-20T12:00:55Z",
                "price": 0.50,
                "size": 2.0,
            },
        ]
    )
    writer = RawWriter(tmp_path)

    summary = asyncio.run(
        run_realtime_ws_job(
            ws_connector=connector,
            raw_writer=writer,
            url="wss://example.test/stream",
            dt="2026-02-20",
            subscribe_message={"type": "subscribe", "channel": "market"},
            message_limit=1000,
        )
    )

    ticks_path = tmp_path / "raw" / "realtime_ticks" / "dt=2026-02-20" / "data.jsonl"
    bars_1m_path = tmp_path / "raw" / "realtime_bars_1m" / "dt=2026-02-20" / "data.jsonl"
    bars_5m_path = tmp_path / "raw" / "realtime_bars_5m" / "dt=2026-02-20" / "data.jsonl"

    assert connector.calls == [
        {
            "url": "wss://example.test/stream",
            "subscribe_message": {"type": "subscribe", "channel": "market"},
            "message_limit": 1000,
        }
    ]
    assert summary["message_count"] == 3
    assert summary["tick_count"] == 3
    assert summary["deduped_tick_count"] == 2
    assert summary["bar_1m_count"] == 1
    assert summary["bar_5m_count"] == 1
    assert summary["output_paths"] == {
        "realtime_ticks": str(ticks_path),
        "realtime_bars_1m": str(bars_1m_path),
        "realtime_bars_5m": str(bars_5m_path),
    }

    assert _read_jsonl(ticks_path) == [
        {
            "event_id": "e-1",
            "market_id": "mkt-1",
            "timestamp": "2026-02-20T12:00:20Z",
            "price": 0.42,
            "size": 5.0,
        },
        {
            "event_id": "e-2",
            "market_id": "mkt-1",
            "timestamp": "2026-02-20T12:00:55Z",
            "price": 0.50,
            "size": 2.0,
        },
    ]

    expected_bar_1m = [
        {
            "bar_id": "mkt-1|2026-02-20T12:00:00Z|1m",
            "market_id": "mkt-1",
            "bar_start": "2026-02-20T12:00:00Z",
            "bar_end": "2026-02-20T12:01:00Z",
            "open": 0.42,
            "high": 0.50,
            "low": 0.42,
            "close": 0.50,
            "volume": 12.0,
            "tick_count": 2,
        }
    ]
    expected_bar_5m = [
        {
            "bar_id": "mkt-1|2026-02-20T12:00:00Z|5m",
            "market_id": "mkt-1",
            "bar_start": "2026-02-20T12:00:00Z",
            "bar_end": "2026-02-20T12:05:00Z",
            "open": 0.42,
            "high": 0.50,
            "low": 0.42,
            "close": 0.50,
            "volume": 12.0,
            "tick_count": 2,
        }
    ]
    assert _read_jsonl(bars_1m_path) == expected_bar_1m
    assert _read_jsonl(bars_5m_path) == expected_bar_5m

    assert [row["event_id"] for row in aggregate_calls["build_ticks"]] == ["e-1", "e-2"]
    assert aggregate_calls["build_args"] == ()
    assert aggregate_calls["build_kwargs"] == {}
    assert aggregate_calls["resample_bars"] == expected_bar_1m
    assert aggregate_calls["resample_args"] == ()
    assert aggregate_calls["resample_kwargs"] == {}


def test_run_realtime_ws_job_sync_respects_message_limit(monkeypatch, tmp_path: Path) -> None:
    aggregate_module = types.ModuleType("pipelines.aggregate_intraday_bars")

    def fake_build_time_bars(ticks: list[dict[str, Any]], *args: Any, **kwargs: Any):
        _ = args, kwargs
        rows: list[dict[str, Any]] = []
        for index, tick in enumerate(ticks, start=1):
            rows.append(
                {
                    "bar_id": f"{tick['event_id']}|1m",
                    "market_id": tick["market_id"],
                    "bar_start": f"2026-02-20T12:0{index-1}:00Z",
                    "bar_end": f"2026-02-20T12:0{index}:00Z",
                    "open": tick["price"],
                    "high": tick["price"],
                    "low": tick["price"],
                    "close": tick["price"],
                    "volume": tick["size"],
                    "tick_count": 1,
                }
            )
        return rows

    def fake_resample_to_5m(bars_1m: list[dict[str, Any]], *args: Any, **kwargs: Any):
        _ = args, kwargs
        if not bars_1m:
            return []
        return [
            {
                "bar_id": "mkt-2|2026-02-20T12:00:00Z|5m",
                "market_id": "mkt-2",
                "bar_start": "2026-02-20T12:00:00Z",
                "bar_end": "2026-02-20T12:05:00Z",
                "open": bars_1m[0]["open"],
                "high": max(row["high"] for row in bars_1m),
                "low": min(row["low"] for row in bars_1m),
                "close": bars_1m[-1]["close"],
                "volume": sum(row["volume"] for row in bars_1m),
                "tick_count": len(bars_1m),
            }
        ]

    aggregate_module.build_time_bars = fake_build_time_bars
    aggregate_module.resample_to_5m = fake_resample_to_5m
    monkeypatch.setitem(sys.modules, "pipelines.aggregate_intraday_bars", aggregate_module)

    connector = FakeWSConnector(
        [
            {
                "event_id": "a-1",
                "market_id": "mkt-2",
                "timestamp": "2026-02-20T12:00:05Z",
                "price": 0.10,
                "size": 1.0,
            },
            {
                "event_id": "a-2",
                "market_id": "mkt-2",
                "timestamp": "2026-02-20T12:01:05Z",
                "price": 0.20,
                "size": 1.0,
            },
            {
                "event_id": "a-3",
                "market_id": "mkt-2",
                "timestamp": "2026-02-20T12:02:05Z",
                "price": 0.30,
                "size": 1.0,
            },
            {
                "event_id": "a-4",
                "market_id": "mkt-2",
                "timestamp": "2026-02-20T12:03:05Z",
                "price": 0.40,
                "size": 1.0,
            },
        ]
    )
    writer = RawWriter(tmp_path)

    summary = run_realtime_ws_job_sync(
        ws_connector=connector,
        raw_writer=writer,
        url="wss://example.test/fallback",
        dt="2026-02-20",
        message_limit=2,
    )

    ticks_path = tmp_path / "raw" / "realtime_ticks" / "dt=2026-02-20" / "data.jsonl"
    bars_1m_path = tmp_path / "raw" / "realtime_bars_1m" / "dt=2026-02-20" / "data.jsonl"
    bars_5m_path = tmp_path / "raw" / "realtime_bars_5m" / "dt=2026-02-20" / "data.jsonl"

    assert connector.calls == [
        {
            "url": "wss://example.test/fallback",
            "subscribe_message": None,
            "message_limit": 2,
        }
    ]
    assert summary["message_count"] == 2
    assert summary["tick_count"] == 2
    assert summary["deduped_tick_count"] == 2
    assert summary["bar_1m_count"] == 2
    assert summary["bar_5m_count"] == 1
    assert summary["output_paths"] == {
        "realtime_ticks": str(ticks_path),
        "realtime_bars_1m": str(bars_1m_path),
        "realtime_bars_5m": str(bars_5m_path),
    }
    assert ticks_path.exists()
    assert bars_1m_path.exists()
    assert bars_5m_path.exists()
    assert len(_read_jsonl(ticks_path)) == 2


def test_run_realtime_ws_job_writes_run_metrics_and_passthrough_last_stats(
    monkeypatch, tmp_path: Path
) -> None:
    aggregate_module = types.ModuleType("pipelines.aggregate_intraday_bars")
    aggregate_module.build_time_bars = lambda ticks, *args, **kwargs: []
    aggregate_module.resample_to_5m = lambda bars_1m, *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "pipelines.aggregate_intraday_bars", aggregate_module)

    def fake_generate_run_id(prefix: str = "daily") -> str:
        assert prefix == "realtime-ws"
        return "realtime-ws-20260220T120000Z"

    monkeypatch.setattr(realtime_ws_job, "generate_run_id", fake_generate_run_id)

    connector = FakeWSConnector(
        [
            {
                "event_id": "dup-1",
                "market_id": "mkt-9",
                "timestamp": "2026-02-20T12:00:10Z",
                "price": 0.40,
                "size": 1.0,
            },
            {
                "event_id": "dup-1",
                "market_id": "mkt-9",
                "timestamp": "2026-02-20T12:00:15Z",
                "price": 0.41,
                "size": 2.0,
            },
        ],
        last_stats={"messages_seen": 2, "disconnects": 0},
    )
    writer = RawWriter(tmp_path)

    summary = run_realtime_ws_job_sync(
        ws_connector=connector,
        raw_writer=writer,
        url="wss://example.test/metrics",
        dt="2026-02-20",
        message_limit=100,
    )

    metrics_path = tmp_path / "raw" / "realtime_run_metrics" / "dt=2026-02-20" / "data.jsonl"
    assert summary["run_id"] == "realtime-ws-20260220T120000Z"
    assert summary["last_stats"] == {"messages_seen": 2, "disconnects": 0}
    assert "realtime_run_metrics" not in summary["output_paths"]
    assert metrics_path.exists()
    assert _read_jsonl(metrics_path) == [
        {
            "run_id": "realtime-ws-20260220T120000Z",
            "message_count": 2,
            "tick_count": 2,
            "deduped_tick_count": 1,
            "bar_1m_count": 0,
            "bar_5m_count": 0,
            "last_stats": {"messages_seen": 2, "disconnects": 0},
        }
    ]
