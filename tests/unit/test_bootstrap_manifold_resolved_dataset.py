from __future__ import annotations

import asyncio

from scripts.bootstrap_manifold_resolved_dataset import (
    bootstrap_manifold_resolved_dataset,
    normalize_manifold_market_to_dataset_row,
)


def test_normalize_manifold_market_to_dataset_row_maps_resolved_yes_market() -> None:
    row = normalize_manifold_market_to_dataset_row(
        {
            "id": "abc123",
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
    )

    assert row is not None
    assert row["market_id"] == "manifold:abc123"
    assert row["label"] == 1
    assert row["category"] == "weather"
    assert row["liquidity_bucket"] == "MID"
    assert row["snapshot_ts"] < row["resolution_ts"]


def test_normalize_manifold_market_to_dataset_row_rejects_unresolved_or_non_binary() -> None:
    assert normalize_manifold_market_to_dataset_row({"id": "x", "outcome_type": "BINARY", "resolution": "MKT"}) is None
    assert normalize_manifold_market_to_dataset_row({"id": "x", "outcome_type": "MULTIPLE_CHOICE", "resolution": "YES"}) is None


def test_normalize_manifold_market_to_dataset_row_infers_category_template_and_grouped_event() -> None:
    row = normalize_manifold_market_to_dataset_row(
        {
            "id": "movie1",
            "question": "Will there be any future celebrities in tonight's movie? (March 9 2026)",
            "probability": 0.41,
            "resolution": "NO",
            "outcome_type": "BINARY",
            "close_time": 1773000000000,
            "resolution_time": 1773003600000,
            "total_liquidity": 8000,
            "volume24_hours": 600,
            "slug": "will-there-be-any-future-celebrities-tonights-movie",
        }
    )

    assert row is not None
    assert row["category"] == "entertainment"
    assert row["template_group"] == "entertainment"
    assert row["market_template"] == "entertainment_event"
    assert row["event_id"] == "manifold:entertainment:tonights-movie:march-9-2026"


def test_normalize_manifold_market_to_dataset_row_infers_direct_rule_categories() -> None:
    row = normalize_manifold_market_to_dataset_row(
        {
            "id": "tech1",
            "question": "Will a PR be opened on manifoldmarkets/manifold today?",
            "probability": 0.58,
            "resolution": "YES",
            "outcome_type": "BINARY",
            "close_time": 1773000000000,
            "resolution_time": 1773003600000,
            "total_liquidity": 3000,
            "volume24_hours": 250,
            "slug": "will-a-pr-be-opened-on-manifoldmarkets-manifold-today",
        }
    )

    assert row is not None
    assert row["category"] == "technology"
    assert row["market_template"] == "binary_yes_no"


def test_bootstrap_summary_includes_category_and_template_counts(tmp_path, monkeypatch) -> None:
    class _FakeConnector:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def fetch_markets(self, *, limit: int = 500):
            return [
                {
                    "id": "macro1",
                    "question": "Will Nifty Close above 24050 10th March 2026",
                    "probability": 0.62,
                    "resolution": "YES",
                    "outcome_type": "BINARY",
                    "close_time": 1773000000000,
                    "resolution_time": 1773003600000,
                    "total_liquidity": 20000,
                    "volume24_hours": 1000,
                    "slug": "will-nifty-close-above-24050-10th-march-2026",
                },
                {
                    "id": "coin1",
                    "question": "Daily coinflip",
                    "probability": 0.5,
                    "resolution": "YES",
                    "outcome_type": "BINARY",
                    "close_time": 1773000000000,
                    "resolution_time": 1773003600000,
                    "total_liquidity": 500,
                    "volume24_hours": 50,
                    "slug": "daily-coinflip-abc123",
                },
            ]

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("scripts.bootstrap_manifold_resolved_dataset.ManifoldConnector", _FakeConnector)

    summary = asyncio.run(
        bootstrap_manifold_resolved_dataset(output_path=tmp_path / "bootstrap.csv", limit=2)
    )

    assert summary["resolved_rows"] == 2
    assert summary["unique_events"] == 2
    assert summary["category_counts"]["macro"] == 1
    assert summary["category_counts"]["games"] == 1
    assert summary["template_group_counts"]["numeric_threshold"] == 1
    assert summary["template_group_counts"]["games"] == 1
