from __future__ import annotations

import json

import pytest

from llm.schemas import QuestionQualityResult, StrictJSONError, parse_json_as


def _valid_payload() -> dict[str, object]:
    return {
        "ambiguity_score": 0.22,
        "resolution_risk_score": 0.61,
        "trigger_events": [
            {"type": "regulatory_change", "market": "elections"},
            {"type": "data_revision", "source": "official_statement"},
        ],
        "rationale_bullets": [
            "Question includes a clear event definition.",
            "Resolution still depends on external adjudication timing.",
        ],
    }


def test_question_quality_schema_accepts_valid_payload() -> None:
    raw = json.dumps(_valid_payload())

    parsed = parse_json_as(raw, QuestionQualityResult)

    assert parsed.ambiguity_score == pytest.approx(0.22)
    assert parsed.resolution_risk_score == pytest.approx(0.61)
    assert len(parsed.trigger_events) == 2
    assert len(parsed.rationale_bullets) == 2


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("ambiguity_score", -0.01, "ambiguity_score must be between 0 and 1"),
        ("ambiguity_score", 1.01, "ambiguity_score must be between 0 and 1"),
        (
            "resolution_risk_score",
            -0.01,
            "resolution_risk_score must be between 0 and 1",
        ),
        (
            "resolution_risk_score",
            1.01,
            "resolution_risk_score must be between 0 and 1",
        ),
    ],
)
def test_question_quality_schema_rejects_out_of_bounds_scores(
    field_name: str,
    invalid_value: float,
    message: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = invalid_value
    raw = json.dumps(payload)

    with pytest.raises(StrictJSONError, match=message):
        parse_json_as(raw, QuestionQualityResult)


@pytest.mark.parametrize(
    "bullets",
    [
        [],
        [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
        ],
    ],
)
def test_question_quality_schema_rejects_invalid_bullet_count(
    bullets: list[str],
) -> None:
    payload = _valid_payload()
    payload["rationale_bullets"] = bullets
    raw = json.dumps(payload)

    with pytest.raises(
        StrictJSONError, match="rationale_bullets must contain between 1 and 5 items"
    ):
        parse_json_as(raw, QuestionQualityResult)


def test_question_quality_schema_rejects_missing_required_keys() -> None:
    payload = _valid_payload()
    payload.pop("trigger_events")
    raw = json.dumps(payload)

    with pytest.raises(StrictJSONError, match="missing required keys: trigger_events"):
        parse_json_as(raw, QuestionQualityResult)
