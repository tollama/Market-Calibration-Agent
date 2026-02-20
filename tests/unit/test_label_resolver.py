from __future__ import annotations

from agents.label_resolver import LabelStatus, resolve_label


def test_resolve_label_resolved_true() -> None:
    result = resolve_label(
        {
            "status": "RESOLVED",
            "outcomes": ["Yes", "No"],
            "winningOutcomeIndex": 0,
            "clobTokenIds": ["yes-token", "no-token"],
        }
    )

    assert result.label_status is LabelStatus.RESOLVED_TRUE
    assert result.outcome_id == "yes-token"
    assert result.reason is None


def test_resolve_label_resolved_false() -> None:
    result = resolve_label(
        {
            "status": "RESOLVED",
            "outcomes": ["Yes", "No"],
            "resolved_outcome": "No",
        }
    )

    assert result.label_status is LabelStatus.RESOLVED_FALSE
    assert result.outcome_id == "1"
    assert result.reason is None


def test_resolve_label_void() -> None:
    result = resolve_label(
        {
            "status": "VOID",
            "outcomes": ["Yes", "No"],
            "winning_outcome": "Yes",
        }
    )

    assert result.label_status is LabelStatus.VOID
    assert result.outcome_id is None
    assert result.reason == "void_or_invalid"


def test_resolve_label_unresolved() -> None:
    result = resolve_label(
        {
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        }
    )

    assert result.label_status is LabelStatus.UNRESOLVED
    assert result.outcome_id is None
    assert result.reason == "status_not_final"


def test_resolve_label_malformed_input() -> None:
    result = resolve_label(["not", "a", "mapping"])  # type: ignore[arg-type]

    assert result.label_status is LabelStatus.UNRESOLVED
    assert result.outcome_id is None
    assert result.reason == "metadata_not_mapping"


def test_resolve_label_infers_true_from_prices_without_explicit_winner() -> None:
    result = resolve_label(
        {
            "status": "RESOLVED",
            "outcomes": ["Yes", "No"],
            "outcome_prices": [1, 0],
        }
    )

    assert result.label_status is LabelStatus.RESOLVED_TRUE
    assert result.outcome_id == "0"
    assert result.reason == "inferred_from_prices"


def test_resolve_label_resolved_marker_non_binary_outcomes_is_unresolved() -> None:
    result = resolve_label(
        {
            "status": "RESOLVED",
            "outcomes": ["Up", "Down"],
            "outcome_prices": [1, 0],
        }
    )

    assert result.label_status is LabelStatus.UNRESOLVED
    assert result.outcome_id is None
    assert result.reason == "resolved_without_binary_winner"
