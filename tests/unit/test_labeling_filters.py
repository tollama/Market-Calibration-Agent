from __future__ import annotations

from agents.label_resolver import LabelStatus
from calibration.labeling import (
    RESOLVED_FALSE,
    RESOLVED_TRUE,
    UNRESOLVED,
    VOID,
    split_by_label_status,
    to_binary_label_rows,
)


def test_split_by_label_status_counts_and_order() -> None:
    rows = [
        {"id": "a", "label_status": RESOLVED_TRUE},
        {"id": "b", "label_status": "resolved_false"},
        {"id": "c", "label_status": VOID},
        {"id": "d", "label_status": UNRESOLVED},
        {"id": "e", "label_status": "UNKNOWN"},
        {"id": "f"},
        {"id": "g", "label_status": LabelStatus.RESOLVED_TRUE},
    ]

    grouped = split_by_label_status(rows)

    assert set(grouped) == {"resolved_true", "resolved_false", "void", "unresolved"}
    assert [row["id"] for row in grouped["resolved_true"]] == ["a", "g"]
    assert [row["id"] for row in grouped["resolved_false"]] == ["b"]
    assert [row["id"] for row in grouped["void"]] == ["c"]
    assert [row["id"] for row in grouped["unresolved"]] == ["d", "e", "f"]


def test_to_binary_label_rows_filters_and_enriches() -> None:
    resolved_true_row = {"id": "a", "label_status": RESOLVED_TRUE, "pred": 0.9}
    resolved_false_row = {"id": "b", "label_status": LabelStatus.RESOLVED_FALSE}
    rows: list[object] = [
        resolved_true_row,
        resolved_false_row,
        {"id": "c", "label_status": VOID},
        {"id": "d", "label_status": UNRESOLVED},
        {"id": "e", "label_status": "UNKNOWN"},
        {"id": "f"},
        "not-a-row",
    ]

    converted = to_binary_label_rows(rows)

    assert [row["id"] for row in converted] == ["a", "b"]
    assert [row["y"] for row in converted] == [1, 0]
    assert converted[0] is not resolved_true_row
    assert converted[1] is not resolved_false_row
    assert "y" not in resolved_true_row
    assert "y" not in resolved_false_row


def test_to_binary_label_rows_supports_custom_status_key() -> None:
    rows = [
        {"id": "a", "status": RESOLVED_TRUE},
        {"id": "b", "status": RESOLVED_FALSE},
        {"id": "c", "status": VOID},
    ]

    converted = to_binary_label_rows(rows, status_key="status")

    assert [row["id"] for row in converted] == ["a", "b"]
    assert [row["y"] for row in converted] == [1, 0]
