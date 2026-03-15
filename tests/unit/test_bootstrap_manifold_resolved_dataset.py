from __future__ import annotations

from scripts.bootstrap_manifold_resolved_dataset import normalize_manifold_market_to_dataset_row


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
