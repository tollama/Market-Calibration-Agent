from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

RESOLVED_TRUE = "RESOLVED_TRUE"
RESOLVED_FALSE = "RESOLVED_FALSE"
VOID = "VOID"
UNRESOLVED = "UNRESOLVED"

_DEFAULT_STATUS_KEY = "label_status"


def _normalize_status(value: object) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        value = enum_value
    token = str(value).strip().upper()
    return token or None


def _effective_status_key(status_key: object) -> str:
    if isinstance(status_key, str) and status_key:
        return status_key
    return _DEFAULT_STATUS_KEY


def _status_from_row(row: object, *, status_key: str) -> str | None:
    if not isinstance(row, Mapping):
        return None
    return _normalize_status(row.get(status_key))


def split_by_label_status(rows: Sequence[object]) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = {
        "resolved_true": [],
        "resolved_false": [],
        "void": [],
        "unresolved": [],
    }

    for row in rows:
        status = _status_from_row(row, status_key=_DEFAULT_STATUS_KEY)
        if status == RESOLVED_TRUE:
            grouped["resolved_true"].append(row)
        elif status == RESOLVED_FALSE:
            grouped["resolved_false"].append(row)
        elif status == VOID:
            grouped["void"].append(row)
        else:
            grouped["unresolved"].append(row)
    return grouped


def to_binary_label_rows(
    rows: Sequence[object],
    *,
    status_key: str = _DEFAULT_STATUS_KEY,
) -> list[dict[str, Any]]:
    resolved_key = _effective_status_key(status_key)
    converted: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        status = _status_from_row(row, status_key=resolved_key)
        if status == RESOLVED_TRUE:
            y = 1
        elif status == RESOLVED_FALSE:
            y = 0
        else:
            continue

        enriched = dict(row)
        enriched["y"] = y
        converted.append(enriched)

    return converted


__all__ = [
    "RESOLVED_TRUE",
    "RESOLVED_FALSE",
    "VOID",
    "UNRESOLVED",
    "split_by_label_status",
    "to_binary_label_rows",
]
