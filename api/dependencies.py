"""Dependency providers and local derived-data loaders for API."""

from __future__ import annotations

import json
import logging
import os
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schemas import MarketDetailResponse, MarketMetricsResponse

logger = logging.getLogger(__name__)

_record_read_metrics = Counter(
    malformed_lines=0,
    non_dict_records=0,
    empty_lines=0,
    parsed_records=0,
    non_parseable_documents=0,
)


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

    local_metrics: Counter[str] = Counter()

    def _inc(key: str, amount: int = 1) -> None:
        _record_read_metrics[key] += amount
        local_metrics[key] += amount

    raw = path.read_text(encoding="utf-8")
    if raw.strip() == "":
        _inc("empty_lines", raw.count("\n") or 1)
        logger.info(
            "record_read_metrics path=%s parsed=0 malformed=0 empty=%s non_dict=0 non_parseable=0", path, local_metrics["empty_lines"]
        )
        return []

    try:
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            records = [item for item in loaded if isinstance(item, dict)]
            for _ in records:
                _inc("parsed_records")
            if len(records) < len(loaded):
                _inc("non_dict_records", len(loaded) - len(records))
            logger.debug("Parsed full-record JSON for %s with %d valid records", path, len(records))
            logger.info(
                "record_read_metrics path=%s parsed=%s malformed=%s empty=%s non_dict=%s non_parseable=%s",
                path,
                local_metrics["parsed_records"],
                local_metrics["malformed_lines"],
                local_metrics["empty_lines"],
                local_metrics["non_dict_records"],
                local_metrics["non_parseable_documents"],
            )
            return records
        if isinstance(loaded, dict):
            _inc("parsed_records")
            logger.info(
                "record_read_metrics path=%s parsed=%s malformed=%s empty=%s non_dict=%s non_parseable=%s",
                path,
                local_metrics["parsed_records"],
                local_metrics["malformed_lines"],
                local_metrics["empty_lines"],
                local_metrics["non_dict_records"],
                local_metrics["non_parseable_documents"],
            )
            return [loaded]

        _inc("non_parseable_documents")
        logger.warning("Skipping non-dict JSON document in %s", path)
        logger.info(
            "record_read_metrics path=%s parsed=%s malformed=%s empty=%s non_dict=%s non_parseable=%s",
            path,
            local_metrics["parsed_records"],
            local_metrics["malformed_lines"],
            local_metrics["empty_lines"],
            local_metrics["non_dict_records"],
            local_metrics["non_parseable_documents"],
        )
        return []
    except json.JSONDecodeError:
        records: List[Dict[str, Any]] = []
        for line_no, raw_line in enumerate(raw.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                _inc("empty_lines")
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                _inc("malformed_lines")
                logger.warning("Skipping malformed JSON in %s at line %s: %s", path, line_no, exc)
                continue

            if not isinstance(parsed, dict):
                _inc("non_dict_records")
                logger.warning(
                    "Skipping non-dict record in %s at line %s (type=%s)",
                    path,
                    line_no,
                    type(parsed).__name__,
                )
                continue

            records.append(parsed)
            _inc("parsed_records")

        logger.debug(
            "Loaded %s records from line-delimited JSON in %s (malformed=%s, empty=%s, non_dict=%s)",
            len(records),
            path,
            local_metrics["malformed_lines"],
            local_metrics["empty_lines"],
            local_metrics["non_dict_records"],
        )
        logger.info(
            "record_read_metrics path=%s parsed=%s malformed=%s empty=%s non_dict=%s non_parseable=%s",
            path,
            local_metrics["parsed_records"],
            local_metrics["malformed_lines"],
            local_metrics["empty_lines"],
            local_metrics["non_dict_records"],
            local_metrics["non_parseable_documents"],
        )
        return records


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
        self._alerts_cache_signature: tuple[tuple[str, int, int], ...] = ()
        self._alerts_sorted: list[Dict[str, Any]] = []
        self._alerts_sorted_with_ts: list[Tuple[datetime, Dict[str, Any]]] = []
        self._alerts_latest_by_market: dict[str, Dict[str, Any]] = {}

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

    def _alerts_source_signature(self) -> tuple[tuple[str, int, int], ...]:
        if self.alerts_path.exists():
            stat = self.alerts_path.stat()
            return ((str(self.alerts_path), stat.st_mtime_ns, stat.st_size),)

        partition_root = self.derived_root / "alerts"
        partitions = sorted(partition_root.glob("dt=*/alerts.json"))
        signature: list[tuple[str, int, int]] = []
        for path in partitions:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def _refresh_alerts_cache(self) -> None:
        signature = self._alerts_source_signature()
        if signature == self._alerts_cache_signature:
            return

        records = _read_records(self.alerts_path)
        if not self.alerts_path.exists():
            records = self._scan_partition_records(
                root=self.derived_root / "alerts",
                filename="alerts.json",
            )
            records = self._dedupe_alert_records(records)

        sorted_records: list[Dict[str, Any]] = sorted(
            records,
            key=lambda item: _parse_record_datetime(item, "ts")
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        sorted_with_ts = [
            (_parse_record_datetime(item, "ts") or datetime.min.replace(tzinfo=timezone.utc), item)
            for item in sorted_records
        ]

        latest_by_market: dict[str, Dict[str, Any]] = {}
        for _, item in sorted_with_ts:
            market_id = str(item.get("market_id") or "")
            if market_id and market_id not in latest_by_market:
                latest_by_market[market_id] = item

        self._alerts_cache_signature = signature
        self._alerts_sorted = sorted_records
        self._alerts_sorted_with_ts = [
            (ts, item) for ts, item in sorted_with_ts if item.get("ts") is not None
        ]
        self._alerts_latest_by_market = latest_by_market

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
        self._refresh_alerts_cache()

        since_utc = _normalize_utc(since) if since else None
        if since_utc is None:
            filtered = self._alerts_sorted
        else:
            ts_cursor = [ts.timestamp() for ts, _ in self._alerts_sorted_with_ts]
            if not ts_cursor:
                filtered = []
            else:
                since_epoch = since_utc.timestamp()
                cursor = bisect_right([-ts for ts in ts_cursor], -since_epoch)
                filtered = [item for _, item in self._alerts_sorted_with_ts[:cursor]]

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
