from __future__ import annotations

import math
from typing import Mapping

W_LIQUIDITY = 0.35
W_STABILITY = 0.25
W_QUESTION_QUALITY = 0.25
W_MANIPULATION = 0.15

_COMPONENT_KEYS = (
    "liquidity_depth",
    "stability",
    "question_quality",
    "manipulation_suspect",
)

_DEFAULT_WEIGHTS: dict[str, float] = {
    "liquidity_depth": W_LIQUIDITY,
    "stability": W_STABILITY,
    "question_quality": W_QUESTION_QUALITY,
    "manipulation_suspect": W_MANIPULATION,
}


def _as_float(value: object, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"Non-finite value for {name}: {value}")
    return number


def _clip_unit(value: object, *, name: str) -> float:
    number = _as_float(value, name=name)
    if number <= 0.0:
        return 0.0
    if number >= 1.0:
        return 1.0
    return number


def _normalize_components(components: Mapping[str, object]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key in _COMPONENT_KEYS:
        if key not in components:
            raise ValueError(f"Missing trust component: {key}")
        normalized[key] = _clip_unit(components[key], name=key)
    return normalized


def _normalize_weights(weights: Mapping[str, object] | None) -> dict[str, float]:
    source = _DEFAULT_WEIGHTS if weights is None else weights

    normalized: dict[str, float] = {}
    for key in _COMPONENT_KEYS:
        raw = source[key] if key in source else _DEFAULT_WEIGHTS[key]
        value = _as_float(raw, name=f"weight.{key}")
        if value < 0:
            raise ValueError(f"Weight for {key} must be non-negative")
        normalized[key] = value

    total = sum(normalized[key] for key in _COMPONENT_KEYS)
    if total <= 0:
        raise ValueError("At least one trust score weight must be positive")

    return {key: normalized[key] / total for key in _COMPONENT_KEYS}


def compute_trust_components(
    *,
    liquidity_depth: object,
    stability: object,
    question_quality: object,
    manipulation_suspect: object,
) -> dict[str, float]:
    return {
        "liquidity_depth": _clip_unit(liquidity_depth, name="liquidity_depth"),
        "stability": _clip_unit(stability, name="stability"),
        "question_quality": _clip_unit(question_quality, name="question_quality"),
        "manipulation_suspect": _clip_unit(
            manipulation_suspect,
            name="manipulation_suspect",
        ),
    }


def compute_trust_score(
    components: Mapping[str, object],
    weights: Mapping[str, object] | None = None,
) -> float:
    normalized_components = _normalize_components(components)
    normalized_weights = _normalize_weights(weights)

    adjusted_components = dict(normalized_components)
    adjusted_components["manipulation_suspect"] = 1.0 - adjusted_components[
        "manipulation_suspect"
    ]

    score = 100.0 * sum(
        normalized_weights[key] * adjusted_components[key] for key in _COMPONENT_KEYS
    )
    return max(0.0, min(100.0, score))


def build_trust_score_row(
    market_id: object,
    ts: object,
    components: Mapping[str, object],
    weights: Mapping[str, object] | None = None,
    formula_version: str = "v1",
) -> dict[str, object]:
    normalized_components = _normalize_components(components)
    normalized_weights = _normalize_weights(weights)

    return {
        "market_id": market_id,
        "ts": ts,
        "trust_score": compute_trust_score(normalized_components, normalized_weights),
        "components": normalized_components,
        "weights": normalized_weights,
        "formula_version": formula_version,
    }


__all__ = [
    "W_LIQUIDITY",
    "W_STABILITY",
    "W_QUESTION_QUALITY",
    "W_MANIPULATION",
    "compute_trust_components",
    "compute_trust_score",
    "build_trust_score_row",
]
