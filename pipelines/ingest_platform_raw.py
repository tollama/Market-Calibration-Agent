"""Platform-agnostic raw data ingestion pipeline.

Generalizes ``ingest_gamma_raw`` to work with any platform connector
that satisfies the ``MarketDataConnector`` protocol. The existing
``ingest_gamma_raw`` remains untouched for backward compatibility.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol


class _MarketDataConnector(Protocol):
    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


class _RawWriter(Protocol):
    def write(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.jsonl",
        dedupe_key: str | None = None,
    ) -> Path: ...


def _clone_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


async def ingest_platform_raw(
    *,
    connector: _MarketDataConnector,
    raw_writer: _RawWriter,
    platform: str,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
    market_params: Mapping[str, Any] | None = None,
    event_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest raw market and event data for any supported platform.

    Writes to ``raw/{platform}/dt=YYYY-MM-DD/{markets,events}.jsonl``.

    Parameters
    ----------
    connector:
        Any connector satisfying the ``MarketDataConnector`` protocol.
    raw_writer:
        Storage writer for persisting raw records.
    platform:
        Platform identifier (e.g. ``"kalshi"``, ``"manifold"``).
    dt:
        Date partition override. Defaults to today.
    market_limit, event_limit:
        Max records to fetch per entity type.
    market_params, event_params:
        Extra query parameters passed to the connector.

    Returns
    -------
    dict with ingestion summary including counts and output paths.
    """
    markets, events = await asyncio.gather(
        connector.fetch_markets(limit=market_limit, params=market_params),
        connector.fetch_events(limit=event_limit, params=event_params),
    )
    markets = _clone_rows(markets)
    events = _clone_rows(events)

    markets_path = raw_writer.write(
        markets,
        dataset=f"{platform}/markets",
        dt=dt,
        dedupe_key="record_id",
    )
    events_path = raw_writer.write(
        events,
        dataset=f"{platform}/events",
        dt=dt,
        dedupe_key="record_id",
    )

    # Canonical partition: raw/{platform}/dt=YYYY-MM-DD/*.jsonl
    canonical_markets_path = raw_writer.write(
        markets,
        dataset=platform,
        dt=dt,
        filename="markets.jsonl",
        dedupe_key="record_id",
    )
    canonical_events_path = raw_writer.write(
        events,
        dataset=platform,
        dt=dt,
        filename="events.jsonl",
        dedupe_key="record_id",
    )

    dt_partition = canonical_markets_path.parent.name
    partition_path = canonical_markets_path.parent
    partition_relpath = str(Path("raw") / platform / dt_partition)

    return {
        "platform": platform,
        "market_count": len(markets),
        "event_count": len(events),
        "raw_record_count": len(markets) + len(events),
        "dataset_counts": {
            f"{platform}/markets": len(markets),
            f"{platform}/events": len(events),
        },
        "path_meta": {
            f"raw_{platform}_dt_path": str(partition_path),
            f"raw_{platform}_dt_relpath": partition_relpath,
        },
        "output_paths": {
            f"{platform}_markets": str(markets_path),
            f"{platform}_events": str(events_path),
            f"{platform}/markets": str(markets_path),
            f"{platform}/events": str(events_path),
            f"{platform}_dt/markets": str(canonical_markets_path),
            f"{platform}_dt/events": str(canonical_events_path),
        },
    }


def run_ingest_platform_raw(
    *,
    connector: _MarketDataConnector,
    raw_writer: _RawWriter,
    platform: str,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
    market_params: Mapping[str, Any] | None = None,
    event_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper around :func:`ingest_platform_raw`."""
    return asyncio.run(
        ingest_platform_raw(
            connector=connector,
            raw_writer=raw_writer,
            platform=platform,
            dt=dt,
            market_limit=market_limit,
            event_limit=event_limit,
            market_params=market_params,
            event_params=event_params,
        )
    )
