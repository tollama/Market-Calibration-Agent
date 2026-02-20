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


class _GammaConnectorRaw(Protocol):
    async def fetch_markets_raw(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    async def fetch_events_raw(
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


def _clone_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _canonical_filename(dataset: str) -> str:
    if dataset.startswith("gamma/"):
        dataset = dataset.split("/", 1)[1]
    return f"{dataset}.jsonl"


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
    markets = _clone_rows(markets)
    events = _clone_rows(events)

    markets_original = _clone_rows(markets)
    events_original = _clone_rows(events)

    raw_fetches: list[tuple[str, Any]] = []
    fetch_markets_raw = getattr(connector, "fetch_markets_raw", None)
    fetch_events_raw = getattr(connector, "fetch_events_raw", None)
    if callable(fetch_markets_raw):
        raw_fetches.append(
            (
                "markets",
                fetch_markets_raw(limit=market_limit, params=market_params),
            )
        )
    if callable(fetch_events_raw):
        raw_fetches.append(
            (
                "events",
                fetch_events_raw(limit=event_limit, params=event_params),
            )
        )
    if raw_fetches:
        raw_results = await asyncio.gather(*(fetch_call for _, fetch_call in raw_fetches))
        for (dataset_kind, _), raw_rows in zip(raw_fetches, raw_results):
            if dataset_kind == "markets":
                markets_original = _clone_rows(raw_rows)
                continue
            events_original = _clone_rows(raw_rows)

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
    markets_original_path = raw_writer.write(
        markets_original,
        dataset="gamma/markets_original",
        dt=dt,
    )
    events_original_path = raw_writer.write(
        events_original,
        dataset="gamma/events_original",
        dt=dt,
    )

    # PRD1 I-01 canonical partition contract: raw/gamma/dt=YYYY-MM-DD/*.jsonl
    canonical_markets_path = raw_writer.write(
        markets,
        dataset="gamma",
        dt=dt,
        filename=_canonical_filename("gamma/markets"),
        dedupe_key="record_id",
    )
    canonical_events_path = raw_writer.write(
        events,
        dataset="gamma",
        dt=dt,
        filename=_canonical_filename("gamma/events"),
        dedupe_key="record_id",
    )
    canonical_markets_original_path = raw_writer.write(
        markets_original,
        dataset="gamma",
        dt=dt,
        filename=_canonical_filename("gamma/markets_original"),
    )
    canonical_events_original_path = raw_writer.write(
        events_original,
        dataset="gamma",
        dt=dt,
        filename=_canonical_filename("gamma/events_original"),
    )

    normalized_record_count = len(markets) + len(events)
    original_record_count = len(markets_original) + len(events_original)
    raw_record_count = normalized_record_count + original_record_count

    dt_partition = canonical_markets_path.parent.name
    prd_raw_partition_path = canonical_markets_path.parent
    prd_raw_partition_relpath = str(Path("raw") / "gamma" / dt_partition)

    return {
        "market_count": len(markets),
        "event_count": len(events),
        "raw_record_count": raw_record_count,
        "original_record_count": original_record_count,
        "normalized_record_count": normalized_record_count,
        "dataset_counts": {
            "gamma/markets": len(markets),
            "gamma/events": len(events),
            "gamma/markets_original": len(markets_original),
            "gamma/events_original": len(events_original),
        },
        "path_meta": {
            "raw_gamma_dt_path": str(prd_raw_partition_path),
            "raw_gamma_dt_relpath": prd_raw_partition_relpath,
        },
        "output_paths": {
            "gamma_markets": str(markets_path),
            "gamma_events": str(events_path),
            "gamma_markets_original": str(markets_original_path),
            "gamma_events_original": str(events_original_path),
            "gamma/markets": str(markets_path),
            "gamma/events": str(events_path),
            "gamma/markets_original": str(markets_original_path),
            "gamma/events_original": str(events_original_path),
            "gamma_dt/markets": str(canonical_markets_path),
            "gamma_dt/events": str(canonical_events_path),
            "gamma_dt/markets_original": str(canonical_markets_original_path),
            "gamma_dt/events_original": str(canonical_events_original_path),
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
