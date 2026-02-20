"""Build alert feed rows from model/market inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from agents.alert_agent import AlertThresholdConfig, evaluate_alert

_REQUIRED_ROW_KEYS: tuple[str, ...] = ("market_id", "ts", "p_yes", "q10", "q90")
_SEVERITY_PRIORITY: dict[str, int] = {"HIGH": 0, "MED": 1, "FYI": 2}


def build_alert_feed_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    thresholds: AlertThresholdConfig | None = None,
    include_fyi: bool = False,
    min_trust_score: float | None = None,
) -> list[dict[str, object]]:
    """Build alert feed rows, excluding FYI alerts unless include_fyi=True."""
    alert_rows: list[dict[str, object]] = []
    normalized_min_trust_score = (
        float(min_trust_score) if min_trust_score is not None else None
    )

    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{idx}] must be a mapping")
        _validate_required_keys(row=row, idx=idx)

        market_id = str(row["market_id"])
        ts = row["ts"]
        p_yes = float(row["p_yes"])
        q10 = float(row["q10"])
        q90 = float(row["q90"])
        open_interest_change_1h = _optional_float(row.get("open_interest_change_1h"))
        ambiguity_score = _optional_float(row.get("ambiguity_score"))
        volume_velocity = _optional_float(row.get("volume_velocity"))
        trust_score = _optional_float(row.get("trust_score"))

        if (
            normalized_min_trust_score is not None
            and trust_score is not None
            and trust_score < normalized_min_trust_score
        ):
            continue

        evaluation = evaluate_alert(
            p_yes=p_yes,
            q10=q10,
            q90=q90,
            open_interest_change_1h=open_interest_change_1h,
            ambiguity_score=ambiguity_score,
            volume_velocity=volume_velocity,
            thresholds=thresholds,
        )

        severity = str(evaluation["severity"])
        if severity not in _SEVERITY_PRIORITY:
            continue
        if severity == "FYI" and not include_fyi:
            continue

        reason_codes = [str(code) for code in evaluation.get("reason_codes", [])]
        evidence: dict[str, Any] = {"p_yes": p_yes, "q10": q10, "q90": q90}
        if open_interest_change_1h is not None:
            evidence["oi_change_1h"] = open_interest_change_1h
        if ambiguity_score is not None:
            evidence["ambiguity_score"] = ambiguity_score
        if volume_velocity is not None:
            evidence["volume_velocity"] = volume_velocity

        alert_rows.append(
            {
                "alert_id": _build_alert_id(
                    market_id=market_id,
                    ts=ts,
                    severity=severity,
                    reason_codes=reason_codes,
                    evidence=evidence,
                ),
                "market_id": market_id,
                "ts": ts,
                "severity": severity,
                "reason_codes": reason_codes,
                "evidence": evidence,
            }
        )

    alert_rows.sort(key=_alert_sort_key)
    return alert_rows


def _validate_required_keys(*, row: Mapping[str, object], idx: int) -> None:
    for key in _REQUIRED_ROW_KEYS:
        if key not in row:
            raise ValueError(f"rows[{idx}] missing required key: {key}")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _alert_sort_key(row: Mapping[str, object]) -> tuple[int, float, str]:
    severity = str(row.get("severity", ""))
    ts = row.get("ts")
    market_id = str(row.get("market_id", ""))
    return (_SEVERITY_PRIORITY.get(severity, 99), -_to_epoch_seconds(ts), market_id)


def _build_alert_id(
    *,
    market_id: str,
    ts: object,
    severity: str,
    reason_codes: Sequence[str],
    evidence: Mapping[str, object],
) -> str:
    payload = {
        "market_id": market_id,
        "ts": _canonical_ts(ts),
        "severity": severity,
        "reason_codes": list(reason_codes),
        "evidence": dict(evidence),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_ts(value: object) -> str:
    parsed = _parse_ts(value)
    if parsed is None:
        return str(value)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_epoch_seconds(value: object) -> float:
    parsed = _parse_ts(value)
    if parsed is None:
        return float("-inf")
    return parsed.astimezone(timezone.utc).timestamp()


def _parse_ts(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
