"""Load alert policy thresholds from YAML configuration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from agents.alert_agent import AlertThresholds

_DEFAULT_CONFIG_PATH = Path("configs/alerts.yaml")
_THRESHOLD_KEY_ALIASES: dict[str, str] = {
    "low_oi_confirmation": "low_oi_confirmation",
    "low_oi_threshold": "low_oi_confirmation",
    "low_ambiguity": "low_ambiguity",
    "low_ambiguity_threshold": "low_ambiguity",
    "volume_spike": "volume_spike",
    "volume_spike_threshold": "volume_spike",
}


def load_alert_thresholds(config_path: str | Path | None = None) -> dict[str, float]:
    """Load alert thresholds from config, falling back to evaluate_alert defaults."""
    resolved = _default_thresholds()
    config = _load_alert_config(config_path)
    if not config:
        return resolved

    for section in _iter_candidate_sections(config):
        for raw_key, raw_value in section.items():
            canonical_key = _THRESHOLD_KEY_ALIASES.get(str(raw_key).lower())
            if canonical_key is None:
                continue
            resolved[canonical_key] = float(raw_value)

    return resolved


def load_alert_min_trust_score(config_path: str | Path | None = None) -> float | None:
    """Load optional min_trust_score from config and validate [0, 100] range."""
    config = _load_alert_config(config_path)
    if not config:
        return None

    found = False
    raw_value: object | None = None
    for section in _iter_candidate_sections(config):
        if "min_trust_score" in section:
            raw_value = section["min_trust_score"]
            found = True

    if not found or raw_value is None:
        return None

    try:
        parsed = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_trust_score must be numeric") from exc

    if parsed < 0.0 or parsed > 100.0:
        raise ValueError("min_trust_score must be within [0, 100]")
    return parsed


def _default_thresholds() -> dict[str, float]:
    defaults = AlertThresholds()
    return {
        "low_oi_confirmation": float(defaults.low_oi_confirmation),
        "low_ambiguity": float(defaults.low_ambiguity),
        "volume_spike": float(defaults.volume_spike),
    }


def _load_alert_config(config_path: str | Path | None) -> Mapping[str, Any]:
    resolved_path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH
    if not resolved_path.exists():
        return {}

    loaded = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, Mapping):
        raise ValueError("alert policy config must be a mapping")
    return loaded


def _iter_candidate_sections(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sections: list[Mapping[str, Any]] = []
    visited: set[int] = set()

    def visit(mapping: Mapping[str, Any]) -> None:
        marker = id(mapping)
        if marker in visited:
            return
        visited.add(marker)
        sections.append(mapping)

        for key in ("alerts", "alert_policy", "policy", "thresholds"):
            nested = mapping.get(key)
            if isinstance(nested, Mapping):
                visit(nested)

    visit(config)
    return sections
