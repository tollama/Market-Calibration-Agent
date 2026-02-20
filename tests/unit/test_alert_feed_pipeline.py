from __future__ import annotations

from pipelines.build_alert_feed import build_alert_feed_rows


def test_build_alert_feed_rows_includes_high_and_med_excludes_fyi() -> None:
    rows = [
        {
            "market_id": "mkt-fyi",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.50,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.40,
        },
        {
            "market_id": "mkt-med",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
        },
        {
            "market_id": "mkt-high",
            "ts": "2026-02-20T09:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.40,
        },
    ]

    alert_rows = build_alert_feed_rows(rows)

    assert [row["severity"] for row in alert_rows] == ["HIGH", "MED"]
    assert [row["market_id"] for row in alert_rows] == ["mkt-high", "mkt-med"]
    assert all(row["alert_id"] for row in alert_rows)

    high_row = alert_rows[0]
    assert high_row["reason_codes"] == [
        "BAND_BREACH",
        "LOW_OI_CONFIRMATION",
        "LOW_AMBIGUITY",
        "VOLUME_SPIKE",
    ]
    assert high_row["evidence"] == {
        "p_yes": 0.95,
        "q10": 0.20,
        "q90": 0.90,
        "oi_change_1h": -0.20,
        "ambiguity_score": 0.30,
        "volume_velocity": 2.40,
    }

    med_row = alert_rows[1]
    assert med_row["reason_codes"] == [
        "BAND_BREACH",
        "LOW_OI_CONFIRMATION",
        "LOW_AMBIGUITY",
    ]
    assert med_row["evidence"] == {
        "p_yes": 0.10,
        "q10": 0.20,
        "q90": 0.80,
        "oi_change_1h": -0.20,
        "ambiguity_score": 0.30,
    }


def test_build_alert_feed_rows_sorting_and_hash_are_deterministic() -> None:
    rows = [
        {
            "market_id": "mkt-2",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.20,
        },
        {
            "market_id": "mkt-3",
            "ts": "2026-02-20T12:30:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
        },
        {
            "market_id": "mkt-1",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.30,
        },
    ]

    first = build_alert_feed_rows(rows)
    second = build_alert_feed_rows(list(reversed(rows)))

    assert first == second
    assert [(row["severity"], row["market_id"]) for row in first] == [
        ("HIGH", "mkt-1"),
        ("HIGH", "mkt-2"),
        ("MED", "mkt-3"),
    ]
    assert len({row["alert_id"] for row in first}) == len(first)
