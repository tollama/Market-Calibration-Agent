"""Publish-stage artifact writer utilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from storage.writers import ParquetWriter, RawWriter, normalize_dt


def _collect_rows(rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if rows is None:
        return []

    collected: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"rows[{idx}] must be a mapping")
        collected.append(dict(row))
    return collected


def write_publish_artifacts(
    *,
    root: str | Path,
    dt: date | datetime | str | None = None,
    scoreboard_rows: Iterable[Mapping[str, Any]] | None = None,
    alert_rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, object]:
    """Write publish-stage scoreboard and alert artifacts."""
    root_path = Path(root)
    normalized_dt = normalize_dt(dt)
    normalized_scoreboard_rows = _collect_rows(scoreboard_rows)
    normalized_alert_rows = _collect_rows(alert_rows)

    scoreboard_path: Path | None = None
    if normalized_scoreboard_rows:
        scoreboard_path = ParquetWriter(root_path).write(
            normalized_scoreboard_rows,
            dataset="metrics",
            dt=normalized_dt,
            filename="scoreboard.parquet",
        )

    alerts_path: Path | None = None
    if normalized_alert_rows:
        alerts_path = RawWriter(root_path).write(
            normalized_alert_rows,
            dataset="alerts",
            dt=normalized_dt,
            filename="alerts.jsonl",
        )

    return {
        "scoreboard_path": str(scoreboard_path) if scoreboard_path is not None else None,
        "alerts_path": str(alerts_path) if alerts_path is not None else None,
        "scoreboard_count": len(normalized_scoreboard_rows),
        "alert_count": len(normalized_alert_rows),
    }


__all__ = ["write_publish_artifacts"]
