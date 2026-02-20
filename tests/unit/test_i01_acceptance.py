from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import run_ingest_gamma_raw
from storage.writers import RawWriter


class _FakeConnectorWithRaw:
    def __init__(
        self,
        *,
        markets: list[dict[str, Any]],
        events: list[dict[str, Any]],
        markets_raw: list[dict[str, Any]],
        events_raw: list[dict[str, Any]],
    ) -> None:
        self._markets = markets
        self._events = events
        self._markets_raw = markets_raw
        self._events_raw = events_raw
        self.market_calls: list[dict[str, Any]] = []
        self.event_calls: list[dict[str, Any]] = []
        self.market_raw_calls: list[dict[str, Any]] = []
        self.event_raw_calls: list[dict[str, Any]] = []

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


class _FakeConnectorWithoutRaw:
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
    rows = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in rows]


def _assert_output_path_contract(
    *,
    root: Path,
    dt: str,
    output_paths: Mapping[str, str],
) -> dict[str, Path]:
    expected = {
        "markets": root / "raw" / "gamma" / "markets" / f"dt={dt}" / "data.jsonl",
        "events": root / "raw" / "gamma" / "events" / f"dt={dt}" / "data.jsonl",
        "markets_original": root
        / "raw"
        / "gamma"
        / "markets_original"
        / f"dt={dt}"
        / "data.jsonl",
        "events_original": root
        / "raw"
        / "gamma"
        / "events_original"
        / f"dt={dt}"
        / "data.jsonl",
    }
    assert set(output_paths) == {
        "gamma_markets",
        "gamma_events",
        "gamma_markets_original",
        "gamma_events_original",
        "gamma/markets",
        "gamma/events",
        "gamma/markets_original",
        "gamma/events_original",
    }
    for dataset, expected_path in expected.items():
        grouped_key = f"gamma/{dataset}"
        legacy_key = f"gamma_{dataset}"
        assert output_paths[grouped_key] == output_paths[legacy_key]
        assert output_paths[grouped_key] == str(expected_path)
        assert output_paths[legacy_key] == str(expected_path)
        assert expected_path.relative_to(root).parts == (
            "raw",
            "gamma",
            dataset,
            f"dt={dt}",
            "data.jsonl",
        )
    return expected


def _assert_path_meta_contract(
    *,
    root: Path,
    dt: str,
    path_meta: Mapping[str, str],
    output_paths: Mapping[str, str],
) -> None:
    expected_dt_partition = f"dt={dt}"
    expected_prd_path = root / "raw" / "gamma" / expected_dt_partition
    expected_prd_relpath = Path("raw") / "gamma" / expected_dt_partition

    assert set(path_meta) == {"raw_gamma_dt_path", "raw_gamma_dt_relpath"}
    assert path_meta["raw_gamma_dt_path"] == str(expected_prd_path)
    assert path_meta["raw_gamma_dt_relpath"] == expected_prd_relpath.as_posix()
    assert Path(path_meta["raw_gamma_dt_path"]).relative_to(root) == expected_prd_relpath
    assert Path(path_meta["raw_gamma_dt_relpath"]) == expected_prd_relpath

    for dataset in ("markets", "events", "markets_original", "events_original"):
        grouped_path = Path(output_paths[f"gamma/{dataset}"])
        assert grouped_path.parent.name == expected_dt_partition
        assert grouped_path.parent.parent.parent == expected_prd_path.parent


def test_i01_acceptance_preserves_raw_normalized_original_and_summary_contract(
    tmp_path: Path,
) -> None:
    connector = _FakeConnectorWithRaw(
        markets=[
            {"record_id": "m-1", "question": "q1", "yes_price": 0.41},
            {"record_id": "m-1", "question": "q1-updated", "yes_price": 0.55},
            {"record_id": "m-2", "question": "q2", "yes_price": 0.23},
        ],
        events=[
            {"record_id": "e-1", "title": "event-1", "status": "open"},
            {"record_id": "e-1", "title": "event-1-updated", "status": "resolved"},
            {"record_id": "e-2", "title": "event-2", "status": "open"},
        ],
        markets_raw=[
            {"id": "raw-m-1", "record_id": "m-1", "payload": {"yes_price": "0.41"}},
            {"id": "raw-m-2", "record_id": "m-1", "payload": {"yes_price": "0.55"}},
            {"id": "raw-m-3", "record_id": "m-2", "payload": {"yes_price": "0.23"}},
        ],
        events_raw=[
            {"id": "raw-e-1", "record_id": "e-1", "payload": {"status": "open"}},
            {"id": "raw-e-2", "record_id": "e-1", "payload": {"status": "resolved"}},
            {"id": "raw-e-3", "record_id": "e-2", "payload": {"status": "open"}},
        ],
    )
    writer = RawWriter(tmp_path)
    dt = "2026-02-20"

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt=dt,
        market_limit=111,
        event_limit=222,
        market_params={"active": True},
        event_params={"closed": False},
    )

    assert set(summary) == {
        "market_count",
        "event_count",
        "raw_record_count",
        "original_record_count",
        "normalized_record_count",
        "dataset_counts",
        "path_meta",
        "output_paths",
    }
    assert connector.market_calls == [{"limit": 111, "params": {"active": True}}]
    assert connector.event_calls == [{"limit": 222, "params": {"closed": False}}]
    assert connector.market_raw_calls == [{"limit": 111, "params": {"active": True}}]
    assert connector.event_raw_calls == [{"limit": 222, "params": {"closed": False}}]
    assert summary["market_count"] == 3
    assert summary["event_count"] == 3
    assert summary["normalized_record_count"] == 6
    assert summary["original_record_count"] == 6
    assert summary["raw_record_count"] == 12
    assert summary["dataset_counts"] == {
        "gamma/markets": 3,
        "gamma/events": 3,
        "gamma/markets_original": 3,
        "gamma/events_original": 3,
    }

    expected_paths = _assert_output_path_contract(
        root=tmp_path,
        dt=dt,
        output_paths=summary["output_paths"],
    )
    _assert_path_meta_contract(
        root=tmp_path,
        dt=dt,
        path_meta=summary["path_meta"],
        output_paths=summary["output_paths"],
    )

    assert _read_jsonl(expected_paths["markets"]) == [
        {"record_id": "m-1", "question": "q1-updated", "yes_price": 0.55},
        {"record_id": "m-2", "question": "q2", "yes_price": 0.23},
    ]
    assert _read_jsonl(expected_paths["events"]) == [
        {"record_id": "e-1", "title": "event-1-updated", "status": "resolved"},
        {"record_id": "e-2", "title": "event-2", "status": "open"},
    ]
    assert _read_jsonl(expected_paths["markets_original"]) == [
        {"id": "raw-m-1", "record_id": "m-1", "payload": {"yes_price": "0.41"}},
        {"id": "raw-m-2", "record_id": "m-1", "payload": {"yes_price": "0.55"}},
        {"id": "raw-m-3", "record_id": "m-2", "payload": {"yes_price": "0.23"}},
    ]
    assert _read_jsonl(expected_paths["events_original"]) == [
        {"id": "raw-e-1", "record_id": "e-1", "payload": {"status": "open"}},
        {"id": "raw-e-2", "record_id": "e-1", "payload": {"status": "resolved"}},
        {"id": "raw-e-3", "record_id": "e-2", "payload": {"status": "open"}},
    ]


def test_i01_acceptance_falls_back_to_normalized_when_raw_methods_are_missing(
    tmp_path: Path,
) -> None:
    connector = _FakeConnectorWithoutRaw(
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
    dt = "2026-02-21"

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt=dt,
        market_limit=11,
        event_limit=22,
    )

    assert connector.market_calls == [{"limit": 11, "params": None}]
    assert connector.event_calls == [{"limit": 22, "params": None}]
    assert summary["normalized_record_count"] == 5
    assert summary["original_record_count"] == 5
    assert summary["raw_record_count"] == 10
    assert summary["dataset_counts"] == {
        "gamma/markets": 3,
        "gamma/events": 2,
        "gamma/markets_original": 3,
        "gamma/events_original": 2,
    }

    expected_paths = _assert_output_path_contract(
        root=tmp_path,
        dt=dt,
        output_paths=summary["output_paths"],
    )
    _assert_path_meta_contract(
        root=tmp_path,
        dt=dt,
        path_meta=summary["path_meta"],
        output_paths=summary["output_paths"],
    )
    assert _read_jsonl(expected_paths["markets"]) == [
        {"record_id": "m-1", "question": "q1-updated"},
        {"record_id": "m-2", "question": "q2"},
    ]
    assert _read_jsonl(expected_paths["events"]) == [
        {"record_id": "e-1", "title": "event-1-updated"},
    ]
    assert _read_jsonl(expected_paths["markets_original"]) == [
        {"record_id": "m-1", "question": "q1"},
        {"record_id": "m-1", "question": "q1-updated"},
        {"record_id": "m-2", "question": "q2"},
    ]
    assert _read_jsonl(expected_paths["events_original"]) == [
        {"record_id": "e-1", "title": "event-1"},
        {"record_id": "e-1", "title": "event-1-updated"},
    ]
