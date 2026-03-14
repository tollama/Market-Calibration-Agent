"""Multi-platform ingestion orchestrator.

Runs raw data ingestion across all enabled platforms defined in config,
aggregating per-platform results into a single summary.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from schemas.enums import Platform

from .ingest_platform_raw import ingest_platform_raw

logger = logging.getLogger(__name__)


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


async def run_multi_platform_ingest(
    *,
    config: dict[str, Any],
    raw_writer: _RawWriter,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
) -> dict[str, dict[str, Any]]:
    """Run raw ingestion for all enabled platforms.

    Parameters
    ----------
    config:
        Full application config dict. Expected to have a ``platforms`` key
        containing per-platform configuration.
    raw_writer:
        Storage writer for persisting raw records.
    dt:
        Date partition override.
    market_limit, event_limit:
        Max records to fetch per entity type per platform.

    Returns
    -------
    dict mapping platform name to its ingestion result summary.
    """
    from connectors.factory import create_connector

    platforms_config = config.get("platforms", {})
    results: dict[str, dict[str, Any]] = {}

    for platform_name, platform_config in platforms_config.items():
        if not platform_config.get("enabled", False):
            logger.info("Skipping disabled platform: %s", platform_name)
            continue

        try:
            platform = Platform(platform_name)
        except ValueError:
            logger.warning("Unknown platform in config: %s", platform_name)
            continue

        try:
            connector = create_connector(platform, config=platform_config)
        except Exception:
            logger.exception("Failed to create connector for %s", platform_name)
            results[platform_name] = {"error": f"Failed to create connector for {platform_name}"}
            continue

        try:
            result = await ingest_platform_raw(
                connector=connector,
                raw_writer=raw_writer,
                platform=platform_name,
                dt=dt,
                market_limit=market_limit,
                event_limit=event_limit,
            )
            results[platform_name] = result
            logger.info(
                "Ingested %d markets + %d events from %s",
                result.get("market_count", 0),
                result.get("event_count", 0),
                platform_name,
            )
        except Exception:
            logger.exception("Ingestion failed for %s", platform_name)
            results[platform_name] = {"error": f"Ingestion failed for {platform_name}"}
        finally:
            aclose = getattr(connector, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:
                    pass

    return results


def run_multi_platform_ingest_sync(
    *,
    config: dict[str, Any],
    raw_writer: _RawWriter,
    dt: date | datetime | str | None = None,
    market_limit: int = 500,
    event_limit: int = 500,
) -> dict[str, dict[str, Any]]:
    """Synchronous wrapper around :func:`run_multi_platform_ingest`."""
    return asyncio.run(
        run_multi_platform_ingest(
            config=config,
            raw_writer=raw_writer,
            dt=dt,
            market_limit=market_limit,
            event_limit=event_limit,
        )
    )
