from __future__ import annotations

from pipelines.build_alert_feed import build_alert_feed_rows


def test_build_alert_feed_rows_min_trust_score_suppresses_below_threshold() -> None:
    rows = [
        {
            "market_id": "mkt-low-trust",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "trust_score": 59.9,
        },
        {
            "market_id": "mkt-at-threshold",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "trust_score": 60.0,
        },
        {
            "market_id": "mkt-missing-trust",
            "ts": "2026-02-20T12:00:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
        },
    ]

    alert_rows = build_alert_feed_rows(rows, min_trust_score=60.0)

    assert [row["market_id"] for row in alert_rows] == [
        "mkt-at-threshold",
        "mkt-missing-trust",
    ]
    assert [row["severity"] for row in alert_rows] == ["HIGH", "MED"]


def test_build_alert_feed_rows_min_trust_score_preserves_sort_and_alert_id_determinism() -> None:
    rows = [
        {
            "market_id": "mkt-b",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "trust_score": 70.0,
        },
        {
            "market_id": "mkt-c",
            "ts": "2026-02-20T12:30:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "trust_score": 90.0,
        },
        {
            "market_id": "mkt-a",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "trust_score": 75.0,
        },
        {
            "market_id": "mkt-suppressed",
            "ts": "2026-02-20T13:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "trust_score": 55.0,
        },
        {
            "market_id": "mkt-none-trust",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "trust_score": None,
        },
    ]

    first = build_alert_feed_rows(rows, min_trust_score=60.0)
    second = build_alert_feed_rows(list(reversed(rows)), min_trust_score=60.0)

    assert first == second
    assert [(row["severity"], row["market_id"]) for row in first] == [
        ("HIGH", "mkt-a"),
        ("HIGH", "mkt-b"),
        ("MED", "mkt-c"),
        ("MED", "mkt-none-trust"),
    ]
    assert len({row["alert_id"] for row in first}) == len(first)
