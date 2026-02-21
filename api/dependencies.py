"""Dependency providers and local derived-data loaders for API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schemas import MarketDetailResponse, MarketMetricsResponse


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


def _parse_record_datetime(record: Dict[str, Any], field: str) -> Optional[datetime]:
    value = record.get(field)
    if not isinstance(value, str):
        return None
    try:
        return _parse_iso_datetime(value)
    except ValueError:
        return None


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

    def _scan_partition_records(
        self,
        *,
        root: Path,
        filename: str,
    ) -> List[Dict[str, Any]]:
        partition_files = sorted(
            root.glob(f"dt=*/{filename}"),
            key=lambda path: (path.parent.name, str(path)),
            reverse=True,
        )
        merged: List[Dict[str, Any]] = []
        for path in partition_files:
            merged.extend(_read_records(path))
        return merged

    def _dedupe_alert_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen_keys: set[Tuple[str, ...]] = set()

        for record in records:
            dedupe_key: Optional[Tuple[str, ...]] = None

            alert_id = record.get("alert_id")
            if alert_id not in (None, ""):
                dedupe_key = ("alert_id", str(alert_id))
            else:
                market_id = record.get("market_id")
                ts = record.get("ts")
                if market_id not in (None, "") and ts not in (None, ""):
                    dedupe_key = ("market_ts", str(market_id), str(ts))

            if dedupe_key is not None:
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

            deduped.append(record)

        return deduped

    def load_scoreboard(self, *, window: str) -> List[Dict[str, Any]]:
        records = _read_records(self.scoreboard_path)
        if not self.scoreboard_path.exists():
            records = self._scan_partition_records(
                root=self.derived_root / "metrics",
                filename="scoreboard.json",
            )
            records.sort(
                key=lambda item: _parse_record_datetime(item, "as_of")
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

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
        if not self.alerts_path.exists():
            records = self._scan_partition_records(
                root=self.derived_root / "alerts",
                filename="alerts.json",
            )
            records = self._dedupe_alert_records(records)

        since_utc = _normalize_utc(since) if since else None

        filtered: List[Dict[str, Any]] = []
        for record in records:
            record_ts = _parse_record_datetime(record, "ts")
            if since_utc and (record_ts is None or record_ts < since_utc):
                continue
            filtered.append(record)

        filtered.sort(
            key=lambda item: _parse_record_datetime(item, "ts")
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        total = len(filtered)
        return filtered[offset : offset + limit], total

    def load_markets(self) -> List[MarketDetailResponse]:
        score_90 = self.load_scoreboard(window="90d")
        alerts, _ = self.load_alerts(since=None, limit=1000, offset=0)

        by_id: Dict[str, Dict[str, Any]] = {}
        for row in score_90:
            market_id = str(row.get("market_id") or "")
            if not market_id:
                continue
            by_id.setdefault(market_id, {})
            by_id[market_id].update(
                {
                    "market_id": market_id,
                    "category": row.get("category"),
                    "liquidity_bucket": row.get("liquidity_bucket"),
                    "trust_score": row.get("trust_score"),
                    "as_of": row.get("as_of"),
                }
            )

        latest_alert: Dict[str, Dict[str, Any]] = {}
        for row in alerts:
            market_id = str(row.get("market_id") or "")
            if market_id and market_id not in latest_alert:
                latest_alert[market_id] = row

        for market_id, alert in latest_alert.items():
            by_id.setdefault(market_id, {"market_id": market_id})
            by_id[market_id]["latest_alert"] = alert

        return [MarketDetailResponse(**item) for item in sorted(by_id.values(), key=lambda x: str(x["market_id"]))]

    def load_market(self, market_id: str) -> Optional[MarketDetailResponse]:
        for market in self.load_markets():
            if market.market_id == market_id:
                return market
        return None

    def load_market_metrics(self, market_id: str) -> Optional[MarketMetricsResponse]:
        all_rows = _read_records(self.scoreboard_path)
        windows = [row for row in all_rows if str(row.get("market_id")) == market_id]
        if not windows:
            return None

        alerts, _ = self.load_alerts(since=None, limit=1000, offset=0)
        market_alerts = [a for a in alerts if str(a.get("market_id")) == market_id]
        severity_counts: Dict[str, int] = {}
        for row in market_alerts:
            sev = str(row.get("severity") or "UNKNOWN").upper()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return MarketMetricsResponse(
            market_id=market_id,
            scoreboard_by_window=windows,
            alert_total=len(market_alerts),
            alert_severity_counts=severity_counts,
        )

    def load_postmortem(self, *, market_id: str) -> Tuple[str, Path]:
        dated_candidates: List[Tuple[datetime, Path]] = []
        for candidate in self.postmortem_dir.glob(f"{market_id}_*.md"):
            resolved_date = candidate.stem.removeprefix(f"{market_id}_")
            try:
                parsed_date = datetime.strptime(resolved_date, "%Y-%m-%d")
            except ValueError:
                continue
            dated_candidates.append((parsed_date, candidate))

        if dated_candidates:
            _, path = max(dated_candidates, key=lambda item: (item[0], str(item[1])))
        else:
            path = self.postmortem_dir / f"{market_id}.md"

        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8"), path


def get_derived_root() -> Path:
    return Path(os.getenv("DERIVED_DIR", "data/derived")).resolve()


def get_derived_store() -> LocalDerivedStore:
    return LocalDerivedStore(derived_root=get_derived_root())
