"""Strict JSON schema parsing for LLM outputs."""

import json
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Mapping, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


class StrictJSONError(ValueError):
    """Raised when model output is not strict JSON matching a schema."""


@dataclass(frozen=True)
class QuestionQualityResult:
    """Result schema for question quality scoring."""

    ambiguity_score: float
    resolution_risk_score: float
    trigger_events: list[dict]
    rationale_bullets: list[str]

    def __post_init__(self) -> None:
        if self.ambiguity_score < 0 or self.ambiguity_score > 1:
            raise StrictJSONError("ambiguity_score must be between 0 and 1")
        if self.resolution_risk_score < 0 or self.resolution_risk_score > 1:
            raise StrictJSONError("resolution_risk_score must be between 0 and 1")
        if len(self.rationale_bullets) < 1 or len(self.rationale_bullets) > 5:
            raise StrictJSONError("rationale_bullets must contain between 1 and 5 items")


@dataclass(frozen=True)
class ExplainFiveLinesResult:
    """Result schema for 5-line explanation."""

    lines: list[str]

    def __post_init__(self) -> None:
        if len(self.lines) != 5:
            raise StrictJSONError("lines must contain exactly 5 items")
        for line in self.lines:
            if not line.strip():
                raise StrictJSONError("each line must be non-empty")


def parse_json_object(raw_text: str) -> dict[str, Any]:
    """Parse strict JSON object text."""
    if not isinstance(raw_text, str):
        raise StrictJSONError("raw_text must be a string")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StrictJSONError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise StrictJSONError("top-level JSON value must be an object")
    return payload


def parse_json_as(raw_text: str, schema: type[T]) -> T:
    """Parse and validate a JSON object as the provided dataclass schema."""
    payload = parse_json_object(raw_text)
    return from_dict_strict(payload, schema)


def from_dict_strict(data: Mapping[str, Any], schema: type[T]) -> T:
    """Strictly validate input mapping against a dataclass schema."""
    if not is_dataclass(schema):
        raise TypeError("schema must be a dataclass type")
    if not isinstance(data, Mapping):
        raise StrictJSONError("data must be a mapping")

    schema_fields = {field.name: field for field in fields(schema)}
    expected_keys = set(schema_fields)
    actual_keys = set(data)
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys

    if missing:
        missing_list = ", ".join(sorted(missing))
        raise StrictJSONError(f"missing required keys: {missing_list}")
    if extra:
        extra_list = ", ".join(sorted(extra))
        raise StrictJSONError(f"unexpected keys: {extra_list}")

    type_hints = get_type_hints(schema)
    normalized: dict[str, Any] = {}
    for name in schema_fields:
        expected_type = type_hints.get(name, Any)
        normalized[name] = _validate_type(data[name], expected_type, f"$.{name}")

    try:
        return schema(**normalized)
    except (TypeError, ValueError) as exc:
        raise StrictJSONError(str(exc)) from exc


def _validate_type(value: Any, expected_type: Any, path: str) -> Any:
    if expected_type is Any:
        return value

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin is Union:
        for option in args:
            try:
                return _validate_type(value, option, path)
            except StrictJSONError:
                continue
        raise StrictJSONError(f"{path} does not match any allowed type")

    if origin is list:
        if not isinstance(value, list):
            raise StrictJSONError(f"{path} must be a list")
        item_type = args[0] if args else Any
        return [_validate_type(item, item_type, f"{path}[{idx}]") for idx, item in enumerate(value)]

    if origin is dict:
        if not isinstance(value, dict):
            raise StrictJSONError(f"{path} must be an object")
        key_type = args[0] if len(args) >= 1 else Any
        value_type = args[1] if len(args) >= 2 else Any
        normalized: dict[Any, Any] = {}
        for key, nested_value in value.items():
            normalized_key = _validate_type(key, key_type, f"{path}.<key>")
            normalized_value = _validate_type(nested_value, value_type, f"{path}[{key!r}]")
            normalized[normalized_key] = normalized_value
        return normalized

    if is_dataclass(expected_type):
        if not isinstance(value, Mapping):
            raise StrictJSONError(f"{path} must be an object")
        return from_dict_strict(value, expected_type)

    if expected_type is bool:
        if not isinstance(value, bool):
            raise StrictJSONError(f"{path} must be a boolean")
        return value

    if expected_type is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise StrictJSONError(f"{path} must be an integer")
        return value

    if expected_type is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise StrictJSONError(f"{path} must be a number")
        return float(value)

    if expected_type is str:
        if not isinstance(value, str):
            raise StrictJSONError(f"{path} must be a string")
        return value

    if expected_type is type(None):
        if value is not None:
            raise StrictJSONError(f"{path} must be null")
        return value

    if not isinstance(value, expected_type):
        raise StrictJSONError(f"{path} has invalid type {type(value).__name__}")
    return value
