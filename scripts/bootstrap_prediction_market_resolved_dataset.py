#!/usr/bin/env python3
"""Bootstrap a minimal resolved dataset from all supported prediction-market connectors."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.factory import create_connector
from schemas.enums import Platform
from scripts.bootstrap_manifold_resolved_dataset import (
    _infer_category,
    _infer_event_id,
    _infer_template,
    _liquidity_bucket,
    _parse_dt,
    _tte_bucket,
    _to_float,
    normalize_manifold_market_to_dataset_row,
)

_PLATFORM_DEFAULTS: dict[Platform, dict[str, Any]] = {
    Platform.POLYMARKET: {
        "market_params": {"closed": "true"},
        "event_params": {},
        "fetch_events": False,
    },
    Platform.KALSHI: {
        "market_params": {"status": "settled"},
        "event_params": {},
        "fetch_events": True,
    },
    Platform.MANIFOLD: {
        "market_params": {},
        "event_params": {},
        "fetch_events": False,
    },
}
_SNAKE_CASE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_CASE_2 = re.compile(r"([a-z0-9])([A-Z])")
_KALSHI_CATEGORY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("KXNBA", "sports"),
    ("KXNFL", "sports"),
    ("KXNHL", "sports"),
    ("KXMLB", "sports"),
    ("KXNCAA", "sports"),
    ("KXSOCCER", "sports"),
    ("KXMVESPORT", "sports"),
    ("KXMVECROSSCATEGORY", "sports"),
    ("KXCRYPTO", "crypto"),
    ("KXBITCOIN", "crypto"),
    ("KXETH", "crypto"),
    ("KXWARMING", "weather"),
    ("KXTEMP", "weather"),
    ("KXRAIN", "weather"),
    ("KXINFLATION", "macro"),
    ("KXCPI", "macro"),
    ("KXFED", "macro"),
)


def _normalize_category_name(value: Any) -> str:
    token = str(value or "").strip().lower().replace("/", " ").replace("-", " ")
    token = "_".join(part for part in token.split() if part)
    return token or "unknown"


def _to_snake_case(value: str) -> str:
    step_1 = _SNAKE_CASE_1.sub(r"\1_\2", value)
    return _SNAKE_CASE_2.sub(r"\1_\2", step_1).replace("-", "_").lower()


def _normalize_value_to_snake_case(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _to_snake_case(str(key)): _normalize_value_to_snake_case(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_normalize_value_to_snake_case(item) for item in value]
    return value


def _safe_snapshot_ts(
    *,
    snapshot_ts: datetime | None,
    resolution_ts: datetime,
) -> datetime:
    if snapshot_ts is None:
        return resolution_ts - timedelta(hours=24)
    if snapshot_ts >= resolution_ts:
        return resolution_ts - timedelta(minutes=1)
    return snapshot_ts


def _infer_kalshi_category(record: Mapping[str, Any], event_row: Mapping[str, Any]) -> str:
    category = _normalize_category_name(event_row.get("category"))
    if category != "unknown":
        return category

    for key in ("event_ticker", "ticker"):
        token = str(record.get(key) or "").strip().upper()
        for prefix, mapped in _KALSHI_CATEGORY_PREFIXES:
            if token.startswith(prefix):
                return mapped

    haystack = " ".join(
        str(record.get(key) or "")
        for key in ("title", "yes_sub_title", "no_sub_title", "ticker", "event_ticker")
    ).lower()
    if "points scored" in haystack or "wins by over" in haystack:
        return "sports"
    return _infer_category({"question": haystack, "title": haystack, "slug": haystack})


def _parse_json_like_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _midpoint(*values: Any, default: float = 0.5) -> float:
    numeric = [float(value) for value in values if value not in (None, "")]
    if not numeric:
        return float(default)
    return float(sum(numeric) / len(numeric))


def _infer_binary_label_from_probability(prob: float) -> int | None:
    if prob >= 0.999:
        return 1
    if prob <= 0.001:
        return 0
    return None


def _build_event_lookup(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in ("event_ticker", "event_id", "ticker", "slug", "id", "record_id"):
            value = str(row.get(key) or "").strip()
            if value and value not in lookup:
                lookup[value] = row
    return lookup


def normalize_polymarket_market_to_dataset_row(
    record: Mapping[str, Any],
    *,
    event_lookup: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    outcomes = [str(item).strip().lower() for item in _parse_json_like_list(record.get("outcomes"))]
    prices = [_to_float(item, default=-1.0) for item in _parse_json_like_list(record.get("outcome_prices"))]
    if len(outcomes) != 2 or len(prices) != 2:
        return None

    try:
        yes_index = outcomes.index("yes")
        no_index = outcomes.index("no")
    except ValueError:
        return None
    if yes_index == no_index:
        return None

    yes_price = max(0.0, min(1.0, prices[yes_index]))
    label = _infer_binary_label_from_probability(yes_price)
    if label is None:
        return None

    resolution_ts = _parse_dt(record.get("closed_time")) or _parse_dt(record.get("end_date"))
    if resolution_ts is None:
        return None

    snapshot_ts = _safe_snapshot_ts(
        snapshot_ts=_parse_dt(record.get("updated_at")) or _parse_dt(record.get("created_at")),
        resolution_ts=resolution_ts,
    )
    category = _normalize_category_name(record.get("category"))

    event_rows = record.get("events")
    event_row = event_rows[0] if isinstance(event_rows, list) and event_rows else None
    if event_row is None and event_lookup is not None:
        for key in ("slug", "record_id", "id"):
            candidate = str(record.get(key) or "").strip()
            if candidate and candidate in event_lookup:
                event_row = event_lookup[candidate]
                break

    event_id = f"polymarket:{record.get('slug') or record.get('id')}"
    if isinstance(event_row, Mapping):
        event_id_value = event_row.get("id") or event_row.get("slug") or event_row.get("ticker")
        if event_id_value:
            event_id = f"polymarket:{event_id_value}"
        category = _normalize_category_name(event_row.get("category") or category)

    liquidity = _to_float(record.get("liquidity_num") or record.get("liquidity"), default=0.0)
    volume_24h = _to_float(record.get("volume24hr") or record.get("volume_24hr"), default=0.0)
    liquidity_bucket, liquidity_bucket_id = _liquidity_bucket(liquidity)
    tte_seconds = max((resolution_ts - snapshot_ts).total_seconds(), 60.0)
    tte_hours = tte_seconds / 3600.0

    previous_yes_bid = record.get("previous_yes_bid")
    previous_yes_ask = record.get("previous_yes_ask")
    market_prob = _midpoint(
        _to_float(previous_yes_bid, default=float("nan")) if previous_yes_bid not in (None, "") else None,
        _to_float(previous_yes_ask, default=float("nan")) if previous_yes_ask not in (None, "") else None,
        default=_to_float(record.get("last_trade_price"), default=yes_price),
    )
    if not (0.0 <= market_prob <= 1.0):
        market_prob = yes_price

    title = str(record.get("question") or "")
    slug = str(record.get("slug") or "")
    template_group, market_template, template_confidence, template_entity_count = _infer_template(title, slug, category)
    return {
        "market_id": f"polymarket:{record.get('id', '')}",
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
        "open_interest": liquidity,
        "volume_24h": volume_24h,
        "category": category,
        "platform": "polymarket",
        "title": title,
        "slug": slug,
        "template_group": template_group,
        "market_template": market_template,
        "template_confidence": template_confidence,
        "template_entity_count": template_entity_count,
    }


def normalize_kalshi_market_to_dataset_row(
    record: Mapping[str, Any],
    *,
    event_lookup: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if str(record.get("market_type") or "").strip().lower() != "binary":
        return None

    result = str(record.get("result") or "").strip().lower()
    if result == "yes":
        label = 1
    elif result == "no":
        label = 0
    else:
        return None

    resolution_ts = (
        _parse_dt(record.get("settlement_ts"))
        or _parse_dt(record.get("close_time"))
        or _parse_dt(record.get("expiration_time"))
    )
    if resolution_ts is None:
        return None

    snapshot_hint = _parse_dt(record.get("close_time")) or _parse_dt(record.get("updated_time")) or _parse_dt(record.get("open_time"))
    snapshot_ts = _safe_snapshot_ts(snapshot_ts=snapshot_hint, resolution_ts=resolution_ts)

    market_prob = _midpoint(
        _to_float(record.get("previous_yes_bid_dollars"), default=float("nan")) if record.get("previous_yes_bid_dollars") not in (None, "") else None,
        _to_float(record.get("previous_yes_ask_dollars"), default=float("nan")) if record.get("previous_yes_ask_dollars") not in (None, "") else None,
        default=_to_float(record.get("previous_price_dollars"), default=_to_float(record.get("last_price_dollars"), default=0.5)),
    )
    if not (0.0 <= market_prob <= 1.0):
        market_prob = _midpoint(
            _to_float(record.get("yes_bid_dollars"), default=float("nan")) if record.get("yes_bid_dollars") not in (None, "") else None,
            _to_float(record.get("yes_ask_dollars"), default=float("nan")) if record.get("yes_ask_dollars") not in (None, "") else None,
            default=0.5,
        )

    event_ticker = str(record.get("event_ticker") or "").strip()
    event_row = event_lookup.get(event_ticker, {}) if event_lookup is not None else {}
    category = _infer_kalshi_category(record, event_row)
    title = str(record.get("title") or event_row.get("title") or "")
    slug = str(record.get("ticker") or "")
    template_group, market_template, template_confidence, template_entity_count = _infer_template(title, slug, category)
    liquidity = _to_float(record.get("open_interest_fp"), default=0.0)
    volume_24h = _to_float(record.get("volume_24h_fp"), default=_to_float(record.get("volume_fp"), default=0.0))
    liquidity_bucket, liquidity_bucket_id = _liquidity_bucket(liquidity)
    tte_seconds = max((resolution_ts - snapshot_ts).total_seconds(), 60.0)
    tte_hours = tte_seconds / 3600.0
    event_id = f"kalshi:{event_ticker}" if event_ticker else f"kalshi:{record.get('ticker', '')}"
    return {
        "market_id": f"kalshi:{record.get('ticker', '')}",
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
        "open_interest": liquidity,
        "volume_24h": volume_24h,
        "category": category,
        "platform": "kalshi",
        "title": title,
        "slug": slug.lower(),
        "template_group": template_group,
        "market_template": market_template,
        "template_confidence": template_confidence,
        "template_entity_count": template_entity_count,
    }


def _fetch_polymarket_markets_fallback(
    *,
    limit: int,
    params: Mapping[str, Any],
) -> list[dict[str, Any]]:
    query = urlencode({**dict(params), "limit": int(limit)})
    url = f"https://gamma-api.polymarket.com/markets?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "curl/8.7.1",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        return []
    return [
        value
        for value in (_normalize_value_to_snake_case(item) for item in payload)
        if isinstance(value, dict)
    ]


async def _fetch_platform_records(
    *,
    platform: Platform,
    limit: int,
    config: Mapping[str, Any] | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    if verbose:
        print(f"[bootstrap] fetching {platform.value} markets/events", flush=True)
    connector = create_connector(platform, config=dict(config or {}))
    defaults = _PLATFORM_DEFAULTS[platform]
    market_params = dict(defaults["market_params"])
    event_params = dict(defaults["event_params"])
    fetch_events = bool(defaults.get("fetch_events", True))
    try:
        try:
            markets = await asyncio.wait_for(
                connector.fetch_markets(limit=limit, params=market_params),
                timeout=45.0,
            )
        except TimeoutError:
            if platform == Platform.POLYMARKET:
                if verbose:
                    print("[bootstrap] polymarket connector timed out, using direct Gamma fallback", flush=True)
                markets = await asyncio.to_thread(
                    _fetch_polymarket_markets_fallback,
                    limit=limit,
                    params=market_params,
                )
            else:
                raise
        events = await connector.fetch_events(limit=limit, params=event_params) if fetch_events else []
    finally:
        aclose = getattr(connector, "aclose", None)
        if callable(aclose):
            await aclose()
    return {
        "platform": platform.value,
        "markets": markets,
        "events": events,
    }


async def bootstrap_prediction_market_resolved_dataset(
    *,
    output_path: Path,
    limit_per_platform: int = 1000,
    platform_configs: Mapping[str, Mapping[str, Any]] | None = None,
    platforms: tuple[Platform, ...] = (Platform.POLYMARKET, Platform.KALSHI, Platform.MANIFOLD),
    verbose: bool = False,
) -> dict[str, Any]:
    platform_configs = platform_configs or {}
    fetched: list[dict[str, Any]] = []
    for platform in platforms:
        fetched.append(
            await _fetch_platform_records(
                platform=platform,
                limit=limit_per_platform,
                config=platform_configs.get(platform.value),
                verbose=verbose,
            )
        )

    rows: list[dict[str, Any]] = []
    platform_fetch_counts: dict[str, dict[str, int]] = {}
    for payload in fetched:
        platform_name = str(payload["platform"])
        markets = list(payload["markets"])
        events = list(payload["events"])
        platform_fetch_counts[platform_name] = {
            "market_count": int(len(markets)),
            "event_count": int(len(events)),
        }
        if platform_name == Platform.MANIFOLD.value:
            rows.extend(
                row
                for row in (normalize_manifold_market_to_dataset_row(record) for record in markets)
                if row is not None
            )
            continue

        event_lookup = _build_event_lookup(events)
        if platform_name == Platform.POLYMARKET.value:
            rows.extend(
                row
                for row in (
                    normalize_polymarket_market_to_dataset_row(record, event_lookup=event_lookup)
                    for record in markets
                )
                if row is not None
            )
            continue
        if platform_name == Platform.KALSHI.value:
            rows.extend(
                row
                for row in (
                    normalize_kalshi_market_to_dataset_row(record, event_lookup=event_lookup)
                    for record in markets
                )
                if row is not None
            )

    dataset = pd.DataFrame(rows).sort_values(["resolution_ts", "market_id"]).reset_index(drop=True) if rows else pd.DataFrame()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)

    summary = {
        "output_path": str(output_path),
        "status": "ok" if not dataset.empty else "empty",
        "resolved_rows": int(len(dataset)),
        "markets": int(dataset["market_id"].nunique()) if not dataset.empty else 0,
        "platform_fetch_counts": platform_fetch_counts,
        "platform_row_counts": {
            str(key): int(value)
            for key, value in Counter(dataset["platform"].fillna("unknown")).most_common()
        } if not dataset.empty else {},
        "category_counts": {
            str(key): int(value)
            for key, value in Counter(dataset["category"].fillna("unknown")).most_common()
        } if not dataset.empty else {},
        "unique_events": int(dataset["event_id"].nunique()) if not dataset.empty else 0,
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a resolved dataset from all supported prediction-market connectors")
    parser.add_argument(
        "--output",
        default="data/derived/resolved/bootstrap_prediction_market_resolved_dataset.csv",
        help="output csv path",
    )
    parser.add_argument("--limit-per-platform", type=int, default=1000)
    parser.add_argument(
        "--platforms",
        default="polymarket,kalshi,manifold",
        help="comma-separated platform list",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    platform_values = tuple(
        Platform(token.strip())
        for token in str(args.platforms).split(",")
        if token.strip()
    )
    summary = asyncio.run(
        bootstrap_prediction_market_resolved_dataset(
            output_path=Path(args.output),
            limit_per_platform=int(args.limit_per_platform),
            platforms=platform_values,
            verbose=bool(args.verbose),
        )
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["resolved_rows"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
