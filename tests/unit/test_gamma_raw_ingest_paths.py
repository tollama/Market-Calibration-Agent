from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import run_ingest_gamma_raw
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


def test_ingest_gamma_raw_writes_grouped_paths_and_legacy_aliases(tmp_path: Path) -> None:
    connector = FakeAsyncConnector(
        markets=[{"record_id": "m-1"}],
        events=[{"record_id": "e-1"}],
    )
    writer = RawWriter(tmp_path)

    summary = run_ingest_gamma_raw(
        connector=connector,
        raw_writer=writer,
        dt="2026-02-22",
    )

    output_paths = summary["output_paths"]
    markets_path = Path(output_paths["gamma/markets"])
    events_path = Path(output_paths["gamma/events"])

    assert markets_path.relative_to(tmp_path).parts[:3] == ("raw", "gamma", "markets")
    assert events_path.relative_to(tmp_path).parts[:3] == ("raw", "gamma", "events")

    assert output_paths["gamma_markets"] == str(markets_path)
    assert output_paths["gamma_events"] == str(events_path)
