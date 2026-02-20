from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol


class _GammaConnector(Protocol):
    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
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


async def ingest_gamma_raw(
    *,
    connector: _GammaConnector,
    raw_writer: _RawWriter,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
    market_params: Mapping[str, Any] | None = None,
    event_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    markets, events = await asyncio.gather(
        connector.fetch_markets(limit=market_limit, params=market_params),
        connector.fetch_events(limit=event_limit, params=event_params),
    )

    markets_path = raw_writer.write(
        markets,
        dataset="gamma/markets",
        dt=dt,
        dedupe_key="record_id",
    )
    events_path = raw_writer.write(
        events,
        dataset="gamma/events",
        dt=dt,
        dedupe_key="record_id",
    )

    return {
        "market_count": len(markets),
        "event_count": len(events),
        "output_paths": {
            "gamma_markets": str(markets_path),
            "gamma_events": str(events_path),
            "gamma/markets": str(markets_path),
            "gamma/events": str(events_path),
        },
    }


def run_ingest_gamma_raw(
    *,
    connector: _GammaConnector,
    raw_writer: _RawWriter,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
    market_params: Mapping[str, Any] | None = None,
    event_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        ingest_gamma_raw(
            connector=connector,
            raw_writer=raw_writer,
            dt=dt,
            market_limit=market_limit,
            event_limit=event_limit,
            market_params=market_params,
            event_params=event_params,
        )
    )
