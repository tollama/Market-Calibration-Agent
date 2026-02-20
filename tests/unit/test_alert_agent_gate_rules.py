from __future__ import annotations

from agents.alert_agent import AlertThresholds, evaluate_alert


def test_evaluate_alert_fyi_when_any_gate_missing() -> None:
    # Gate2/Gate3 missing
    band_only = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.50,
        volume_velocity=1.00,
    )
    assert band_only == {"severity": "FYI", "reason_codes": ["BAND_BREACH"]}

    # Gate2 missing (only Gate1/Gate3 hit)
    no_structure = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.35,
        volume_velocity=1.00,
    )
    assert no_structure == {
        "severity": "FYI",
        "reason_codes": ["BAND_BREACH", "LOW_AMBIGUITY"],
    }

    # Gate3 missing (only Gate1/Gate2 hit)
    no_low_ambiguity = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.36,
        volume_velocity=2.00,
    )
    assert no_low_ambiguity == {
        "severity": "FYI",
        "reason_codes": ["BAND_BREACH", "LOW_OI_CONFIRMATION", "VOLUME_SPIKE"],
    }


def test_evaluate_alert_med_boundary_when_gate1_to_gate3_met() -> None:
    result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.35,
        volume_velocity=1.99,
    )

    assert result == {
        "severity": "MED",
        "reason_codes": ["BAND_BREACH", "LOW_OI_CONFIRMATION", "LOW_AMBIGUITY"],
    }


def test_evaluate_alert_high_boundary_when_all_confirmations_hit() -> None:
    result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.35,
        volume_velocity=2.00,
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


def test_evaluate_alert_fyi_boundary_when_band_is_not_breached() -> None:
    result = evaluate_alert(
        p_yes=0.90,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.35,
        volume_velocity=2.00,
    )

    assert result == {
        "severity": "FYI",
        "reason_codes": ["LOW_OI_CONFIRMATION", "LOW_AMBIGUITY", "VOLUME_SPIKE"],
    }


def test_evaluate_alert_threshold_override_alias_mapping_keeps_api_compatibility() -> None:
    default_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.35,
        volume_velocity=1.00,
    )
    override_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.35,
        volume_velocity=1.00,
        thresholds={"low_oi_threshold": -0.05},
    )

    assert default_result == {
        "severity": "FYI",
        "reason_codes": ["BAND_BREACH", "LOW_AMBIGUITY"],
    }
    assert override_result == {
        "severity": "MED",
        "reason_codes": ["BAND_BREACH", "LOW_OI_CONFIRMATION", "LOW_AMBIGUITY"],
    }


def test_evaluate_alert_threshold_override_dataclass_keeps_api_compatibility() -> None:
    default_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.35,
        volume_velocity=1.50,
    )
    override_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.15,
        ambiguity_score=0.35,
        volume_velocity=1.50,
        thresholds=AlertThresholds(volume_spike=1.50),
    )

    assert default_result == {
        "severity": "MED",
        "reason_codes": ["BAND_BREACH", "LOW_OI_CONFIRMATION", "LOW_AMBIGUITY"],
    }
    assert override_result == {
        "severity": "HIGH",
        "reason_codes": [
            "BAND_BREACH",
            "LOW_OI_CONFIRMATION",
            "LOW_AMBIGUITY",
            "VOLUME_SPIKE",
        ],
    }
