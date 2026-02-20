"""Batch writer for postmortem markdown reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from reports.postmortem import write_postmortem_markdown


def _extract_market_id(event: Mapping[str, Any]) -> str | None:
    value = event.get("market_id")
    if value is None:
        return None
    market_id = str(value).strip()
    return market_id or None


def build_and_write_postmortems(
    events: Iterable[Mapping[str, Any] | Any],
    *,
    root: str | Path,
) -> dict[str, object]:
    """Write postmortem markdown files for events that include a market_id."""

    output_paths: list[str] = []
    skipped_count = 0

    for event in events:
        if not isinstance(event, Mapping):
            skipped_count += 1
            continue

        market_id = _extract_market_id(event)
        if market_id is None:
            skipped_count += 1
            continue

        output_path = write_postmortem_markdown(dict(event), root=root, market_id=market_id)
        output_paths.append(str(output_path))

    output_paths.sort()
    return {
        "written_count": len(output_paths),
        "skipped_count": skipped_count,
        "output_paths": output_paths,
    }


__all__ = ["build_and_write_postmortems"]
