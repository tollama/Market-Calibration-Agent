from __future__ import annotations

from agents.alert_agent import evaluate_alert


def test_evaluate_alert_high_when_band_breach_has_confirmation() -> None:
    result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.20,
        ambiguity_score=0.60,
        volume_velocity=1.20,
    )

    assert result == {
        "severity": "HIGH",
        "reason_codes": ["BAND_BREACH", "LOW_OI_CONFIRMATION"],
    }


def test_evaluate_alert_med_for_band_breach_only() -> None:
    result = evaluate_alert(
        p_yes=0.10,
        q10=0.20,
        q90=0.80,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.70,
        volume_velocity=1.40,
    )

    assert result == {"severity": "MED", "reason_codes": ["BAND_BREACH"]}


def test_evaluate_alert_fyi_without_band_breach_with_ordered_reason_codes() -> None:
    result = evaluate_alert(
        p_yes=0.50,
        q10=0.20,
        q90=0.80,
        open_interest_change_1h=-0.20,
        ambiguity_score=0.35,
        volume_velocity=2.00,
    )

    assert result == {
        "severity": "FYI",
        "reason_codes": [
            "LOW_OI_CONFIRMATION",
            "LOW_AMBIGUITY",
            "VOLUME_SPIKE",
        ],
    }
