"""Resolve final market labels from Gamma market/event metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

_SNAKE_CASE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_CASE_2 = re.compile(r"([a-z0-9])([A-Z])")

DEFAULT_STATUS_TOKENS: dict[str, frozenset[str]] = {
    "void": frozenset({"void", "invalid", "canceled", "cancelled"}),
    "unresolved": frozenset({"active", "open", "pending", "unresolved"}),
    "resolved": frozenset({"closed", "finalized", "resolved", "settled"}),
}
DEFAULT_BOOLEAN_TOKENS: dict[bool, frozenset[str]] = {
    True: frozenset({"1", "true", "yes", "y"}),
    False: frozenset({"0", "false", "no", "n"}),
}
DEFAULT_OUTCOME_ID_FALLBACK_STRATEGY = "index_as_string"

_VOID_TOKENS = DEFAULT_STATUS_TOKENS["void"]
_UNRESOLVED_STATUS_TOKENS = DEFAULT_STATUS_TOKENS["unresolved"]
_RESOLVED_STATUS_TOKENS = DEFAULT_STATUS_TOKENS["resolved"]
_TRUE_TOKENS = DEFAULT_BOOLEAN_TOKENS[True]
_FALSE_TOKENS = DEFAULT_BOOLEAN_TOKENS[False]


class LabelStatus(str, Enum):
    """Canonical label states for calibration pipelines."""

    RESOLVED_TRUE = "RESOLVED_TRUE"
    RESOLVED_FALSE = "RESOLVED_FALSE"
    VOID = "VOID"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class LabelResolution:
    """Resolved label payload with optional winning outcome metadata."""

    label_status: LabelStatus
    outcome_id: str | None = None
    reason: str | None = None


def resolve_label(metadata: Mapping[str, Any] | None) -> LabelResolution:
    """
    Resolve market/event metadata into a stable label state.

    The resolver is intentionally conservative:
    - Explicit VOID/invalid markers always return VOID.
    - Explicit unresolved/open markers return UNRESOLVED.
    - True/false resolution is emitted only for binary outcomes.
    """
    if not isinstance(metadata, Mapping):
        return LabelResolution(
            label_status=LabelStatus.UNRESOLVED,
            reason="metadata_not_mapping",
        )

    data = _normalize_mapping(metadata)
    if _is_void(data):
        return LabelResolution(label_status=LabelStatus.VOID, reason="void_or_invalid")

    if _is_unresolved(data):
        return LabelResolution(label_status=LabelStatus.UNRESOLVED, reason="status_not_final")

    winner = _extract_winner(data)
    if winner is not None:
        outcome_id, winner_token = winner
        value = _as_binary_value(winner_token)
        if value is True:
            return LabelResolution(
                label_status=LabelStatus.RESOLVED_TRUE,
                outcome_id=outcome_id,
            )
        if value is False:
            return LabelResolution(
                label_status=LabelStatus.RESOLVED_FALSE,
                outcome_id=outcome_id,
            )
        return LabelResolution(
            label_status=LabelStatus.UNRESOLVED,
            outcome_id=outcome_id,
            reason="non_binary_outcome",
        )

    if _has_resolved_marker(data):
        inferred = _infer_from_prices(data)
        if inferred is not None:
            return inferred
        return LabelResolution(
            label_status=LabelStatus.UNRESOLVED,
            reason="resolved_without_binary_winner",
        )

    return LabelResolution(label_status=LabelStatus.UNRESOLVED, reason="insufficient_metadata")


def _normalize_mapping(metadata: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized[_to_snake_case(str(key))] = value
    return normalized


def _to_snake_case(value: str) -> str:
    step_1 = _SNAKE_CASE_1.sub(r"\1_\2", value)
    return _SNAKE_CASE_2.sub(r"\1_\2", step_1).replace("-", "_").lower()


def _normalize_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    token = _normalize_token(value)
    if token is None:
        return None
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return None


def _coerce_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    token = _normalize_token(value)
    if token is None:
        return None
    if token.startswith("-"):
        return None
    if token.isdigit():
        return int(token)
    return None


def _is_void(data: Mapping[str, Any]) -> bool:
    status_token = _normalize_token(data.get("status"))
    if status_token in _VOID_TOKENS:
        return True

    for key in (
        "is_void",
        "voided",
        "is_invalid",
        "invalid",
        "is_canceled",
        "is_cancelled",
        "canceled",
        "cancelled",
    ):
        if _coerce_bool(data.get(key)) is True:
            return True

    for key in ("resolution", "resolved_outcome", "winning_outcome", "winner"):
        token = _normalize_token(data.get(key))
        if token in _VOID_TOKENS:
            return True
    return False


def _has_resolved_marker(data: Mapping[str, Any]) -> bool:
    status_token = _normalize_token(data.get("status"))
    if status_token in _RESOLVED_STATUS_TOKENS:
        return True

    for key in ("is_resolved", "resolved", "settled", "closed", "is_closed"):
        if _coerce_bool(data.get(key)) is True:
            return True
    return False


def _is_unresolved(data: Mapping[str, Any]) -> bool:
    status_token = _normalize_token(data.get("status"))
    if status_token in _UNRESOLVED_STATUS_TOKENS:
        return True

    for key in ("is_resolved", "resolved", "settled"):
        if _coerce_bool(data.get(key)) is False:
            return True
    return False


def _extract_winner(data: Mapping[str, Any]) -> tuple[str, str] | None:
    outcomes = _parse_sequence(data.get("outcomes"))
    outcome_ids = _parse_outcome_ids(data)

    for key in ("winning_outcome_index", "winner_index", "resolved_outcome_index"):
        index = _coerce_index(data.get(key))
        if index is None:
            continue
        winner = _winner_from_index(index, outcomes, outcome_ids)
        if winner is not None:
            return winner

    for key in ("winning_outcome_id", "winner_outcome_id", "resolved_outcome_id"):
        outcome_id = _normalize_token(data.get(key))
        if outcome_id is None:
            continue
        winner = _winner_from_id(outcome_id, outcomes, outcome_ids)
        if winner is not None:
            return winner

    for key in ("winning_outcome", "resolved_outcome", "winner", "resolution"):
        raw_value = data.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, bool):
            return ("1" if raw_value else "0", "yes" if raw_value else "no")

        index = _coerce_index(raw_value)
        if index is not None:
            winner = _winner_from_index(index, outcomes, outcome_ids)
            if winner is not None:
                return winner

        token = _normalize_token(raw_value)
        if token is None:
            continue

        match_index = _match_index(token, outcomes)
        if match_index is not None:
            winner = _winner_from_index(match_index, outcomes, outcome_ids)
            if winner is not None:
                return winner
        return token, token

    return None


def _parse_outcome_ids(data: Mapping[str, Any]) -> list[str]:
    for key in ("outcome_ids", "clob_token_ids", "token_ids", "tokens"):
        values = _parse_sequence(data.get(key))
        if values:
            return [str(value).strip() for value in values if str(value).strip()]
    return []


def _parse_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(parsed, list):
            return parsed
    return []


def _winner_from_index(
    index: int,
    outcomes: Sequence[Any],
    outcome_ids: Sequence[str],
) -> tuple[str, str] | None:
    if index < 0:
        return None
    if outcomes and index >= len(outcomes):
        return None
    outcome_id = (
        outcome_ids[index]
        if outcome_ids and index < len(outcome_ids)
        else _fallback_outcome_id(index)
    )
    token = str(outcomes[index]).strip().lower() if outcomes else str(index)
    return outcome_id, token


def _winner_from_id(
    outcome_id: str,
    outcomes: Sequence[Any],
    outcome_ids: Sequence[str],
) -> tuple[str, str] | None:
    if not outcome_id:
        return None

    if outcome_ids:
        for index, candidate in enumerate(outcome_ids):
            if candidate.strip().lower() == outcome_id:
                return _winner_from_index(index, outcomes, outcome_ids)

    index = _coerce_index(outcome_id)
    if index is not None:
        winner = _winner_from_index(index, outcomes, outcome_ids)
        if winner is not None:
            return winner

    if outcomes:
        match_index = _match_index(outcome_id, outcomes)
        if match_index is not None:
            return _winner_from_index(match_index, outcomes, outcome_ids)
    return outcome_id, outcome_id


def _match_index(token: str, outcomes: Sequence[Any]) -> int | None:
    for index, outcome in enumerate(outcomes):
        if str(outcome).strip().lower() == token:
            return index
    return None


def _as_binary_value(token: str) -> bool | None:
    normalized = token.strip().lower()
    if normalized in _TRUE_TOKENS or normalized.startswith("yes"):
        return True
    if normalized in _FALSE_TOKENS or normalized.startswith("no"):
        return False
    return None


def _infer_from_prices(data: Mapping[str, Any]) -> LabelResolution | None:
    prices = _parse_prices(data.get("outcome_prices"))
    outcomes = _parse_sequence(data.get("outcomes"))
    outcome_ids = _parse_outcome_ids(data)

    if len(prices) != 2 or len(outcomes) != 2:
        return None

    first = _as_binary_value(str(outcomes[0]).strip().lower())
    second = _as_binary_value(str(outcomes[1]).strip().lower())
    if first is None or second is None or first == second:
        return None

    yes_index = 0 if first else 1
    no_index = 1 if yes_index == 0 else 0
    yes_price = prices[yes_index]
    no_price = prices[no_index]
    yes_outcome_id = (
        outcome_ids[yes_index]
        if outcome_ids and yes_index < len(outcome_ids)
        else _fallback_outcome_id(yes_index)
    )
    no_outcome_id = (
        outcome_ids[no_index]
        if outcome_ids and no_index < len(outcome_ids)
        else _fallback_outcome_id(no_index)
    )

    if _is_one(yes_price) and _is_zero(no_price):
        return LabelResolution(
            label_status=LabelStatus.RESOLVED_TRUE,
            outcome_id=yes_outcome_id,
            reason="inferred_from_prices",
        )
    if _is_zero(yes_price) and _is_one(no_price):
        return LabelResolution(
            label_status=LabelStatus.RESOLVED_FALSE,
            outcome_id=no_outcome_id,
            reason="inferred_from_prices",
        )
    return None


def _parse_prices(value: Any) -> list[float]:
    values = _parse_sequence(value)
    parsed: list[float] = []
    for entry in values:
        try:
            parsed.append(float(entry))
        except (TypeError, ValueError):
            return []
    return parsed


def _is_zero(value: float) -> bool:
    return abs(value - 0.0) <= 1e-9


def _is_one(value: float) -> bool:
    return abs(value - 1.0) <= 1e-9


def _fallback_outcome_id(index: int) -> str:
    if DEFAULT_OUTCOME_ID_FALLBACK_STRATEGY == "index_as_string":
        return str(index)
    return str(index)
