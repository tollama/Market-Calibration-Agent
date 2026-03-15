#!/usr/bin/env python3
"""Bootstrap a minimal resolved-market dataset from Manifold's public API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.manifold import ManifoldConnector

_LIQUIDITY_LOW = 10_000.0
_LIQUIDITY_HIGH = 100_000.0


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, "", 0, False):
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=UTC)
        except (ValueError, OSError):
            return None
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return None
        try:
            return datetime.fromisoformat(token.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _resolved_label(record: Mapping[str, Any]) -> int | None:
    resolution = str(record.get("resolution") or "").strip().upper()
    if resolution == "YES":
        return 1
    if resolution == "NO":
        return 0
    return None


def _liquidity_bucket(open_interest: float) -> tuple[str, int]:
    if open_interest < _LIQUIDITY_LOW:
        return "LOW", 0
    if open_interest < _LIQUIDITY_HIGH:
        return "MID", 1
    return "HIGH", 2


def _tte_bucket(hours: float) -> str:
    if hours <= 6:
        return "0-6h"
    if hours <= 24:
        return "6-24h"
    if hours <= 72:
        return "24-72h"
    return "72h+"


def normalize_manifold_market_to_dataset_row(record: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(record.get("outcome_type") or "").upper() != "BINARY":
        return None
    label = _resolved_label(record)
    if label is None:
        return None

    resolution_ts = _parse_dt(record.get("resolution_time")) or _parse_dt(record.get("close_time"))
    if resolution_ts is None:
        return None

    snapshot_ts = (
        _parse_dt(record.get("close_time"))
        or _parse_dt(record.get("last_updated_time"))
        or _parse_dt(record.get("created_time"))
    )
    if snapshot_ts is None:
        snapshot_ts = resolution_ts - timedelta(hours=24)
    if snapshot_ts >= resolution_ts:
        snapshot_ts = resolution_ts - timedelta(minutes=1)

    market_prob = min(max(_to_float(record.get("probability"), 0.5), 0.0), 1.0)
    open_interest = max(_to_float(record.get("total_liquidity"), 0.0), 0.0)
    volume_24h = max(_to_float(record.get("volume24_hours") or record.get("volume_24_hours"), 0.0), 0.0)
    liquidity_bucket, liquidity_bucket_id = _liquidity_bucket(open_interest)
    tte_seconds = max((resolution_ts - snapshot_ts).total_seconds(), 60.0)
    tte_hours = tte_seconds / 3600.0
    group_slugs = record.get("group_slugs") if isinstance(record.get("group_slugs"), list) else []
    category = str(group_slugs[0]).strip().lower() if group_slugs else "unknown"
    event_id = f"manifold:{group_slugs[0]}" if group_slugs else f"manifold:{record.get('id', '')}"

    return {
        "market_id": f"manifold:{record.get('id', '')}",
        "event_id": event_id,
        "snapshot_ts": snapshot_ts.isoformat(),
        "resolution_ts": resolution_ts.isoformat(),
        "label": label,
        "market_prob": market_prob,
        "p_yes": market_prob,
        "returns": 0.0,
        "vol": 0.0,
        "volume_velocity": 0.0,
        "oi_change": 0.0,
        "tte_seconds": float(tte_seconds),
        "tte_hours": float(tte_hours),
        "tte_bucket": _tte_bucket(tte_hours),
        "horizon_hours": max(1, min(72, int(round(tte_hours)))),
        "liquidity_bucket": liquidity_bucket,
        "liquidity_bucket_id": liquidity_bucket_id,
        "open_interest": open_interest,
        "volume_24h": volume_24h,
        "category": category,
        "platform": "manifold",
        "title": str(record.get("question") or ""),
        "slug": str(record.get("slug") or ""),
        "template_group": category,
        "market_template": "binary_yes_no",
        "template_confidence": 0.0,
        "template_entity_count": 0,
    }


async def bootstrap_manifold_resolved_dataset(
    *,
    output_path: Path,
    limit: int = 1000,
    max_retries: int = 3,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    connector = ManifoldConnector(max_retries=max_retries, timeout=timeout_s)
    try:
        markets = await connector.fetch_markets(limit=limit)
    finally:
        await connector.aclose()

    rows = [
        row
        for row in (
            normalize_manifold_market_to_dataset_row(record)
            for record in markets
        )
        if row is not None
    ]
    dataset = pd.DataFrame(rows).sort_values(["resolution_ts", "market_id"]).reset_index(drop=True) if rows else pd.DataFrame()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)

    summary = {
        "output_path": str(output_path),
        "fetched_markets": int(len(markets)),
        "resolved_rows": int(len(dataset)),
        "status": "ok" if not dataset.empty else "empty",
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a resolved dataset from Manifold public markets")
    parser.add_argument(
        "--output",
        default="data/derived/resolved/bootstrap_manifold_resolved_dataset.csv",
        help="output csv path",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    summary = asyncio.run(
        bootstrap_manifold_resolved_dataset(
            output_path=Path(args.output),
            limit=int(args.limit),
            max_retries=int(args.max_retries),
            timeout_s=float(args.timeout_s),
        )
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["resolved_rows"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
