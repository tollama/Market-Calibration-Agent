"""Rule-based alert severity evaluation."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import Mapping, Union

BAND_BREACH = "BAND_BREACH"
LOW_OI_CONFIRMATION = "LOW_OI_CONFIRMATION"
LOW_AMBIGUITY = "LOW_AMBIGUITY"
VOLUME_SPIKE = "VOLUME_SPIKE"

_REASON_CODE_ORDER: tuple[str, ...] = (
    BAND_BREACH,
    LOW_OI_CONFIRMATION,
    LOW_AMBIGUITY,
    VOLUME_SPIKE,
)

_LOW_OI_THRESHOLD = -0.15
_LOW_AMBIGUITY_THRESHOLD = 0.35
_VOLUME_SPIKE_THRESHOLD = 2.0


@dataclass(frozen=True)
class AlertThresholds:
    """Thresholds used by non-band confirmation gates."""

    low_oi_confirmation: float = _LOW_OI_THRESHOLD
    low_ambiguity: float = _LOW_AMBIGUITY_THRESHOLD
    volume_spike: float = _VOLUME_SPIKE_THRESHOLD


AlertThresholdConfig = Union[AlertThresholds, Mapping[str, float]]

_THRESHOLD_KEY_TO_FIELD: dict[str, str] = {
    "low_oi_confirmation": "low_oi_confirmation",
    "low_oi_threshold": "low_oi_confirmation",
    "low_ambiguity": "low_ambiguity",
    "low_ambiguity_threshold": "low_ambiguity",
    "volume_spike": "volume_spike",
    "volume_spike_threshold": "volume_spike",
}


def evaluate_alert(
    p_yes: float,
    q10: float,
    q90: float,
    open_interest_change_1h: float | None = None,
    ambiguity_score: float | None = None,
    volume_velocity: float | None = None,
    *,
    oi_change_1h: float | None = None,
    thresholds: AlertThresholdConfig | None = None,
) -> dict[str, object]:
    """Evaluate alert gates and derive severity/reason codes."""

    oi_change = (
        open_interest_change_1h if open_interest_change_1h is not None else oi_change_1h
    )
    configured_thresholds = _resolve_thresholds(thresholds)
    gate_hits = {
        BAND_BREACH: p_yes < q10 or p_yes > q90,
        LOW_OI_CONFIRMATION: (
            oi_change is not None and oi_change <= configured_thresholds.low_oi_confirmation
        ),
        LOW_AMBIGUITY: (
            ambiguity_score is not None
            and ambiguity_score <= configured_thresholds.low_ambiguity
        ),
        VOLUME_SPIKE: (
            volume_velocity is not None
            and volume_velocity >= configured_thresholds.volume_spike
        ),
    }

    gate1_band_breach = gate_hits[BAND_BREACH]
    gate2_structure = gate_hits[LOW_OI_CONFIRMATION] or gate_hits[VOLUME_SPIKE]
    gate3_low_ambiguity = gate_hits[LOW_AMBIGUITY]

    reason_codes = [code for code in _REASON_CODE_ORDER if gate_hits[code]]
    if gate1_band_breach and gate2_structure and gate3_low_ambiguity:
        if gate_hits[LOW_OI_CONFIRMATION] and gate_hits[VOLUME_SPIKE]:
            severity = "HIGH"
        else:
            severity = "MED"
    else:
        severity = "FYI"

    return {"severity": severity, "reason_codes": reason_codes}


def _resolve_thresholds(thresholds: AlertThresholdConfig | None) -> AlertThresholds:
    if thresholds is None:
        return AlertThresholds()
    if isinstance(thresholds, AlertThresholds):
        return thresholds
    if not isinstance(thresholds, MappingABC):
        raise TypeError("thresholds must be a mapping or AlertThresholds")

    resolved = AlertThresholds()
    updates: dict[str, float] = {}
    for key, value in thresholds.items():
        key_str = str(key)
        field = _THRESHOLD_KEY_TO_FIELD.get(key_str)
        if field is None:
            raise ValueError(f"Unsupported threshold key: {key_str}")
        updates[field] = float(value)

    return AlertThresholds(
        low_oi_confirmation=updates.get(
            "low_oi_confirmation", resolved.low_oi_confirmation
        ),
        low_ambiguity=updates.get("low_ambiguity", resolved.low_ambiguity),
        volume_spike=updates.get("volume_spike", resolved.volume_spike),
    )
