"""Rule-based alert severity evaluation."""

from __future__ import annotations

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


def evaluate_alert(
    p_yes: float,
    q10: float,
    q90: float,
    open_interest_change_1h: float | None = None,
    ambiguity_score: float | None = None,
    volume_velocity: float | None = None,
    *,
    oi_change_1h: float | None = None,
) -> dict[str, object]:
    """Evaluate default alert gates and derive severity/reason codes."""

    oi_change = (
        open_interest_change_1h if open_interest_change_1h is not None else oi_change_1h
    )
    gate_hits = {
        BAND_BREACH: p_yes < q10 or p_yes > q90,
        LOW_OI_CONFIRMATION: oi_change is not None and oi_change <= _LOW_OI_THRESHOLD,
        LOW_AMBIGUITY: (
            ambiguity_score is not None and ambiguity_score <= _LOW_AMBIGUITY_THRESHOLD
        ),
        VOLUME_SPIKE: (
            volume_velocity is not None and volume_velocity >= _VOLUME_SPIKE_THRESHOLD
        ),
    }

    reason_codes = [code for code in _REASON_CODE_ORDER if gate_hits[code]]
    confirmation_hit = any(gate_hits[code] for code in _REASON_CODE_ORDER[1:])

    if gate_hits[BAND_BREACH] and confirmation_hit:
        severity = "HIGH"
    elif gate_hits[BAND_BREACH]:
        severity = "MED"
    else:
        severity = "FYI"

    return {"severity": severity, "reason_codes": reason_codes}
