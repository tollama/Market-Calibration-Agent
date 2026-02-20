from __future__ import annotations

from agents.alert_agent import AlertThresholds, evaluate_alert
from pipelines.build_alert_feed import build_alert_feed_rows


def test_evaluate_alert_threshold_overrides_with_mapping_changes_severity() -> None:
    default_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.30,
        volume_velocity=2.10,
    )
    override_result = evaluate_alert(
        p_yes=0.95,
        q10=0.20,
        q90=0.90,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.30,
        volume_velocity=2.10,
        thresholds={"low_oi_confirmation": -0.05},
    )

    assert default_result == {
        "severity": "MED",
        "reason_codes": ["BAND_BREACH", "LOW_AMBIGUITY", "VOLUME_SPIKE"],
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


def test_evaluate_alert_threshold_overrides_with_dataclass_preserves_reason_order() -> None:
    result = evaluate_alert(
        p_yes=0.50,
        q10=0.20,
        q90=0.80,
        open_interest_change_1h=-0.10,
        ambiguity_score=0.40,
        volume_velocity=1.90,
        thresholds=AlertThresholds(
            low_oi_confirmation=-0.05,
            low_ambiguity=0.50,
            volume_spike=1.50,
        ),
    )

    assert result == {
        "severity": "FYI",
        "reason_codes": [
            "LOW_OI_CONFIRMATION",
            "LOW_AMBIGUITY",
            "VOLUME_SPIKE",
        ],
    }


def test_build_alert_feed_rows_include_fyi_flag() -> None:
    rows = [
        {
            "market_id": "mkt-fyi",
            "ts": "2026-02-20T10:00:00Z",
            "p_yes": 0.50,
            "q10": 0.20,
            "q90": 0.80,
            "open_interest_change_1h": -0.20,
        }
    ]

    excluded = build_alert_feed_rows(rows)
    included = build_alert_feed_rows(rows, include_fyi=True)

    assert excluded == []
    assert [row["severity"] for row in included] == ["FYI"]
    assert included[0]["reason_codes"] == ["LOW_OI_CONFIRMATION"]


def test_build_alert_feed_rows_threshold_overrides_change_severity() -> None:
    rows = [
        {
            "market_id": "mkt-med-default-high-override",
            "ts": "2026-02-20T11:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.10,
            "ambiguity_score": 0.30,
            "volume_velocity": 2.10,
            "strict_gate_passed": True,
        }
    ]

    default_alert_rows = build_alert_feed_rows(rows)
    override_alert_rows = build_alert_feed_rows(
        rows, thresholds={"low_oi_confirmation": -0.05}
    )

    assert [row["severity"] for row in default_alert_rows] == ["MED"]
    assert default_alert_rows[0]["reason_codes"] == [
        "BAND_BREACH",
        "LOW_AMBIGUITY",
        "VOLUME_SPIKE",
    ]
    assert [row["severity"] for row in override_alert_rows] == ["HIGH"]
    assert override_alert_rows[0]["reason_codes"] == [
        "BAND_BREACH",
        "LOW_OI_CONFIRMATION",
        "LOW_AMBIGUITY",
        "VOLUME_SPIKE",
    ]
