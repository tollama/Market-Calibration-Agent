from __future__ import annotations

from agents.alert_agent import evaluate_alert


def test_evaluate_alert_high_when_all_strict_gates_hit_with_dual_structure_confirmation() -> None:
    result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.20,
        ambiguity_score=0.30,
        volume_velocity=2.10,
    )

    assert result == {
        "severity": "HIGH",
        "reason_codes": [
            "BAND_BREACH",
            "LOW_OI_CONFIRMATION",
            "LOW_AMBIGUITY",
            "VOLUME_SPIKE",
        ],
    }


def test_evaluate_alert_med_when_strict_gates_hit_with_single_structure_confirmation() -> None:
    result = evaluate_alert(
        p_yes=0.10,
        q10=0.20,
        q90=0.80,
        open_interest_change_1h=-0.20,
        ambiguity_score=0.30,
        volume_velocity=1.40,
    )

    assert result == {
        "severity": "MED",
        "reason_codes": [
            "BAND_BREACH",
            "LOW_OI_CONFIRMATION",
            "LOW_AMBIGUITY",
        ],
    }


def test_evaluate_alert_fyi_when_gate3_fails_even_with_band_breach_and_structure_confirmation() -> None:
    result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.80,
        open_interest_change_1h=-0.20,
        ambiguity_score=0.60,
        volume_velocity=2.10,
    )

    assert result == {
        "severity": "FYI",
        "reason_codes": [
            "BAND_BREACH",
            "LOW_OI_CONFIRMATION",
            "VOLUME_SPIKE",
        ],
    }
