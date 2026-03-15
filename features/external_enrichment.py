"""Optional local-file external feature enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ExternalEnrichmentConfig:
    news_csv_path: str | None = None
    polls_csv_path: str | None = None
    snapshot_time_col: str = "snapshot_ts"


_NEWS_DEFAULTS = {
    "news_articles_24h": 0.0,
    "news_articles_72h": 0.0,
    "news_recentness_hours": float("nan"),
    "news_match_quality": 0.0,
    "news_weighted_count_72h": 0.0,
}

_POLL_DEFAULTS = {
    "poll_yes_support": float("nan"),
    "poll_margin": float("nan"),
    "poll_margin_abs": float("nan"),
    "poll_count_30d": 0.0,
    "poll_days_since_last": float("nan"),
    "poll_match_quality": 0.0,
    "poll_recency_weight": 0.0,
}


def enrich_with_external_features(
    rows: pd.DataFrame,
    config: ExternalEnrichmentConfig | None = None,
) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()

    cfg = config or ExternalEnrichmentConfig()
    enriched = rows.copy()
    news_frame = _load_optional_csv(cfg.news_csv_path)
    polls_frame = _load_optional_csv(cfg.polls_csv_path)

    news_rows: list[dict[str, Any]] = []
    poll_rows: list[dict[str, Any]] = []
    snapshot_times = pd.to_datetime(enriched.get(cfg.snapshot_time_col), utc=True, errors="coerce")

    for idx, row in enriched.iterrows():
        as_of = snapshot_times.iloc[idx]
        query_terms = _coerce_query_terms(row.get("query_terms"))
        news_rows.append(_compute_news_features(news_frame, query_terms, as_of))
        poll_rows.append(_compute_poll_features(polls_frame, query_terms, as_of))

    news_df = pd.DataFrame(news_rows, index=enriched.index)
    poll_df = pd.DataFrame(poll_rows, index=enriched.index)
    for column, default in _NEWS_DEFAULTS.items():
        if column not in news_df.columns:
            news_df[column] = default
    for column, default in _POLL_DEFAULTS.items():
        if column not in poll_df.columns:
            poll_df[column] = default
    return pd.concat([enriched, news_df, poll_df], axis=1)


def _load_optional_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    resolved = Path(path)
    if not resolved.exists():
        return pd.DataFrame()
    return pd.read_csv(resolved)


def _coerce_query_terms(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip().lower() for part in value.split(",")]
        return [part for part in parts if part]
    return []


def _compute_news_features(news_frame: pd.DataFrame, query_terms: list[str], as_of: pd.Timestamp) -> dict[str, Any]:
    if news_frame.empty or not query_terms or pd.isna(as_of):
        return dict(_NEWS_DEFAULTS)

    work = news_frame.copy()
    work["_published_at"] = pd.to_datetime(
        work.get("published_at", work.get("ts")),
        utc=True,
        errors="coerce",
    )
    text_source = (
        work.get("headline", pd.Series("", index=work.index)).astype("string").fillna("")
        + " "
        + work.get("body", pd.Series("", index=work.index)).astype("string").fillna("")
    ).str.lower()
    overlap_counts = text_source.apply(lambda text: sum(term in text for term in query_terms))
    matched = work.loc[(overlap_counts > 0) & work["_published_at"].notna()].copy()
    if matched.empty:
        return dict(_NEWS_DEFAULTS)

    matched["_age_hours"] = (as_of - matched["_published_at"]).dt.total_seconds() / 3600.0
    recent_24 = matched.loc[(matched["_age_hours"] >= 0) & (matched["_age_hours"] <= 24)]
    recent_72 = matched.loc[(matched["_age_hours"] >= 0) & (matched["_age_hours"] <= 72)]
    if recent_72.empty:
        return dict(_NEWS_DEFAULTS)
    match_quality = float(overlap_counts.loc[recent_72.index].mean() / max(len(query_terms), 1))
    weighted_count = float((1.0 / (1.0 + recent_72["_age_hours"])).sum())
    return {
        "news_articles_24h": float(len(recent_24)),
        "news_articles_72h": float(len(recent_72)),
        "news_recentness_hours": float(recent_72["_age_hours"].min()),
        "news_match_quality": match_quality,
        "news_weighted_count_72h": weighted_count,
    }


def _compute_poll_features(polls_frame: pd.DataFrame, query_terms: list[str], as_of: pd.Timestamp) -> dict[str, Any]:
    if polls_frame.empty or not query_terms or pd.isna(as_of):
        return dict(_POLL_DEFAULTS)

    work = polls_frame.copy()
    work["_published_at"] = pd.to_datetime(
        work.get("published_at", work.get("ts")),
        utc=True,
        errors="coerce",
    )
    text_source = (
        work.get("question", pd.Series("", index=work.index)).astype("string").fillna("")
        + " "
        + work.get("subject", pd.Series("", index=work.index)).astype("string").fillna("")
        + " "
        + work.get("answer", pd.Series("", index=work.index)).astype("string").fillna("")
    ).str.lower()
    overlap_counts = text_source.apply(lambda text: sum(term in text for term in query_terms))
    matched = work.loc[(overlap_counts > 0) & work["_published_at"].notna()].copy()
    if matched.empty:
        return dict(_POLL_DEFAULTS)

    matched["_age_days"] = (as_of - matched["_published_at"]).dt.total_seconds() / 86400.0
    recent = matched.loc[(matched["_age_days"] >= 0) & (matched["_age_days"] <= 30)].copy()
    if recent.empty:
        return dict(_POLL_DEFAULTS)

    recent["_yes_support"] = pd.to_numeric(
        recent.get("yes_support", recent.get("pct", recent.get("support"))),
        errors="coerce",
    )
    recent["_no_support"] = pd.to_numeric(
        recent.get("no_support", recent.get("opp_support", recent.get("opposition"))),
        errors="coerce",
    )
    yes_support = recent["_yes_support"].dropna()
    no_support = recent["_no_support"].dropna()
    margin = float("nan")
    if not yes_support.empty and not no_support.empty:
        margin = float(yes_support.iloc[-1] - no_support.iloc[-1])
    match_quality = overlap_counts.loc[recent.index].clip(lower=0).mean() / max(len(query_terms), 1)
    recency_weight = float((1.0 / (1.0 + recent["_age_days"])).sum())
    return {
        "poll_yes_support": float(yes_support.iloc[-1]) if not yes_support.empty else float("nan"),
        "poll_margin": margin,
        "poll_margin_abs": abs(margin) if pd.notna(margin) else float("nan"),
        "poll_count_30d": float(len(recent)),
        "poll_days_since_last": float(recent["_age_days"].min()),
        "poll_match_quality": float(match_quality),
        "poll_recency_weight": recency_weight,
    }


__all__ = ["ExternalEnrichmentConfig", "enrich_with_external_features"]
