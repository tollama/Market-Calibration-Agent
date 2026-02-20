from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

import yaml

from calibration.trust_score import (
    W_LIQUIDITY,
    W_MANIPULATION,
    W_QUESTION_QUALITY,
    W_STABILITY,
)

_DEFAULT_CONFIG_PATH = Path("configs/default.yaml")
_ALLOWED_KEYS = (
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


def load_trust_weights(config_path: str | Path | None = None) -> dict[str, float]:
    """Load normalized trust-score weights from YAML configuration."""
    resolved_path = _DEFAULT_CONFIG_PATH if config_path is None else Path(config_path)
    overrides = _load_weight_overrides(resolved_path)
    return _normalize_weights(overrides)


def _load_weight_overrides(path: Path) -> Mapping[str, object] | None:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, Mapping):
        return None

    calibration = payload.get("calibration")
    if not isinstance(calibration, Mapping):
        return None

    trust_score = calibration.get("trust_score")
    if not isinstance(trust_score, Mapping):
        return None

    return trust_score


def _normalize_weights(overrides: Mapping[str, object] | None) -> dict[str, float]:
    weights: dict[str, float] = {}
    for key in _ALLOWED_KEYS:
        raw_value: object = _DEFAULT_WEIGHTS[key]
        if overrides is not None and key in overrides:
            raw_value = overrides[key]
        weight = _as_finite_float(raw_value, name=key)
        if weight < 0:
            raise ValueError(f"Weight for {key} must be non-negative")
        weights[key] = weight

    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one trust score weight must be positive")

    return {key: value / total for key, value in weights.items()}


def _as_finite_float(value: object, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value}") from exc
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"Non-finite numeric value for {name}: {value}")
    return number


__all__ = ["load_trust_weights"]
