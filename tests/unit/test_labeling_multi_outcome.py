from __future__ import annotations

from calibration.labeling import RESOLVED_FALSE, RESOLVED_TRUE, to_binary_label_rows


def test_to_binary_label_rows_excludes_multi_outcome_by_default() -> None:
    rows = [
        {"id": "binary_true", "label_status": RESOLVED_TRUE, "outcome_count": 2},
        {"id": "multi_by_count", "label_status": RESOLVED_FALSE, "outcome_count": 3},
        {"id": "multi_by_outcomes", "label_status": RESOLVED_TRUE, "outcomes": ["a", "b", "c"]},
        {"id": "multi_by_flag", "label_status": RESOLVED_FALSE, "is_multi_outcome": True},
        {"id": "binary_false", "label_status": RESOLVED_FALSE, "outcomes": ["yes", "no"]},
    ]

    converted = to_binary_label_rows(rows)

    assert [row["id"] for row in converted] == ["binary_true", "binary_false"]
    assert [row["y"] for row in converted] == [1, 0]


def test_to_binary_label_rows_include_multi_outcome_override() -> None:
    rows = [
        {"id": "binary_true", "label_status": RESOLVED_TRUE, "outcome_count": 2},
        {"id": "multi_by_count", "label_status": RESOLVED_FALSE, "outcome_count": 3},
        {"id": "multi_by_outcomes", "label_status": RESOLVED_TRUE, "outcomes": ["a", "b", "c"]},
        {"id": "multi_by_flag", "label_status": RESOLVED_FALSE, "is_multi_outcome": True},
    ]

    converted = to_binary_label_rows(rows, include_multi_outcome=True)

    assert [row["id"] for row in converted] == [
        "binary_true",
        "multi_by_count",
        "multi_by_outcomes",
        "multi_by_flag",
    ]
    assert [row["y"] for row in converted] == [1, 0, 1, 0]
