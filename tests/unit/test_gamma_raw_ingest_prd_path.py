from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import run_ingest_gamma_raw
from storage.writers import RawWriter


class _ConnectorWithRaw:
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

    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [dict(row) for row in self._markets]

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [dict(row) for row in self._events]

    async def fetch_markets_raw(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [dict(row) for row in self._markets_raw]

    async def fetch_events_raw(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [dict(row) for row in self._events_raw]


def _assert_prd_path_meta_and_legacy_output_contract(
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

    assert set(output_paths) == {
        "gamma_markets",
        "gamma_events",
        "gamma_markets_original",
        "gamma_events_original",
        "gamma/markets",
        "gamma/events",
        "gamma/markets_original",
        "gamma/events_original",
        "gamma_dt/markets",
        "gamma_dt/events",
        "gamma_dt/markets_original",
        "gamma_dt/events_original",
    }
    for dataset in ("markets", "events", "markets_original", "events_original"):
        grouped_key = f"gamma/{dataset}"
        legacy_key = f"gamma_{dataset}"
        canonical_key = f"gamma_dt/{dataset}"
        grouped_path = Path(output_paths[grouped_key])
        legacy_path = Path(output_paths[legacy_key])
        canonical_path = Path(output_paths[canonical_key])

        assert grouped_path == legacy_path
        assert grouped_path.relative_to(root).parts == (
            "raw",
            "gamma",
            dataset,
            expected_dt_partition,
            "data.jsonl",
        )
        assert canonical_path.relative_to(root).parts == (
            "raw",
            "gamma",
            expected_dt_partition,
            f"{dataset}.jsonl",
        )
        assert grouped_path.parent.name == expected_dt_partition
        assert grouped_path.parent.parent.parent == expected_prd_path.parent


def test_ingest_gamma_raw_summary_includes_prd_raw_path_meta_and_explicit_counts(
    tmp_path: Path,
) -> None:
    connector = _ConnectorWithRaw(
        markets=[
            {"record_id": "m-1", "question": "q1"},
            {"record_id": "m-2", "question": "q2"},
        ],
        events=[
            {"record_id": "e-1", "title": "event-1"},
        ],
        markets_raw=[
            {"record_id": "raw-m-1"},
            {"record_id": "raw-m-2"},
            {"record_id": "raw-m-3"},
        ],
        events_raw=[
            {"record_id": "raw-e-1"},
            {"record_id": "raw-e-2"},
            {"record_id": "raw-e-3"},
            {"record_id": "raw-e-4"},
        ],
    )
    writer = RawWriter(tmp_path)
    dt = "2026-02-23"

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt=dt,
    )

    _assert_prd_path_meta_and_legacy_output_contract(
        root=tmp_path,
        dt=dt,
        path_meta=summary["path_meta"],
        output_paths=summary["output_paths"],
    )
    assert summary["normalized_record_count"] == 3
    assert summary["original_record_count"] == 7
    assert summary["raw_record_count"] == 10
