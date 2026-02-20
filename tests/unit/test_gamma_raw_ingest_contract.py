from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import run_ingest_gamma_raw
from storage.writers import RawWriter


class _ConnectorWithoutRaw:
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


class _ConnectorWithRaw(_ConnectorWithoutRaw):
    def __init__(
        self,
        *,
        markets: list[dict[str, Any]],
        events: list[dict[str, Any]],
        markets_raw: list[dict[str, Any]],
        events_raw: list[dict[str, Any]],
    ) -> None:
        super().__init__(markets=markets, events=events)
        self._markets_raw = markets_raw
        self._events_raw = events_raw
        self.market_raw_calls: list[dict[str, Any]] = []
        self.event_raw_calls: list[dict[str, Any]] = []

    async def fetch_markets_raw(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.market_raw_calls.append({"limit": limit, "params": params})
        return [dict(row) for row in self._markets_raw]

    async def fetch_events_raw(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.event_raw_calls.append({"limit": limit, "params": params})
        return [dict(row) for row in self._events_raw]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_ingest_gamma_raw_contract_falls_back_to_normalized_when_raw_methods_missing(
    tmp_path: Path,
) -> None:
    connector = _ConnectorWithoutRaw(
        markets=[
            {"record_id": "m-1", "question": "q1"},
            {"record_id": "m-2", "question": "q2"},
        ],
        events=[
            {"record_id": "e-1", "title": "event-1"},
            {"record_id": "e-2", "title": "event-2"},
        ],
    )
    writer = RawWriter(tmp_path)

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt="2026-02-20",
        market_limit=11,
        event_limit=22,
        market_params={"active": True},
        event_params={"closed": False},
    )

    output_paths = summary["output_paths"]
    markets_original_path = Path(output_paths["gamma/markets_original"])
    events_original_path = Path(output_paths["gamma/events_original"])

    assert connector.market_calls == [{"limit": 11, "params": {"active": True}}]
    assert connector.event_calls == [{"limit": 22, "params": {"closed": False}}]
    assert summary["dataset_counts"] == {
        "gamma/markets": 2,
        "gamma/events": 2,
        "gamma/markets_original": 2,
        "gamma/events_original": 2,
    }
    assert _read_jsonl(markets_original_path) == [
        {"record_id": "m-1", "question": "q1"},
        {"record_id": "m-2", "question": "q2"},
    ]
    assert _read_jsonl(events_original_path) == [
        {"record_id": "e-1", "title": "event-1"},
        {"record_id": "e-2", "title": "event-2"},
    ]


def test_ingest_gamma_raw_contract_uses_raw_methods_for_original_datasets(tmp_path: Path) -> None:
    connector = _ConnectorWithRaw(
        markets=[
            {"record_id": "m-1", "question": "normalized-market"},
        ],
        events=[
            {"record_id": "e-1", "title": "normalized-event"},
        ],
        markets_raw=[
            {"record_id": "raw-m-1", "payload": {"price": 0.31}},
            {"record_id": "raw-m-2", "payload": {"price": 0.42}},
        ],
        events_raw=[
            {"record_id": "raw-e-1", "payload": {"status": "open"}},
        ],
    )
    writer = RawWriter(tmp_path)

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt="2026-02-21",
        market_limit=33,
        event_limit=44,
        market_params={"archived": False},
        event_params={"include_markets": True},
    )

    output_paths = summary["output_paths"]
    markets_path = Path(output_paths["gamma/markets"])
    events_path = Path(output_paths["gamma/events"])
    markets_original_path = Path(output_paths["gamma/markets_original"])
    events_original_path = Path(output_paths["gamma/events_original"])

    assert connector.market_calls == [{"limit": 33, "params": {"archived": False}}]
    assert connector.event_calls == [{"limit": 44, "params": {"include_markets": True}}]
    assert connector.market_raw_calls == [{"limit": 33, "params": {"archived": False}}]
    assert connector.event_raw_calls == [{"limit": 44, "params": {"include_markets": True}}]
    assert summary["dataset_counts"] == {
        "gamma/markets": 1,
        "gamma/events": 1,
        "gamma/markets_original": 2,
        "gamma/events_original": 1,
    }
    assert _read_jsonl(markets_path) == [
        {"record_id": "m-1", "question": "normalized-market"},
    ]
    assert _read_jsonl(events_path) == [
        {"record_id": "e-1", "title": "normalized-event"},
    ]
    assert _read_jsonl(markets_original_path) == [
        {"record_id": "raw-m-1", "payload": {"price": 0.31}},
        {"record_id": "raw-m-2", "payload": {"price": 0.42}},
    ]
    assert _read_jsonl(events_original_path) == [
        {"record_id": "raw-e-1", "payload": {"status": "open"}},
    ]
