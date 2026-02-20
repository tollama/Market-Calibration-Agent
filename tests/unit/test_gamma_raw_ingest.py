from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import ingest_gamma_raw, run_ingest_gamma_raw
from storage.writers import RawWriter


class FakeAsyncConnector:
    def __init__(
        self,
        *,
        markets: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> None:
        self._markets = markets
        self._events = events
        self.market_calls: list[dict[str, Any]] = []
        self.event_calls: list[dict[str, Any]] = []

    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.market_calls.append({"limit": limit, "params": params})
        return [dict(row) for row in self._markets]

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.event_calls.append({"limit": limit, "params": params})
        return [dict(row) for row in self._events]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_ingest_gamma_raw_fetches_writes_and_dedupes(tmp_path: Path) -> None:
    connector = FakeAsyncConnector(
        markets=[
            {"record_id": "m-1", "question": "q1"},
            {"record_id": "m-1", "question": "q1-updated"},
            {"record_id": "m-2", "question": "q2"},
        ],
        events=[
            {"record_id": "e-1", "title": "event-1"},
            {"record_id": "e-1", "title": "event-1-updated"},
        ],
    )
    writer = RawWriter(tmp_path)

    summary = asyncio.run(
        ingest_gamma_raw(
            connector=connector,
            raw_writer=writer,
            dt="2026-02-20",
            market_limit=10,
            event_limit=20,
            market_params={"active": True},
            event_params={"closed": False},
        )
    )

    markets_path = tmp_path / "raw" / "gamma" / "markets" / "dt=2026-02-20" / "data.jsonl"
    events_path = tmp_path / "raw" / "gamma" / "events" / "dt=2026-02-20" / "data.jsonl"
    markets_original_path = (
        tmp_path / "raw" / "gamma" / "markets_original" / "dt=2026-02-20" / "data.jsonl"
    )
    events_original_path = (
        tmp_path / "raw" / "gamma" / "events_original" / "dt=2026-02-20" / "data.jsonl"
    )

    assert connector.market_calls == [{"limit": 10, "params": {"active": True}}]
    assert connector.event_calls == [{"limit": 20, "params": {"closed": False}}]

    assert summary["market_count"] == 3
    assert summary["event_count"] == 2
    assert summary["dataset_counts"] == {
        "gamma/markets": 3,
        "gamma/events": 2,
        "gamma/markets_original": 3,
        "gamma/events_original": 2,
    }
    assert summary["output_paths"] == {
        "gamma_markets": str(markets_path),
        "gamma_events": str(events_path),
        "gamma_markets_original": str(markets_original_path),
        "gamma_events_original": str(events_original_path),
        "gamma/markets": str(markets_path),
        "gamma/events": str(events_path),
        "gamma/markets_original": str(markets_original_path),
        "gamma/events_original": str(events_original_path),
    }

    assert _read_jsonl(markets_path) == [
        {"record_id": "m-1", "question": "q1-updated"},
        {"record_id": "m-2", "question": "q2"},
    ]
    assert _read_jsonl(events_path) == [
        {"record_id": "e-1", "title": "event-1-updated"},
    ]
    assert _read_jsonl(markets_original_path) == [
        {"record_id": "m-1", "question": "q1"},
        {"record_id": "m-1", "question": "q1-updated"},
        {"record_id": "m-2", "question": "q2"},
    ]
    assert _read_jsonl(events_original_path) == [
        {"record_id": "e-1", "title": "event-1"},
        {"record_id": "e-1", "title": "event-1-updated"},
    ]


def test_run_ingest_gamma_raw_uses_defaults(tmp_path: Path) -> None:
    connector = FakeAsyncConnector(
        markets=[{"record_id": "m-1", "question": "q1"}],
        events=[{"record_id": "e-1", "title": "event-1"}],
    )
    writer = RawWriter(tmp_path)

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt="2026-02-21",
    )

    markets_path = tmp_path / "raw" / "gamma" / "markets" / "dt=2026-02-21" / "data.jsonl"
    events_path = tmp_path / "raw" / "gamma" / "events" / "dt=2026-02-21" / "data.jsonl"
    markets_original_path = (
        tmp_path / "raw" / "gamma" / "markets_original" / "dt=2026-02-21" / "data.jsonl"
    )
    events_original_path = (
        tmp_path / "raw" / "gamma" / "events_original" / "dt=2026-02-21" / "data.jsonl"
    )

    assert connector.market_calls == [{"limit": 500, "params": None}]
    assert connector.event_calls == [{"limit": 500, "params": None}]
    assert summary["market_count"] == 1
    assert summary["event_count"] == 1
    assert summary["dataset_counts"] == {
        "gamma/markets": 1,
        "gamma/events": 1,
        "gamma/markets_original": 1,
        "gamma/events_original": 1,
    }
    assert summary["output_paths"] == {
        "gamma_markets": str(markets_path),
        "gamma_events": str(events_path),
        "gamma_markets_original": str(markets_original_path),
        "gamma_events_original": str(events_original_path),
        "gamma/markets": str(markets_path),
        "gamma/events": str(events_path),
        "gamma/markets_original": str(markets_original_path),
        "gamma/events_original": str(events_original_path),
    }
    assert markets_path.exists()
    assert events_path.exists()
    assert markets_original_path.exists()
    assert events_original_path.exists()
