import math

import pytest

from pipelines.aggregate_intraday_bars import build_time_bars, resample_to_5m


def _assert_bar_matches(actual: dict, expected: dict) -> None:
    assert actual["market_id"] == expected["market_id"]
    assert actual["start_ts"] == expected["start_ts"]
    assert actual["end_ts"] == expected["end_ts"]
    assert actual["count"] == expected["count"]
    assert actual["open"] == pytest.approx(expected["open"])
    assert actual["high"] == pytest.approx(expected["high"])
    assert actual["low"] == pytest.approx(expected["low"])
    assert actual["close"] == pytest.approx(expected["close"])


def test_build_time_bars_computes_ohlc_per_market_bucket() -> None:
    rows = [
        {"market_id": "MKT-B", "ts": 122, "p_yes": 0.40},
        {"market_id": "MKT-A", "ts": 61, "p_yes": 0.20, "volume_24h": 100.0},
        {"market_id": "MKT-A", "ts": 119, "p_yes": 0.50, "open_interest": 220.0},
        {"market_id": "MKT-A", "ts": 65, "p_yes": 0.10},
        {"market_id": "MKT-A", "ts": 125, "p_yes": 0.70},
        {"market_id": "MKT-B", "ts": 121, "p_yes": 0.30},
        {"market_id": "MKT-B", "ts": 179, "p_yes": 0.20},
    ]

    bars = build_time_bars(rows, interval_seconds=60)
    expected = [
        {
            "market_id": "MKT-A",
            "start_ts": 60,
            "end_ts": 119,
            "open": 0.20,
            "high": 0.50,
            "low": 0.10,
            "close": 0.50,
            "count": 3,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 120,
            "end_ts": 179,
            "open": 0.70,
            "high": 0.70,
            "low": 0.70,
            "close": 0.70,
            "count": 1,
        },
        {
            "market_id": "MKT-B",
            "start_ts": 120,
            "end_ts": 179,
            "open": 0.30,
            "high": 0.40,
            "low": 0.20,
            "close": 0.20,
            "count": 3,
        },
    ]

    assert len(bars) == len(expected)
    for actual, expected_bar in zip(bars, expected):
        _assert_bar_matches(actual, expected_bar)


def test_build_time_bars_orders_output_by_market_then_start_ts() -> None:
    rows = [
        {"market_id": "MKT-Z", "ts": 310, "p_yes": 0.20},
        {"market_id": "MKT-A", "ts": 125, "p_yes": 0.30},
        {"market_id": "MKT-Z", "ts": 65, "p_yes": 0.60},
        {"market_id": "MKT-A", "ts": 62, "p_yes": 0.50},
        {"market_id": "MKT-A", "ts": 61, "p_yes": 0.10},
    ]

    bars = build_time_bars(rows, interval_seconds=60)

    assert [(bar["market_id"], bar["start_ts"]) for bar in bars] == [
        ("MKT-A", 60),
        ("MKT-A", 120),
        ("MKT-Z", 60),
        ("MKT-Z", 300),
    ]


def test_resample_to_5m_rolls_up_one_minute_bars() -> None:
    bars_1m = [
        {
            "market_id": "MKT-A",
            "start_ts": 300,
            "end_ts": 359,
            "open": 2.2,
            "high": 2.4,
            "low": 2.1,
            "close": 2.3,
            "count": 1,
        },
        {
            "market_id": "MKT-B",
            "start_ts": 120,
            "end_ts": 179,
            "open": 0.45,
            "high": 0.48,
            "low": 0.40,
            "close": 0.42,
            "count": 1,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 60,
            "end_ts": 119,
            "open": 1.6,
            "high": 1.8,
            "low": 1.4,
            "close": 1.7,
            "count": 3,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 0,
            "end_ts": 59,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "count": 2,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 180,
            "end_ts": 239,
            "open": 2.0,
            "high": 2.2,
            "low": 1.9,
            "close": 2.1,
            "count": 2,
        },
        {
            "market_id": "MKT-B",
            "start_ts": 60,
            "end_ts": 119,
            "open": 0.4,
            "high": 0.5,
            "low": 0.3,
            "close": 0.45,
            "count": 1,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 120,
            "end_ts": 179,
            "open": 1.7,
            "high": 2.1,
            "low": 1.6,
            "close": 2.0,
            "count": 1,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 240,
            "end_ts": 299,
            "open": 2.1,
            "high": 2.3,
            "low": 2.0,
            "close": 2.2,
            "count": 2,
        },
    ]

    bars_5m = resample_to_5m(bars_1m)
    expected = [
        {
            "market_id": "MKT-A",
            "start_ts": 0,
            "end_ts": 299,
            "open": 1.0,
            "high": 2.3,
            "low": 0.5,
            "close": 2.2,
            "count": 10,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 300,
            "end_ts": 599,
            "open": 2.2,
            "high": 2.4,
            "low": 2.1,
            "close": 2.3,
            "count": 1,
        },
        {
            "market_id": "MKT-B",
            "start_ts": 0,
            "end_ts": 299,
            "open": 0.4,
            "high": 0.5,
            "low": 0.3,
            "close": 0.42,
            "count": 2,
        },
    ]

    assert len(bars_5m) == len(expected)
    for actual, expected_bar in zip(bars_5m, expected):
        _assert_bar_matches(actual, expected_bar)


def test_build_time_bars_adds_trade_count_volume_and_realized_vol() -> None:
    rows = [
        {"market_id": "MKT-A", "ts": 61, "p_yes": 121.0, "size": 4.0},
        {"market_id": "MKT-A", "ts": 20, "p_yes": 121.0},
        {"market_id": "MKT-A", "ts": 0, "p_yes": 100.0, "size": 2.0},
        {"market_id": "MKT-A", "ts": 10, "p_yes": 110.0, "size": 3.0},
    ]

    bars = build_time_bars(rows, interval_seconds=60)

    assert len(bars) == 2

    expected_rv = math.sqrt(math.log(110.0 / 100.0) ** 2 + math.log(121.0 / 110.0) ** 2)
    assert bars[0]["market_id"] == "MKT-A"
    assert bars[0]["start_ts"] == 0
    assert bars[0]["count"] == 3
    assert bars[0]["trade_count"] == 3
    assert bars[0]["volume_sum"] == pytest.approx(5.0)
    assert bars[0]["realized_vol"] == pytest.approx(expected_rv)

    assert bars[1]["market_id"] == "MKT-A"
    assert bars[1]["start_ts"] == 60
    assert bars[1]["count"] == 1
    assert bars[1]["trade_count"] == 1
    assert bars[1]["volume_sum"] == pytest.approx(4.0)
    assert bars[1]["realized_vol"] == pytest.approx(0.0)


def test_resample_to_5m_rolls_up_volume_trade_count_and_realized_vol() -> None:
    bars_1m = [
        {
            "market_id": "MKT-A",
            "start_ts": 120,
            "end_ts": 179,
            "open": 101.0,
            "high": 103.0,
            "low": 100.8,
            "close": 102.0,
            "count": 3,
            "trade_count": 3,
            "volume_sum": 0.0,
            "realized_vol": 0.0,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 0,
            "end_ts": 59,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "count": 2,
            "volume_sum": 2.5,
            "realized_vol": 0.1,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 300,
            "end_ts": 359,
            "open": 102.0,
            "high": 104.0,
            "low": 101.5,
            "close": 103.0,
            "trade_count": 1,
            "volume_sum": 4.0,
            "realized_vol": 0.3,
        },
        {
            "market_id": "MKT-A",
            "start_ts": 60,
            "end_ts": 119,
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.0,
            "trade_count": 1,
            "volume_sum": 1.5,
            "realized_vol": 0.2,
        },
    ]

    bars_5m = resample_to_5m(bars_1m)

    assert len(bars_5m) == 2

    first_bar = bars_5m[0]
    assert first_bar["market_id"] == "MKT-A"
    assert first_bar["start_ts"] == 0
    assert first_bar["end_ts"] == 299
    assert first_bar["open"] == pytest.approx(100.0)
    assert first_bar["high"] == pytest.approx(103.0)
    assert first_bar["low"] == pytest.approx(99.0)
    assert first_bar["close"] == pytest.approx(102.0)
    assert first_bar["count"] == 6
    assert first_bar["trade_count"] == 6
    assert first_bar["volume_sum"] == pytest.approx(4.0)
    assert first_bar["realized_vol"] == pytest.approx(math.sqrt(0.1**2 + 0.2**2))

    second_bar = bars_5m[1]
    assert second_bar["market_id"] == "MKT-A"
    assert second_bar["start_ts"] == 300
    assert second_bar["end_ts"] == 599
    assert second_bar["open"] == pytest.approx(102.0)
    assert second_bar["high"] == pytest.approx(104.0)
    assert second_bar["low"] == pytest.approx(101.5)
    assert second_bar["close"] == pytest.approx(103.0)
    assert second_bar["count"] == 1
    assert second_bar["trade_count"] == 1
    assert second_bar["volume_sum"] == pytest.approx(4.0)
    assert second_bar["realized_vol"] == pytest.approx(0.3)
