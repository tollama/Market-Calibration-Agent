"""Cross-platform normalization helpers for prediction-market datasets."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")

_EXACT_CANONICAL_CATEGORY_MAP: dict[str, str] = {
    "art": "culture",
    "arts": "culture",
    "business": "business",
    "chess": "sports",
    "coronavirus": "science_health",
    "covid": "science_health",
    "crypto": "crypto",
    "education": "science_health",
    "entertainment": "culture",
    "games": "culture",
    "global_politics": "politics",
    "health": "science_health",
    "macro": "macro",
    "nfts": "crypto",
    "olympics": "sports",
    "personal": "lifestyle",
    "pop_culture": "culture",
    "politics": "politics",
    "science": "science_health",
    "sports": "sports",
    "technology": "technology",
    "tech": "technology",
    "ukraine_russia": "politics",
    "ukraine_&_russia": "politics",
    "us_current_affairs": "politics",
    "weather": "weather",
    "world": "politics",
}

_TOKEN_CANONICAL_CATEGORY_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("politic", "election", "senate", "house", "president", "prime_minister", "supreme_court", "government", "congress"), "politics"),
    (("affairs", "geopolit", "war", "ukraine", "russia", "china", "israel", "gaza", "world"), "politics"),
    (("inflation", "fed", "fomc", "gdp", "recession", "rates", "jobs", "treasury", "econom"), "macro"),
    (("bitcoin", "ethereum", "solana", "crypto", "defi", "nft"), "crypto"),
    (("nba", "nfl", "nhl", "mlb", "soccer", "football", "basketball", "baseball", "hockey", "tennis", "golf", "olympic", "score", "points"), "sports"),
    (("covid", "coronavirus", "vaccine", "health", "medicine", "scient", "research", "study", "disease"), "science_health"),
    (("ai", "artificial_intelligence", "openai", "anthropic", "technology", "software", "chip", "semiconductor", "tesla"), "technology"),
    (("movie", "tv", "music", "album", "film", "show", "celebrity", "pop_culture", "art", "game"), "culture"),
    (("earnings", "stock", "company", "startup", "business", "revenue", "sales"), "business"),
    (("storm", "temperature", "rain", "snow", "weather", "hurricane"), "weather"),
)

_COMBO_TICKER_TOKENS = (
    "crosscategory",
    "multigame",
    "parlay",
    "samegame",
    "sgp",
)

_PLAYER_PROP_RE = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+: \d+\+")
_YES_NO_CLAUSE_RE = re.compile(r"\b(?:yes|no) [^,]+")


def normalize_category_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    token = token.replace("&", " and ")
    token = _SEPARATOR_RE.sub("_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token or "unknown"


def infer_canonical_category(
    *,
    category: Any,
    title: Any = "",
    slug: Any = "",
    platform: Any = "",
) -> str:
    raw = normalize_category_token(category)
    if raw in _EXACT_CANONICAL_CATEGORY_MAP:
        return _EXACT_CANONICAL_CATEGORY_MAP[raw]
    for part in raw.split("_"):
        if part in _EXACT_CANONICAL_CATEGORY_MAP:
            return _EXACT_CANONICAL_CATEGORY_MAP[part]

    haystack = "_".join(
        token
        for token in (
            normalize_category_token(title),
            normalize_category_token(slug),
            normalize_category_token(platform),
            raw,
        )
        if token and token != "unknown"
    )
    for needles, mapped in _TOKEN_CANONICAL_CATEGORY_MAP:
        if any(needle in haystack for needle in needles):
            return mapped
    return "other"


def coalesce_market_category(
    *,
    category: Any,
    title: Any = "",
    slug: Any = "",
    platform: Any = "",
) -> str:
    raw = normalize_category_token(category)
    if raw != "unknown":
        return raw
    canonical = infer_canonical_category(category=raw, title=title, slug=slug, platform=platform)
    if canonical == "other":
        return "unknown"
    return canonical


def classify_market_structure(
    *,
    platform: Any,
    title: Any = "",
    slug: Any = "",
    market_id: Any = "",
) -> str:
    platform_token = normalize_category_token(platform)
    title_text = str(title or "").strip()
    lowered = " ".join(
        part
        for part in (
            str(slug or ""),
            str(market_id or ""),
            title_text,
        )
        if part
    ).lower()

    if platform_token == "kalshi":
        if any(token in lowered for token in _COMBO_TICKER_TOKENS):
            return "combo_multi_leg"
        yes_no_clauses = len(_YES_NO_CLAUSE_RE.findall(lowered))
        comma_count = title_text.count(",")
        if yes_no_clauses >= 2 or comma_count >= 2:
            return "combo_multi_leg"
        if _PLAYER_PROP_RE.search(title_text):
            return "player_prop"
    return "standard_binary"


def is_standard_market_structure(value: Any) -> bool:
    return str(value or "").strip().lower() in {"standard_binary", "player_prop", ""}


def augment_prediction_market_context(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    work = frame.copy()
    title = work["title"] if "title" in work.columns else pd.Series([""] * len(work), index=work.index, dtype="string")
    slug = work["slug"] if "slug" in work.columns else pd.Series([""] * len(work), index=work.index, dtype="string")
    platform = work["platform"] if "platform" in work.columns else pd.Series(["unknown"] * len(work), index=work.index, dtype="string")

    if "category" in work.columns:
        work["category"] = [
            coalesce_market_category(category=category, title=ttl, slug=sg, platform=plt)
            for category, ttl, sg, plt in zip(work["category"], title, slug, platform)
        ]
    else:
        work["category"] = [
            coalesce_market_category(category="unknown", title=ttl, slug=sg, platform=plt)
            for ttl, sg, plt in zip(title, slug, platform)
        ]

    work["canonical_category"] = [
        infer_canonical_category(category=category, title=ttl, slug=sg, platform=plt)
        for category, ttl, sg, plt in zip(work["category"], title, slug, platform)
    ]
    work["market_structure"] = [
        classify_market_structure(platform=plt, title=ttl, slug=sg, market_id=mid)
        for plt, ttl, sg, mid in zip(platform, title, slug, work.get("market_id", pd.Series([""] * len(work), index=work.index)))
    ]
    work["platform_category"] = [
        f"{normalize_category_token(plt)}:{canonical}"
        for plt, canonical in zip(platform, work["canonical_category"])
    ]
    work["is_standard_market"] = work["market_structure"].map(is_standard_market_structure).astype(int)
    return work
