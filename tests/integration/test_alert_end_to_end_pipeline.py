from __future__ import annotations

from pipelines.build_alert_feed import build_alert_feed_rows


def test_i15_end_to_end_alert_gate_transitions_are_deterministic() -> None:
    """Traceability: PRD1 I-15 (Gate1+Gate2+Gate3 severity transitions in end-to-end feed build)."""
    rows = [
        # HIGH: band breach + low OI + volume spike + low ambiguity
        {
            "market_id": "mkt-high",
            "ts": "2026-02-20T12:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "strict_gate_passed": True,
            "trust_score": 80.0,
        },
        # MED: band breach + (low OI only) + low ambiguity
        {
            "market_id": "mkt-med",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 1.2,
            "ambiguity_score": 0.30,
            "strict_gate_passed": True,
            "trust_score": 80.0,
        },
        # FYI: gate3 fails
        {
            "market_id": "mkt-fyi",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.70,
            "strict_gate_passed": True,
            "trust_score": 80.0,
        },
    ]

    first = build_alert_feed_rows(rows, include_fyi=True, min_trust_score=60.0)
    second = build_alert_feed_rows(list(reversed(rows)), include_fyi=True, min_trust_score=60.0)

    assert first == second
    assert [(a["market_id"], a["severity"]) for a in first] == [
        ("mkt-high", "HIGH"),
        ("mkt-med", "MED"),
        ("mkt-fyi", "FYI"),
    ]
