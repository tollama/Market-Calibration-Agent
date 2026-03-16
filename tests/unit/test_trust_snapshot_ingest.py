"""Tests for features.trust_snapshot_ingest."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from features.trust_snapshot_ingest import (
    TrustSnapshotConfig,
    _load_jsonl,
    _load_symbol_map,
    _match_financial_snapshot,
    _match_news_snapshot,
    enrich_with_trust_snapshots,
)


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def news_snapshots_path(tmp_path: Path) -> str:
    """Write a sample news trust snapshot JSONL file."""
    records = [
        {
            "story_id": "n1",
            "query": "CPI inflation forecast",
            "source_credibility": 0.85,
            "corroboration": 0.7,
            "freshness_score": 0.9,
            "trust_score": 0.78,
            "analyzed_at": "2026-03-17T10:00:00Z",
        },
        {
            "story_id": "n2",
            "query": "Federal Reserve interest rate decision",
            "source_credibility": 0.92,
            "corroboration": 0.8,
            "freshness_score": 0.95,
            "trust_score": 0.88,
            "analyzed_at": "2026-03-17T11:00:00Z",
        },
        {
            "story_id": "n3",
            "query": "Bitcoin ETF approval news",
            "source_credibility": 0.6,
            "corroboration": 0.4,
            "freshness_score": 0.7,
            "trust_score": 0.55,
            "analyzed_at": "2026-03-17T09:00:00Z",
        },
    ]
    path = tmp_path / "news_trust_snapshot.jsonl"
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return str(path)


@pytest.fixture()
def financial_snapshots_path(tmp_path: Path) -> str:
    """Write a sample financial trust snapshot JSONL file."""
    records = [
        {
            "instrument_id": "SPY",
            "liquidity_depth": 0.92,
            "realized_volatility": 0.15,
            "execution_risk": 0.08,
            "data_freshness": 0.95,
            "trust_score": 0.87,
            "regime": "trending_up",
            "analyzed_at": "2026-03-17T10:00:00Z",
        },
        {
            "instrument_id": "BTC-USD",
            "liquidity_depth": 0.75,
            "realized_volatility": 0.45,
            "execution_risk": 0.25,
            "data_freshness": 0.90,
            "trust_score": 0.65,
            "regime": "high_volatility",
            "analyzed_at": "2026-03-17T10:00:00Z",
        },
    ]
    path = tmp_path / "financial_trust_snapshot.jsonl"
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return str(path)


@pytest.fixture()
def symbol_map_path(tmp_path: Path) -> str:
    """Write a sample symbol map YAML file."""
    content = textwrap.dedent("""\
        mappings:
          - template: "stock_price_"
            symbols: ["SPY", "QQQ"]
          - template: "crypto_"
            symbols: ["BTC-USD", "ETH-USD"]
    """)
    path = tmp_path / "symbol_map.yaml"
    path.write_text(content)
    return str(path)


@pytest.fixture()
def market_frame() -> pd.DataFrame:
    """Minimal market feature frame with query_terms and market_template."""
    return pd.DataFrame(
        {
            "market_id": ["m1", "m2", "m3", "m4"],
            "question": [
                "Will CPI exceed 3%?",
                "Will BTC hit 100k?",
                "Will it rain in Tokyo?",
                "Will Fed raise rates?",
            ],
            "query_terms": [
                ["CPI", "inflation"],
                ["bitcoin", "btc"],
                ["rain", "tokyo"],
                ["federal reserve", "interest rate"],
            ],
            "market_template": [
                "stock_price_spy",
                "crypto_btc",
                "weather_tokyo",
                "interest_rate_fed",
            ],
            "market_prob": [0.65, 0.40, 0.55, 0.72],
        }
    )


# ── _load_jsonl tests ───────────────────────────────────────────────


class TestLoadJsonl:
    def test_returns_empty_for_none(self):
        assert _load_jsonl(None) == []

    def test_returns_empty_for_missing_file(self, tmp_path: Path):
        assert _load_jsonl(str(tmp_path / "nonexistent.jsonl")) == []

    def test_loads_records(self, news_snapshots_path: str):
        records = _load_jsonl(news_snapshots_path)
        assert len(records) == 3
        assert records[0]["story_id"] == "n1"

    def test_skips_blank_lines(self, tmp_path: Path):
        path = tmp_path / "sparse.jsonl"
        path.write_text('{"a": 1}\n\n{"b": 2}\n\n')
        records = _load_jsonl(str(path))
        assert len(records) == 2


# ── _load_symbol_map tests ──────────────────────────────────────────


class TestLoadSymbolMap:
    def test_returns_empty_for_none(self):
        assert _load_symbol_map(None) == {}

    def test_returns_empty_for_missing_file(self, tmp_path: Path):
        assert _load_symbol_map(str(tmp_path / "missing.yaml")) == {}

    def test_loads_map(self, symbol_map_path: str):
        mapping = _load_symbol_map(symbol_map_path)
        assert "stock_price_" in mapping
        assert "SPY" in mapping["stock_price_"]
        assert "crypto_" in mapping
        assert "BTC-USD" in mapping["crypto_"]


# ── _match_news_snapshot tests ──────────────────────────────────────


class TestMatchNewsSnapshot:
    def test_no_query_terms(self):
        result = _match_news_snapshot([], [{"query": "test", "trust_score": 0.9}])
        assert result["ext_news_trust_score"] == 0.5  # default

    def test_no_snapshots(self):
        result = _match_news_snapshot(["CPI"], [])
        assert result["ext_news_trust_score"] == 0.5

    def test_matching_single(self, news_snapshots_path: str):
        snapshots = _load_jsonl(news_snapshots_path)
        result = _match_news_snapshot(["CPI", "inflation"], snapshots)
        assert result["ext_news_trust_score"] == pytest.approx(0.78)
        assert result["ext_news_credibility"] == pytest.approx(0.85)
        assert result["ext_news_count"] == 1.0

    def test_matching_multiple(self, news_snapshots_path: str):
        snapshots = _load_jsonl(news_snapshots_path)
        # "rate" matches "interest rate decision"
        result = _match_news_snapshot(["federal reserve", "interest rate"], snapshots)
        assert result["ext_news_trust_score"] == pytest.approx(0.88)
        assert result["ext_news_count"] >= 1.0

    def test_no_match_returns_defaults(self, news_snapshots_path: str):
        snapshots = _load_jsonl(news_snapshots_path)
        result = _match_news_snapshot(["aliens", "mars"], snapshots)
        assert result["ext_news_trust_score"] == 0.5
        assert result["ext_news_count"] == 0.0

    def test_non_list_query_terms(self):
        result = _match_news_snapshot("not a list", [{"query": "test"}])
        assert result["ext_news_trust_score"] == 0.5


# ── _match_financial_snapshot tests ─────────────────────────────────


class TestMatchFinancialSnapshot:
    def test_no_template(self):
        result = _match_financial_snapshot(None, {}, [])
        assert result["ext_fin_trust_score"] == 0.5

    def test_no_snapshots(self):
        result = _match_financial_snapshot("stock_price_spy", {"stock_price_": ["SPY"]}, [])
        assert result["ext_fin_trust_score"] == 0.5

    def test_no_symbol_map_match(self, financial_snapshots_path: str):
        snapshots = _load_jsonl(financial_snapshots_path)
        result = _match_financial_snapshot("weather_tokyo", {"stock_price_": ["SPY"]}, snapshots)
        assert result["ext_fin_trust_score"] == 0.5

    def test_matching_spy(self, financial_snapshots_path: str, symbol_map_path: str):
        snapshots = _load_jsonl(financial_snapshots_path)
        symbol_map = _load_symbol_map(symbol_map_path)
        result = _match_financial_snapshot("stock_price_spy", symbol_map, snapshots)
        assert result["ext_fin_trust_score"] == pytest.approx(0.87)
        assert result["ext_fin_liquidity"] == pytest.approx(0.92)
        assert result["ext_fin_regime_score"] == pytest.approx(0.8)  # trending_up → 0.8

    def test_matching_crypto(self, financial_snapshots_path: str, symbol_map_path: str):
        snapshots = _load_jsonl(financial_snapshots_path)
        symbol_map = _load_symbol_map(symbol_map_path)
        result = _match_financial_snapshot("crypto_btc", symbol_map, snapshots)
        assert result["ext_fin_trust_score"] == pytest.approx(0.65)
        assert result["ext_fin_volatility"] == pytest.approx(0.45)
        assert result["ext_fin_regime_score"] == pytest.approx(0.2)  # high_volatility → 0.2


# ── enrich_with_trust_snapshots (integration) ──────────────────────


class TestEnrichWithTrustSnapshots:
    def test_no_config_fills_defaults(self, market_frame: pd.DataFrame):
        result = enrich_with_trust_snapshots(market_frame)
        assert "ext_news_trust_score" in result.columns
        assert "ext_fin_trust_score" in result.columns
        assert (result["ext_news_trust_score"] == 0.5).all()
        assert (result["ext_fin_trust_score"] == 0.5).all()

    def test_does_not_mutate_input(self, market_frame: pd.DataFrame):
        original_cols = set(market_frame.columns)
        _ = enrich_with_trust_snapshots(market_frame)
        assert set(market_frame.columns) == original_cols

    def test_news_enrichment(
        self,
        market_frame: pd.DataFrame,
        news_snapshots_path: str,
    ):
        config = TrustSnapshotConfig(news_snapshot_path=news_snapshots_path)
        result = enrich_with_trust_snapshots(market_frame, config)
        # m1 (CPI, inflation) should match news snapshot n1
        row_m1 = result[result["market_id"] == "m1"].iloc[0]
        assert row_m1["ext_news_trust_score"] == pytest.approx(0.78)
        assert row_m1["ext_news_count"] >= 1.0
        # m3 (rain, tokyo) should get defaults
        row_m3 = result[result["market_id"] == "m3"].iloc[0]
        assert row_m3["ext_news_trust_score"] == 0.5
        assert row_m3["ext_news_count"] == 0.0

    def test_financial_enrichment(
        self,
        market_frame: pd.DataFrame,
        financial_snapshots_path: str,
        symbol_map_path: str,
    ):
        config = TrustSnapshotConfig(
            financial_snapshot_path=financial_snapshots_path,
            symbol_map_path=symbol_map_path,
        )
        result = enrich_with_trust_snapshots(market_frame, config)
        # m1 (stock_price_spy) should match SPY
        row_m1 = result[result["market_id"] == "m1"].iloc[0]
        assert row_m1["ext_fin_trust_score"] == pytest.approx(0.87)
        # m2 (crypto_btc) should match BTC-USD
        row_m2 = result[result["market_id"] == "m2"].iloc[0]
        assert row_m2["ext_fin_trust_score"] == pytest.approx(0.65)
        # m3 (weather_tokyo) should get defaults
        row_m3 = result[result["market_id"] == "m3"].iloc[0]
        assert row_m3["ext_fin_trust_score"] == 0.5

    def test_combined_enrichment(
        self,
        market_frame: pd.DataFrame,
        news_snapshots_path: str,
        financial_snapshots_path: str,
        symbol_map_path: str,
    ):
        config = TrustSnapshotConfig(
            news_snapshot_path=news_snapshots_path,
            financial_snapshot_path=financial_snapshots_path,
            symbol_map_path=symbol_map_path,
        )
        result = enrich_with_trust_snapshots(market_frame, config)
        # Should have all 10 ext columns
        ext_cols = [c for c in result.columns if c.startswith("ext_")]
        assert len(ext_cols) == 10
        # m1 should have both news and financial enrichment
        row_m1 = result[result["market_id"] == "m1"].iloc[0]
        assert row_m1["ext_news_trust_score"] > 0.5  # matched
        assert row_m1["ext_fin_trust_score"] > 0.5  # matched

    def test_missing_query_terms_column(self):
        df = pd.DataFrame({"market_id": ["m1"], "market_template": ["stock_price_spy"]})
        config = TrustSnapshotConfig()
        result = enrich_with_trust_snapshots(df, config)
        assert "ext_news_trust_score" in result.columns
        assert result["ext_news_trust_score"].iloc[0] == 0.5

    def test_missing_market_template_column(self):
        df = pd.DataFrame({"market_id": ["m1"], "query_terms": [["CPI"]]})
        config = TrustSnapshotConfig()
        result = enrich_with_trust_snapshots(df, config)
        assert "ext_fin_trust_score" in result.columns
        assert result["ext_fin_trust_score"].iloc[0] == 0.5

    def test_snapshot_absent_graceful_default(self, market_frame: pd.DataFrame):
        """When snapshot files don't exist, should fill defaults gracefully."""
        config = TrustSnapshotConfig(
            news_snapshot_path="/nonexistent/news.jsonl",
            financial_snapshot_path="/nonexistent/financial.jsonl",
        )
        result = enrich_with_trust_snapshots(market_frame, config)
        assert (result["ext_news_trust_score"] == 0.5).all()
        assert (result["ext_fin_trust_score"] == 0.5).all()

    def test_reproducibility(
        self,
        market_frame: pd.DataFrame,
        news_snapshots_path: str,
        financial_snapshots_path: str,
        symbol_map_path: str,
    ):
        """Same snapshot input → identical output (deterministic)."""
        config = TrustSnapshotConfig(
            news_snapshot_path=news_snapshots_path,
            financial_snapshot_path=financial_snapshots_path,
            symbol_map_path=symbol_map_path,
        )
        r1 = enrich_with_trust_snapshots(market_frame, config)
        r2 = enrich_with_trust_snapshots(market_frame, config)
        pd.testing.assert_frame_equal(r1, r2)
