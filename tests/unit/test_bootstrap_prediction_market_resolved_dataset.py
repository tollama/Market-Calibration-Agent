from __future__ import annotations

import asyncio

import pandas as pd

from schemas.enums import Platform
from scripts.bootstrap_prediction_market_resolved_dataset import (
    bootstrap_prediction_market_resolved_dataset,
    normalize_kalshi_market_to_dataset_row,
    normalize_polymarket_market_to_dataset_row,
)


def test_normalize_polymarket_market_to_dataset_row_maps_closed_binary_market() -> None:
    row = normalize_polymarket_market_to_dataset_row(
        {
            "id": "pm1",
            "question": "Will Coinbase begin publicly trading before Jan 1, 2021?",
            "slug": "will-coinbase-begin-publicly-trading-before-jan-1-2021",
            "category": "Crypto",
            "outcomes": '["Yes","No"]',
            "outcome_prices": '["0.000001","0.999999"]',
            "end_date": "2021-01-02T00:00:00Z",
            "closed_time": "2021-01-02 21:43:06+00",
            "updated_at": "2021-01-02T21:40:00Z",
            "created_at": "2020-10-02T19:20:04.249Z",
            "volume24hr": 10,
            "liquidity_num": 50,
            "events": [{"id": "ev1", "category": "Crypto"}],
        }
    )

    assert row is not None
    assert row["market_id"] == "polymarket:pm1"
    assert row["event_id"] == "polymarket:ev1"
    assert row["label"] == 0
    assert row["category"] == "crypto"
    assert row["platform"] == "polymarket"


def test_normalize_kalshi_market_to_dataset_row_maps_finalized_binary_market() -> None:
    row = normalize_kalshi_market_to_dataset_row(
        {
            "ticker": "KXTEST-YES",
            "event_ticker": "KXTEST",
            "market_type": "binary",
            "result": "yes",
            "settlement_ts": "2026-03-16T00:35:21.013877Z",
            "close_time": "2026-03-16T00:34:21Z",
            "updated_time": "2026-03-16T00:35:21.071929Z",
            "previous_yes_bid_dollars": "0.42",
            "previous_yes_ask_dollars": "0.46",
            "open_interest_fp": "1250.00",
            "volume_24h_fp": "88.00",
            "title": "Will test market resolve yes?",
        },
        event_lookup={
            "KXTEST": {
                "event_ticker": "KXTEST",
                "category": "World",
                "title": "Will test market resolve yes?",
            }
        },
    )

    assert row is not None
    assert row["market_id"] == "kalshi:KXTEST-YES"
    assert row["event_id"] == "kalshi:KXTEST"
    assert row["label"] == 1
    assert row["category"] == "world"
    assert row["market_prob"] == 0.44


def test_normalize_kalshi_market_to_dataset_row_infers_sports_from_ticker_prefix() -> None:
    row = normalize_kalshi_market_to_dataset_row(
        {
            "ticker": "KXMVECROSSCATEGORY-ABC",
            "event_ticker": "KXMVESPORTSMULTIGAMEEXTENDED-XYZ",
            "market_type": "binary",
            "result": "no",
            "settlement_ts": "2026-03-16T00:35:21.013877Z",
            "close_time": "2026-03-16T00:34:21Z",
            "previous_price_dollars": "0.33",
            "title": "yes Golden State,yes Portland,yes Utah",
        },
        event_lookup={},
    )

    assert row is not None
    assert row["category"] == "sports"


def test_bootstrap_prediction_market_resolved_dataset_adds_canonical_category_and_structure(
    tmp_path, monkeypatch
) -> None:
    class _FakeConnector:
        def __init__(self, markets, events, historical_markets=None) -> None:
            self._markets = list(markets)
            self._events = list(events)
            self._historical_markets = list(historical_markets or [])

        async def fetch_markets(self, *, limit: int = 500, params=None):
            return self._markets[:limit]

        async def fetch_historical_markets(self, *, limit: int = 500, params=None):
            return self._historical_markets[:limit]

        async def fetch_events(self, *, limit: int = 500, params=None):
            return self._events[:limit]

        async def aclose(self) -> None:
            return None

    connectors = {
        Platform.POLYMARKET: _FakeConnector(
            markets=[],
            events=[],
        ),
        Platform.KALSHI: _FakeConnector(
            markets=[
                {
                    "ticker": "KXMVECROSSCATEGORY-ABC",
                    "event_ticker": "KXMVESPORTSMULTIGAMEEXTENDED-XYZ",
                    "market_type": "binary",
                    "result": "no",
                    "settlement_ts": "2026-03-16T00:35:21.013877Z",
                    "close_time": "2026-03-16T00:34:21Z",
                    "previous_price_dollars": "0.33",
                    "title": "yes Golden State,yes Portland,yes Over 230.5 points scored",
                }
            ],
            events=[],
        ),
        Platform.MANIFOLD: _FakeConnector(
            markets=[],
            events=[],
        ),
    }

    def _fake_create_connector(platform: Platform, *, config=None):
        return connectors[platform]

    monkeypatch.setattr(
        "scripts.bootstrap_prediction_market_resolved_dataset.create_connector",
        _fake_create_connector,
    )

    output = tmp_path / "bootstrap_prediction_market_resolved_dataset.csv"
    summary = asyncio.run(
        bootstrap_prediction_market_resolved_dataset(
            output_path=output,
            limit_per_platform=10,
        )
    )

    assert summary["canonical_category_counts"]["sports"] == 1
    assert summary["market_structure_counts"]["combo_multi_leg"] == 1
    frame = pd.read_csv(output)
    assert frame.loc[0, "canonical_category"] == "sports"
    assert frame.loc[0, "market_structure"] == "combo_multi_leg"
    assert frame.loc[0, "platform_category"] == "kalshi:sports"
    assert frame.loc[0, "is_standard_market"] == 0


def test_bootstrap_prediction_market_resolved_dataset_combines_all_supported_platforms(
    tmp_path, monkeypatch
) -> None:
    class _FakeConnector:
        def __init__(self, markets, events, historical_markets=None) -> None:
            self._markets = list(markets)
            self._events = list(events)
            self._historical_markets = list(historical_markets or [])

        async def fetch_markets(self, *, limit: int = 500, params=None):
            return self._markets[:limit]

        async def fetch_historical_markets(self, *, limit: int = 500, params=None):
            return self._historical_markets[:limit]

        async def fetch_events(self, *, limit: int = 500, params=None):
            return self._events[:limit]

        async def aclose(self) -> None:
            return None

    connectors = {
        Platform.POLYMARKET: _FakeConnector(
            markets=[
                {
                    "id": "pm1",
                    "question": "Will Coinbase begin publicly trading before Jan 1, 2021?",
                    "slug": "will-coinbase-begin-publicly-trading-before-jan-1-2021",
                    "category": "Crypto",
                    "outcomes": '["Yes","No"]',
                    "outcome_prices": '["0.000001","0.999999"]',
                    "closed_time": "2021-01-02 21:43:06+00",
                    "updated_at": "2021-01-02T21:40:00Z",
                    "volume24hr": 10,
                    "liquidity_num": 50,
                    "events": [{"id": "ev1", "category": "Crypto"}],
                }
            ],
            events=[],
        ),
        Platform.KALSHI: _FakeConnector(
            markets=[
                {
                    "ticker": "KXTEST-YES",
                    "event_ticker": "KXTEST",
                    "market_type": "binary",
                    "result": "yes",
                    "settlement_ts": "2026-03-16T00:35:21.013877Z",
                    "close_time": "2026-03-16T00:34:21Z",
                    "previous_yes_bid_dollars": "0.42",
                    "previous_yes_ask_dollars": "0.46",
                    "open_interest_fp": "1250.00",
                    "volume_24h_fp": "88.00",
                    "title": "Will test market resolve yes?",
                }
            ],
            events=[{"event_ticker": "KXTEST", "category": "World", "title": "Will test market resolve yes?"}],
        ),
        Platform.MANIFOLD: _FakeConnector(
            markets=[
                {
                    "id": "mf1",
                    "question": "Will it rain tomorrow?",
                    "probability": 0.72,
                    "resolution": "YES",
                    "outcome_type": "BINARY",
                    "close_time": 1735689600000,
                    "resolution_time": 1735693200000,
                    "group_slugs": ["weather"],
                    "total_liquidity": 25000,
                    "volume24_hours": 1500,
                    "slug": "will-it-rain-tomorrow",
                }
            ],
            events=[],
        ),
    }

    def _fake_create_connector(platform: Platform, *, config=None):
        return connectors[platform]

    monkeypatch.setattr(
        "scripts.bootstrap_prediction_market_resolved_dataset.create_connector",
        _fake_create_connector,
    )

    output = tmp_path / "bootstrap_prediction_market_resolved_dataset.csv"
    summary = asyncio.run(
        bootstrap_prediction_market_resolved_dataset(
            output_path=output,
            limit_per_platform=10,
        )
    )

    assert summary["resolved_rows"] == 3
    assert summary["platform_row_counts"]["polymarket"] == 1
    assert summary["platform_row_counts"]["kalshi"] == 1
    assert summary["platform_row_counts"]["manifold"] == 1
    assert "canonical_category_counts" in summary
    assert "market_structure_counts" in summary
    frame = pd.read_csv(output)
    assert set(frame["platform"]) == {"polymarket", "kalshi", "manifold"}
    assert "canonical_category" in frame.columns
    assert "market_structure" in frame.columns


def test_bootstrap_prediction_market_resolved_dataset_uses_kalshi_historical_markets(
    tmp_path, monkeypatch
) -> None:
    class _FakeConnector:
        def __init__(self, markets, events, historical_markets=None) -> None:
            self._markets = list(markets)
            self._events = list(events)
            self._historical_markets = list(historical_markets or [])

        async def fetch_markets(self, *, limit: int = 500, params=None):
            return self._markets[:limit]

        async def fetch_historical_markets(self, *, limit: int = 500, params=None):
            return self._historical_markets[:limit]

        async def fetch_events(self, *, limit: int = 500, params=None):
            return self._events[:limit]

        async def aclose(self) -> None:
            return None

    connectors = {
        Platform.POLYMARKET: _FakeConnector(markets=[], events=[]),
        Platform.KALSHI: _FakeConnector(
            markets=[
                {
                    "ticker": "LIVE-1",
                    "event_ticker": "LIVE-EVENT",
                    "market_type": "binary",
                    "result": "yes",
                    "settlement_ts": "2026-03-16T00:35:21.013877Z",
                    "close_time": "2026-03-16T00:34:21Z",
                    "previous_price_dollars": "0.44",
                    "title": "Will the live market resolve yes?",
                }
            ],
            historical_markets=[
                {
                    "ticker": "HIST-1",
                    "event_ticker": "HIST-EVENT",
                    "market_type": "binary",
                    "result": "no",
                    "settlement_ts": "2025-03-14T15:27:50.56458Z",
                    "close_time": "2025-03-14T14:00:00Z",
                    "previous_price_dollars": "0.01",
                    "title": "What will J.D. Vance say on Ingraham Angle?",
                    "yes_sub_title": "Meme",
                },
                {
                    "ticker": "LIVE-1",
                    "event_ticker": "LIVE-EVENT",
                    "market_type": "binary",
                    "result": "yes",
                    "settlement_ts": "2026-03-16T00:35:21.013877Z",
                    "close_time": "2026-03-16T00:34:21Z",
                    "previous_price_dollars": "0.44",
                    "title": "Will the live market resolve yes?",
                },
            ],
            events=[
                {"event_ticker": "LIVE-EVENT", "category": "World", "title": "Live event"},
                {"event_ticker": "HIST-EVENT", "category": "Politics", "title": "Historical event"},
            ],
        ),
        Platform.MANIFOLD: _FakeConnector(markets=[], events=[]),
    }

    def _fake_create_connector(platform: Platform, *, config=None):
        return connectors[platform]

    monkeypatch.setattr(
        "scripts.bootstrap_prediction_market_resolved_dataset.create_connector",
        _fake_create_connector,
    )

    output = tmp_path / "bootstrap_prediction_market_resolved_dataset.csv"
    summary = asyncio.run(
        bootstrap_prediction_market_resolved_dataset(
            output_path=output,
            limit_per_platform=10,
        )
    )

    assert summary["platform_fetch_counts"]["kalshi"]["historical_market_count"] == 2
    assert summary["platform_row_counts"]["kalshi"] == 2
    frame = pd.read_csv(output)
    assert set(frame["market_id"]) == {"kalshi:HIST-1", "kalshi:LIVE-1"}
