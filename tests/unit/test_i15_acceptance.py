from __future__ import annotations

from pipelines.build_alert_feed import build_alert_feed_rows


def test_i15_strict_gate_unmet_blocks_high_med_with_deterministic_output() -> None:
    # Strict gate semantics (as implemented in evaluate_alert):
    # Gate1 = BAND_BREACH, Gate2 = LOW_OI_CONFIRMATION or VOLUME_SPIKE,
    # Gate3 = LOW_AMBIGUITY. MED/HIGH requires all three gates.
    rows = [
        # Gate1 only -> FYI
        {
            "market_id": "mkt-g1-only",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.05,
            "ambiguity_score": 0.80,
            "volume_velocity": 1.10,
        },
        # Gate1 + Gate2 (low OI) but missing Gate3 -> FYI
        {
            "market_id": "mkt-g1-g2-only",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.80,
            "volume_velocity": 1.10,
        },
        # Gate1 + Gate3 but missing Gate2 -> FYI
        {
            "market_id": "mkt-g1-g3-only",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.10,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.05,
            "ambiguity_score": 0.30,
            "volume_velocity": 1.10,
        },
    ]

    first = build_alert_feed_rows(rows, include_fyi=True)
    second = build_alert_feed_rows(list(reversed(rows)), include_fyi=True)

    # With equal severity/timestamp, output must be deterministic by market_id.
    assert first == second
    assert [row["market_id"] for row in first] == [
        "mkt-g1-g2-only",
        "mkt-g1-g3-only",
        "mkt-g1-only",
    ]
    assert [row["severity"] for row in first] == ["FYI", "FYI", "FYI"]
