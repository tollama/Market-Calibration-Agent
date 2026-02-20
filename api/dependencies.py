"""Dependency providers and local derived-data loaders for API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    return _normalize_utc(datetime.fromisoformat(normalized))


def _read_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8").strip()
    if raw == "":
        return []

    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        records: List[Dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        return [loaded]
    return []


class LocalDerivedStore:
    """Read-only loader for derived artifacts used by the API."""

    def __init__(self, derived_root: Path) -> None:
        self.derived_root = derived_root

    @property
    def scoreboard_path(self) -> Path:
        return self.derived_root / "metrics" / "scoreboard.json"

    @property
    def alerts_path(self) -> Path:
        return self.derived_root / "alerts" / "alerts.json"

    @property
    def postmortem_dir(self) -> Path:
        return self.derived_root / "reports" / "postmortem"

    def load_scoreboard(self, *, window: str) -> List[Dict[str, Any]]:
        records = _read_records(self.scoreboard_path)
        filtered = [
            record
            for record in records
            if str(record.get("window", window)) == window
        ]
        return filtered

    def load_alerts(
        self,
        *,
        since: Optional[datetime],
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        records = _read_records(self.alerts_path)
        since_utc = _normalize_utc(since) if since else None

        filtered: List[Dict[str, Any]] = []
        for record in records:
            record_ts = _parse_iso_datetime(str(record.get("ts")))
            if since_utc and (record_ts is None or record_ts < since_utc):
                continue
            filtered.append(record)

        # newest first for feed semantics
        filtered.sort(
            key=lambda item: _parse_iso_datetime(str(item.get("ts"))) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        total = len(filtered)
        return filtered[offset : offset + limit], total

    def load_postmortem(self, *, market_id: str) -> Tuple[str, Path]:
        path = self.postmortem_dir / f"{market_id}.md"
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8"), path


def get_derived_root() -> Path:
    return Path(os.getenv("DERIVED_DIR", "data/derived")).resolve()


def get_derived_store() -> LocalDerivedStore:
    return LocalDerivedStore(derived_root=get_derived_root())
