import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from features import build_features


def _sample_cutoff_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_id": "A",
                "ts": "2026-02-20T00:20:00Z",
                "p_yes": 0.50,
                "volume_24h": 220.0,
                "open_interest": 900.0,
                "end_ts": "2026-02-21T00:00:00Z",
            },
            {
                "market_id": "B",
                "ts": "2026-02-20T00:00:00Z",
                "p_yes": 0.20,
                "volume_24h": 50.0,
                "open_interest": 50.0,
                "end_ts": "2026-02-20T00:30:00Z",
            },
            {
                "market_id": "A",
                "ts": "2026-02-20T00:00:00Z",
                "p_yes": 0.50,
                "volume_24h": 100.0,
                "open_interest": 1000.0,
                "end_ts": "2026-02-21T00:00:00Z",
            },
            {
                "market_id": "C",
                "ts": "2026-02-20T00:00:00Z",
                "p_yes": 0.70,
                "volume_24h": 500.0,
                "open_interest": 400.0,
                "end_ts": "2026-02-20T01:00:00Z",
            },
            {
                "market_id": "A",
                "ts": "2026-02-20T00:10:00Z",
                "p_yes": 0.55,
                "volume_24h": 160.0,
                "open_interest": 1200.0,
                "end_ts": "2026-02-21T00:00:00Z",
            },
            {
                "market_id": "B",
                "ts": "2026-02-20T00:15:00Z",
                "p_yes": 0.30,
                "volume_24h": 80.0,
                "open_interest": 75.0,
                "end_ts": "2026-02-20T00:30:00Z",
            },
        ]
    )


def test_build_features_computes_expected_values() -> None:
    result = build_features(
        _sample_cutoff_snapshot(),
        vol_window=2,
        liquidity_low=100.0,
        liquidity_high=1_000.0,
    )

    selected = result[
        [
            "market_id",
            "ts",
            "returns",
            "returns_3",
            "vol",
            "vol_3",
            "price_acceleration",
            "reversal_signal",
            "volume_velocity",
            "volume_acceleration",
            "oi_change",
            "oi_acceleration",
            "gap_minutes",
            "stale_gap_flag",
            "tte_seconds",
            "tte_hours",
            "tte_bucket",
            "price_distance_mid",
            "liquidity_bucket",
        ]
    ]

    expected = pd.DataFrame(
        {
            "market_id": ["A", "A", "A", "B", "B", "C"],
            "ts": pd.to_datetime(
                [
                    "2026-02-20T00:00:00Z",
                    "2026-02-20T00:10:00Z",
                    "2026-02-20T00:20:00Z",
                    "2026-02-20T00:00:00Z",
                    "2026-02-20T00:15:00Z",
                    "2026-02-20T00:00:00Z",
                ],
                utc=True,
            ),
            "returns": [0.0, 0.1, -0.0909090909090909, 0.0, 0.5, 0.0],
            "returns_3": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "vol": [0.0, 0.05, 0.0954545454545454, 0.0, 0.25, 0.0],
            "vol_3": [0.0, 0.05, 0.0779677595773856, 0.0, 0.25, 0.0],
            "price_acceleration": [0.0, 0.1, -0.1909090909090909, 0.0, 0.5, 0.0],
            "reversal_signal": [0.0, 0.0, 0.1909090909090909, 0.0, 0.0, 0.0],
            "volume_velocity": [0.0, 0.1, 0.1, 0.0, 0.0333333333333333, 0.0],
            "volume_acceleration": [0.0, 0.1, 0.0, 0.0, 0.0333333333333333, 0.0],
            "oi_change": [0.0, 0.2, -0.25, 0.0, 0.5, 0.0],
            "oi_acceleration": [0.0, 0.2, -0.45, 0.0, 0.5, 0.0],
            "gap_minutes": [0.0, 10.0, 10.0, 0.0, 15.0, 0.0],
            "stale_gap_flag": [0, 0, 0, 0, 0, 0],
            "tte_seconds": [86400.0, 85800.0, 85200.0, 1800.0, 900.0, 3600.0],
            "tte_hours": [24.0, 23.8333333333333, 23.6666666666667, 0.5, 0.25, 1.0],
            "tte_bucket": ["6-24h", "6-24h", "6-24h", "0-6h", "0-6h", "0-6h"],
            "price_distance_mid": [0.0, 0.1, 0.0, 0.6, 0.4, 0.4],
            "liquidity_bucket": ["HIGH", "HIGH", "MID", "LOW", "LOW", "MID"],
        }
    )

    assert selected["market_id"].tolist() == expected["market_id"].tolist()
    assert selected["ts"].tolist() == expected["ts"].tolist()
    assert selected["returns"].tolist() == pytest.approx(expected["returns"].tolist())
    assert selected["returns_3"].tolist() == pytest.approx(expected["returns_3"].tolist())
    assert selected["vol"].tolist() == pytest.approx(expected["vol"].tolist())
    assert selected["vol_3"].tolist() == pytest.approx(expected["vol_3"].tolist())
    assert selected["price_acceleration"].tolist() == pytest.approx(expected["price_acceleration"].tolist())
    assert selected["reversal_signal"].tolist() == pytest.approx(expected["reversal_signal"].tolist())
    assert selected["volume_velocity"].tolist() == pytest.approx(
        expected["volume_velocity"].tolist()
    )
    assert selected["volume_acceleration"].tolist() == pytest.approx(expected["volume_acceleration"].tolist())
    assert selected["oi_change"].tolist() == pytest.approx(expected["oi_change"].tolist())
    assert selected["oi_acceleration"].tolist() == pytest.approx(expected["oi_acceleration"].tolist())
    assert selected["gap_minutes"].tolist() == pytest.approx(expected["gap_minutes"].tolist())
    assert selected["stale_gap_flag"].tolist() == expected["stale_gap_flag"].tolist()
    assert selected["tte_seconds"].tolist() == pytest.approx(expected["tte_seconds"].tolist())
    assert selected["tte_hours"].tolist() == pytest.approx(expected["tte_hours"].tolist())
    assert selected["tte_bucket"].tolist() == expected["tte_bucket"].tolist()
    assert selected["price_distance_mid"].tolist() == pytest.approx(expected["price_distance_mid"].tolist())
    assert selected["liquidity_bucket"].tolist() == expected["liquidity_bucket"].tolist()


def test_build_features_is_deterministic_for_shuffled_input() -> None:
    cutoff = _sample_cutoff_snapshot()
    shuffled = cutoff.sample(frac=1.0, random_state=7).reset_index(drop=True)

    baseline = build_features(
        cutoff,
        vol_window=2,
        liquidity_low=100.0,
        liquidity_high=1_000.0,
    )
    comparison = build_features(
        shuffled,
        vol_window=2,
        liquidity_low=100.0,
        liquidity_high=1_000.0,
    )

    assert_frame_equal(baseline, comparison, check_like=False)


def test_build_features_prefers_existing_tte_seconds_and_normalizes_liquidity() -> None:
    cutoff = pd.DataFrame(
        [
            {
                "market_id": "X",
                "ts": "2026-02-20T00:00:00Z",
                "p_yes": 0.40,
                "volume_24h": 10.0,
                "open_interest": 15.0,
                "tte_seconds": 120.0,
                "liquidity_bucket": "mid",
            },
            {
                "market_id": "X",
                "ts": "2026-02-20T00:05:00Z",
                "p_yes": 0.40,
                "volume_24h": 10.0,
                "open_interest": 15.0,
                "tte_seconds": -3.0,
                "liquidity_bucket": "INVALID",
            },
            {
                "market_id": "X",
                "ts": "2026-02-20T00:10:00Z",
                "p_yes": 0.40,
                "volume_24h": 10.0,
                "open_interest": 15.0,
                "tte_seconds": None,
                "liquidity_bucket": None,
            },
        ]
    )

    result = build_features(cutoff, liquidity_low=5.0, liquidity_high=20.0)

    assert result["tte_seconds"].tolist() == pytest.approx([120.0, 0.0, 0.0])
    assert result["liquidity_bucket"].tolist() == ["MID", "MID", "MID"]
