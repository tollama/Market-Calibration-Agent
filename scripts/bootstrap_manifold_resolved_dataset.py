#!/usr/bin/env python3
"""Bootstrap a minimal resolved-market dataset from Manifold's public API."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
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
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("politics", ("election", "elections", "president", "prime minister", "senate", "parliament", "vote", "voter", "government", "bjp", "congress", "trump", "biden", "kamala", "state of the union", "iran")),
    ("macro", ("jobless claims", "inflation", "cpi", "fed", "interest rate", "gdp", "economy", "dow", "nifty", "nasdaq", "s&p", "stocks", "solar energy", "retail prices", "prices rise")),
    ("sports", ("nba", "nfl", "mlb", "nhl", "soccer", "football", "tennis", "golf", "stanford daily crossword tournament", "tournament", "match", "ncaab", "ncaa", "olympics", "champions league", "cavaliers", "bucks", "uswnt", "goal", "formula 1", "f1", "george russell", "vitaly", "devon", "marathon")),
    ("crypto", ("bitcoin", "btc", "eth", "ethereum", "solana", "crypto", "coin", "token")),
    ("weather", ("rain", "snow", "weather", "moon phase", "temperature", "wind", "storm")),
    ("entertainment", ("movie", "celebrity", "tv", "show", "oscar", "grammy", "album", "box office", "mrbeast", "youtube", "twitch")),
    ("science", ("space", "nasa", "rocket", "launch", "science", "research", "llm", "ai ", " ai", "gpt", "model", "iss")),
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "before",
    "by",
    "close",
    "day",
    "for",
    "if",
    "in",
    "is",
    "market",
    "my",
    "of",
    "on",
    "the",
    "there",
    "this",
    "to",
    "today",
    "tonight",
    "will",
}
_MONTH_PATTERN = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _slugify(text: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in text.lower()).strip("-")


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


def _infer_category(record: Mapping[str, Any]) -> str:
    group_slugs = record.get("group_slugs")
    if isinstance(group_slugs, list):
        for value in group_slugs:
            token = str(value).strip().lower()
            if token:
                return token

    haystack = " ".join(
        str(record.get(key) or "")
        for key in ("question", "title", "slug")
    ).lower()
    if haystack.startswith("test, do not trade") or haystack.startswith("daily market"):
        return "test"
    if haystack.startswith("will i ") or haystack.startswith("i'm going to "):
        return "personal"
    if any(token in haystack for token in ("comment on this market", "followers", "username")):
        return "social"
    if any(token in haystack for token in ("harvard", " mit ", "class tomorrow", "midterm", "school", "blueprint", "ap compsci", "hls ")):
        return "education"
    if any(token in haystack for token in ("github", "pull request", "pr be opened", "repo", "micrograd", "ai trading bot", "autonomous trading bot")):
        return "technology"
    if any(token in haystack for token in ("flight", "cancelled", "mia->lga", "delta dl")):
        return "travel"
    if any(token in haystack for token in ("random number", "powerball", "lottery")):
        return "games"
    if "coinflip" in haystack or "coin flip" in haystack:
        return "games"
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "unknown"


def _infer_template(title: str, slug: str, category: str) -> tuple[str, str, float, int]:
    title_l = title.lower()
    slug_l = slug.lower()

    if "coinflip" in slug_l or "coin flip" in title_l:
        return "games", "daily_coinflip", 0.95, 1
    if any(token in title_l for token in ("close above", "close below", "higher than", "lower than", "above ", "below ")):
        return "numeric_threshold", "price_threshold", 0.85, 1
    if "election" in title_l or "elections" in title_l:
        return "politics", "election_resolution", 0.9, 1
    if category == "sports":
        return "sports", "sports_event", 0.8, 1
    if category == "macro":
        return "macro", "macro_indicator", 0.8, 1
    if category == "entertainment":
        return "entertainment", "entertainment_event", 0.75, 1
    if title_l.startswith("will i "):
        return "personal", "personal_outcome", 0.8, 1
    return category, "binary_yes_no", 0.5 if category != "unknown" else 0.0, 0 if category == "unknown" else 1


def _extract_date_token(text: str) -> str | None:
    haystack = text.lower()
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", haystack)
    if iso_match:
        return _slugify(iso_match.group(0))
    month_day_year_match = re.search(rf"\b{_MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s+\d{{4}})?\b", haystack)
    if month_day_year_match:
        return _slugify(month_day_year_match.group(0))
    day_month_year_match = re.search(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_PATTERN}(?:\s+\d{{4}})?\b", haystack)
    if day_month_year_match:
        return _slugify(day_month_year_match.group(0))
    return None


def _condense_signature_tokens(tokens: list[str], *, limit: int = 4) -> str:
    filtered = [token for token in tokens if token not in _STOPWORDS and len(token) > 2]
    if not filtered:
        filtered = [token for token in tokens if len(token) > 1]
    return "-".join(filtered[:limit]) if filtered else "unknown"


def _infer_event_signature(title: str, slug: str, category: str) -> str:
    title_l = title.lower()
    slug_l = slug.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", title_l or slug_l).strip()

    if "coinflip" in slug_l or "coin flip" in title_l:
        return "daily-coinflip"
    if "tonight's movie" in title_l or "tonight s movie" in normalized:
        return "tonights-movie"
    if "close" in normalized and category == "macro":
        prefix = normalized.split("close", 1)[0].strip().split()
        return f"{_condense_signature_tokens(prefix, limit=3)}-close"
    if " vs " in normalized and category == "sports":
        left, right = normalized.split(" vs ", 1)
        left_sig = _condense_signature_tokens(left.split()[-3:], limit=2)
        right_sig = _condense_signature_tokens(right.split()[:3], limit=2)
        return f"{left_sig}-vs-{right_sig}"
    if "election" in normalized and category == "politics":
        head = normalized.split("election", 1)[0].strip().split()
        return f"{_condense_signature_tokens(head, limit=3)}-election"

    slug_tokens = [token for token in slug_l.split("-") if token]
    return _condense_signature_tokens(slug_tokens, limit=4)


def _infer_event_id(record: Mapping[str, Any], *, category: str, slug: str) -> str:
    group_slugs = record.get("group_slugs")
    if isinstance(group_slugs, list):
        for value in group_slugs:
            token = str(value).strip()
            if token:
                return f"manifold:{token}"

    title = str(record.get("question") or record.get("title") or "")
    signature = _infer_event_signature(title, slug, category)
    date_token = _extract_date_token(f"{title} {slug}")
    if date_token:
        return f"manifold:{category}:{signature}:{date_token}"
    return f"manifold:{category}:{signature}"


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
    title = str(record.get("question") or "")
    slug = str(record.get("slug") or "")
    category = _infer_category(record)
    template_group, market_template, template_confidence, template_entity_count = _infer_template(title, slug, category)
    event_id = _infer_event_id(record, category=category, slug=slug)

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
        "title": title,
        "slug": slug,
        "template_group": template_group,
        "market_template": market_template,
        "template_confidence": template_confidence,
        "template_entity_count": template_entity_count,
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
    if not dataset.empty:
        summary["unique_events"] = int(dataset["event_id"].nunique())
        summary["category_counts"] = {
            str(key): int(value)
            for key, value in Counter(dataset["category"].fillna("unknown")).most_common()
        }
        summary["template_group_counts"] = {
            str(key): int(value)
            for key, value in Counter(dataset["template_group"].fillna("unknown")).most_common()
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
