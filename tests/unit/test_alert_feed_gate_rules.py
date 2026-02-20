from __future__ import annotations

import pipelines.build_alert_feed as alert_feed
from pipelines.build_alert_feed import build_alert_feed_rows


def test_build_alert_feed_rows_combines_strict_and_min_trust_score_deterministically() -> None:
    rows = [
        {
            "market_id": "mkt-trust-blocked",
            "ts": "2026-02-20T14:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "trust_score": 59.9,
            "strict_gate_passed": True,
        },
        {
            "market_id": "mkt-strict-blocked",
            "ts": "2026-02-20T13:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "trust_score": 80.0,
            "strict_gate_result": {"passed": False},
        },
        {
            "market_id": "mkt-high-pass",
            "ts": "2026-02-20T12:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "trust_score": 75.0,
            "strict_gate_result": {"allow_high_med": True},
        },
        {
            "market_id": "mkt-med-pass",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "ambiguity_score": 0.30,
            "trust_score": 70.0,
            "strict_gate_passed": True,
        },
    ]

    first = build_alert_feed_rows(rows, min_trust_score=60.0)
    second = build_alert_feed_rows(list(reversed(rows)), min_trust_score=60.0)

    assert first == second
    assert [(row["severity"], row["market_id"]) for row in first] == [
        ("HIGH", "mkt-high-pass"),
        ("MED", "mkt-med-pass"),
    ]
    assert len({row["alert_id"] for row in first}) == len(first)


def test_build_alert_feed_rows_uses_evaluation_strict_gate_result(monkeypatch) -> None:
    def fake_evaluate_alert(**_: object) -> dict[str, object]:
        return {
            "severity": "HIGH",
            "reason_codes": ["BAND_BREACH"],
            "strict_gate_passed": False,
        }

    monkeypatch.setattr(alert_feed, "evaluate_alert", fake_evaluate_alert)

    rows = [
        {
            "market_id": "mkt-eval-gate",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "strict_gate_passed": True,
            "trust_score": 90.0,
        }
    ]

    assert build_alert_feed_rows(rows, min_trust_score=60.0) == []
