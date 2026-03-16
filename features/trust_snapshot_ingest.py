"""Trust snapshot ingestion — merges News-Agent / Financial-Agent trust artifacts into MCA feature frame.

This module reads pre-computed trust snapshot JSONL files produced by
News-Agent and Financial-Agent and injects aggregated trust features
into the MCA market feature frame.  It runs **after** the existing
``enrich_with_external_features`` call in scan/train pipelines.

Input contracts:
  news_trust_snapshot.jsonl   — one JSON object per line, fields include:
      query, source_credibility, corroboration, freshness_score,
      trust_score, analyzed_at  (plus optional extras)
  financial_trust_snapshot.jsonl — one JSON object per line, fields include:
      instrument_id, liquidity_depth, realized_volatility,
      execution_risk, data_freshness, trust_score, regime, analyzed_at

Matching:
  - news  → substring match of market ``query_terms`` against snapshot ``query``
  - financial → explicit ``market_template_to_symbol_map.yaml``
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# ── defaults ────────────────────────────────────────────────────────

_NEWS_TRUST_DEFAULTS: dict[str, float] = {
    "ext_news_trust_score": 0.5,
    "ext_news_credibility": 0.5,
    "ext_news_corroboration": 0.5,
    "ext_news_freshness": 0.5,
    "ext_news_count": 0.0,
}

_FIN_TRUST_DEFAULTS: dict[str, float] = {
    "ext_fin_trust_score": 0.5,
    "ext_fin_liquidity": 0.5,
    "ext_fin_volatility": 0.2,
    "ext_fin_regime_score": 0.5,
    "ext_fin_execution_risk": 0.5,
}

# Regime → numeric score mapping (same as Financial-Agent calibration)
_REGIME_SCORES: dict[str, float] = {
    "ranging": 0.7,
    "trending_up": 0.8,
    "trending_down": 0.5,
    "risk_on": 0.6,
    "risk_off": 0.4,
    "high_volatility": 0.2,
}


# ── config ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrustSnapshotConfig:
    """Configuration for trust snapshot ingestion."""

    news_snapshot_path: str | None = None
    financial_snapshot_path: str | None = None
    symbol_map_path: str | None = None
    default_trust_score: float = 0.5
    feature_prefix_news: str = "ext_news_"
    feature_prefix_financial: str = "ext_fin_"


# ── public API ──────────────────────────────────────────────────────


def enrich_with_trust_snapshots(
    rows: pd.DataFrame,
    config: TrustSnapshotConfig | None = None,
) -> pd.DataFrame:
    """Enrich a market feature frame with external trust snapshot features.

    Parameters
    ----------
    rows : pd.DataFrame
        Market feature frame.  Must contain ``query_terms`` column (list[str])
        produced by ``market_templates.py``.
    config : TrustSnapshotConfig, optional
        Snapshot paths and mapping config.  If *None* or paths are *None*,
        default values are filled for the corresponding feature columns.

    Returns
    -------
    pd.DataFrame
        A copy of *rows* with additional ``ext_news_*`` and ``ext_fin_*`` columns.
    """
    out = rows.copy()

    if config is None:
        config = TrustSnapshotConfig()

    # News trust snapshot
    out = _enrich_news_trust(out, config)

    # Financial trust snapshot
    out = _enrich_financial_trust(out, config)

    return out


# ── internals ───────────────────────────────────────────────────────


def _load_jsonl(path: str | None) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        logger.warning("Snapshot file not found: %s", path)
        return []
    records: list[dict[str, Any]] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_symbol_map(path: str | None) -> dict[str, list[str]]:
    """Load market-template-to-symbol mapping YAML.

    Expected format::

        mappings:
          - template: "stock_price_*"
            symbols: ["SPY", "QQQ"]
          - template: "crypto_*"
            symbols: ["BTC-USD", "ETH-USD"]
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        logger.warning("Symbol map file not found: %s", path)
        return {}
    with p.open() as f:
        data = yaml.safe_load(f)
    mapping: dict[str, list[str]] = {}
    for entry in data.get("mappings", []):
        template = entry.get("template", "")
        symbols = entry.get("symbols", [])
        if template and symbols:
            mapping[template] = symbols
    return mapping


def _match_news_snapshot(
    query_terms: list[str] | Any,
    snapshots: list[dict[str, Any]],
) -> dict[str, float]:
    """Match news trust snapshots against market query_terms."""
    if not isinstance(query_terms, list) or not query_terms or not snapshots:
        return dict(_NEWS_TRUST_DEFAULTS)

    matched: list[dict[str, Any]] = []
    terms_lower = [t.lower() for t in query_terms]

    for snap in snapshots:
        snap_query = str(snap.get("query", "")).lower()
        if any(term in snap_query for term in terms_lower):
            matched.append(snap)

    if not matched:
        return dict(_NEWS_TRUST_DEFAULTS)

    # Aggregate: best trust_score, mean credibility/corroboration/freshness
    return {
        "ext_news_trust_score": max(s.get("trust_score", 0.5) for s in matched),
        "ext_news_credibility": sum(s.get("source_credibility", 0.5) for s in matched) / len(matched),
        "ext_news_corroboration": sum(s.get("corroboration", 0.5) for s in matched) / len(matched),
        "ext_news_freshness": max(s.get("freshness_score", 0.5) for s in matched),
        "ext_news_count": float(len(matched)),
    }


def _match_financial_snapshot(
    market_template: str | Any,
    symbol_map: dict[str, list[str]],
    snapshots: list[dict[str, Any]],
) -> dict[str, float]:
    """Match financial trust snapshots via symbol map."""
    if not isinstance(market_template, str) or not snapshots:
        return dict(_FIN_TRUST_DEFAULTS)

    # Find matching symbols via template pattern
    matched_symbols: list[str] = []
    template_lower = market_template.lower()
    for pattern, symbols in symbol_map.items():
        pattern_lower = pattern.lower().rstrip("*")
        if template_lower.startswith(pattern_lower) or pattern_lower in template_lower:
            matched_symbols.extend(symbols)

    if not matched_symbols:
        return dict(_FIN_TRUST_DEFAULTS)

    # Find snapshots for matched symbols
    symbols_upper = {s.upper() for s in matched_symbols}
    matched: list[dict[str, Any]] = []
    for snap in snapshots:
        inst_id = str(snap.get("instrument_id", "")).upper()
        if inst_id in symbols_upper:
            matched.append(snap)

    if not matched:
        return dict(_FIN_TRUST_DEFAULTS)

    return {
        "ext_fin_trust_score": max(s.get("trust_score", 0.5) for s in matched),
        "ext_fin_liquidity": sum(s.get("liquidity_depth", 0.5) for s in matched) / len(matched),
        "ext_fin_volatility": sum(s.get("realized_volatility", 0.2) for s in matched) / len(matched),
        "ext_fin_regime_score": sum(
            _REGIME_SCORES.get(str(s.get("regime", "ranging")), 0.5)
            for s in matched
        ) / len(matched),
        "ext_fin_execution_risk": sum(s.get("execution_risk", 0.5) for s in matched) / len(matched),
    }


def _enrich_news_trust(
    df: pd.DataFrame,
    config: TrustSnapshotConfig,
) -> pd.DataFrame:
    """Add news trust features to the DataFrame."""
    snapshots = _load_jsonl(config.news_snapshot_path)

    if not snapshots or "query_terms" not in df.columns:
        for col, default in _NEWS_TRUST_DEFAULTS.items():
            df[col] = default
        return df

    news_features = df["query_terms"].apply(
        lambda qt: _match_news_snapshot(qt, snapshots)
    )
    news_df = pd.DataFrame(news_features.tolist(), index=df.index)
    for col in _NEWS_TRUST_DEFAULTS:
        df[col] = news_df[col]

    return df


def _enrich_financial_trust(
    df: pd.DataFrame,
    config: TrustSnapshotConfig,
) -> pd.DataFrame:
    """Add financial trust features to the DataFrame."""
    snapshots = _load_jsonl(config.financial_snapshot_path)
    symbol_map = _load_symbol_map(config.symbol_map_path)

    if not snapshots or not symbol_map or "market_template" not in df.columns:
        for col, default in _FIN_TRUST_DEFAULTS.items():
            df[col] = default
        return df

    fin_features = df["market_template"].apply(
        lambda mt: _match_financial_snapshot(mt, symbol_map, snapshots)
    )
    fin_df = pd.DataFrame(fin_features.tolist(), index=df.index)
    for col in _FIN_TRUST_DEFAULTS:
        df[col] = fin_df[col]

    return df


__all__ = [
    "TrustSnapshotConfig",
    "enrich_with_trust_snapshots",
]
