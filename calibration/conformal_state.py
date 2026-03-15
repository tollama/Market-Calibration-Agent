from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from calibration.conformal import ConformalAdjustment

DEFAULT_CONFORMAL_STATE_PATH = Path("data/derived/calibration/conformal_state.json")


def _to_float(value: Any, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid conformal state field {field}: {value!r}") from exc


def _to_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid conformal state field {field}: {value!r}") from exc


def _normalize_path(path: str | Path | None) -> Path:
    if path is None:
        return DEFAULT_CONFORMAL_STATE_PATH
    return Path(path)


def load_conformal_adjustment(path: str | Path | None = None) -> ConformalAdjustment | None:
    resolved = _normalize_path(path)
    if not resolved.exists():
        return None

    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid conformal state payload at {resolved}")

    adjustment_payload = payload.get("default_adjustment", payload.get("adjustment", payload))
    if not isinstance(adjustment_payload, Mapping):
        raise ValueError(f"Invalid conformal adjustment object at {resolved}")

    return _decode_adjustment(adjustment_payload)


def load_conformal_adjustments_by_segment(path: str | Path | None = None) -> dict[str, ConformalAdjustment]:
    resolved = _normalize_path(path)
    if not resolved.exists():
        return {}

    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid conformal state payload at {resolved}")

    segments_payload = payload.get("segments")
    if not isinstance(segments_payload, Mapping):
        return {}

    decoded: dict[str, ConformalAdjustment] = {}
    for key, value in segments_payload.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            continue
        decoded[key] = _decode_adjustment(value)
    return decoded


def save_conformal_adjustment(
    adjustment: ConformalAdjustment,
    *,
    path: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
    segment_adjustments: Mapping[str, ConformalAdjustment] | None = None,
    segment_fields: list[str] | None = None,
) -> Path:
    resolved = _normalize_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 2 if segment_adjustments else 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "adjustment": asdict(adjustment),
        "default_adjustment": asdict(adjustment),
        "metadata": dict(metadata or {}),
    }
    if segment_adjustments:
        payload["segment_fields"] = list(segment_fields or [])
        payload["segments"] = {str(key): asdict(value) for key, value in segment_adjustments.items()}
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return resolved


def _decode_adjustment(payload: Mapping[str, Any]) -> ConformalAdjustment:
    return ConformalAdjustment(
        target_coverage=_to_float(payload.get("target_coverage"), field="target_coverage"),
        quantile_level=_to_float(payload.get("quantile_level"), field="quantile_level"),
        center_shift=_to_float(payload.get("center_shift"), field="center_shift"),
        width_scale=_to_float(payload.get("width_scale"), field="width_scale"),
        sample_size=_to_int(payload.get("sample_size"), field="sample_size"),
    )


DEFAULT_CPTC_STATE_PATH = Path("data/derived/calibration/cptc_state.json")


def load_cptc_state(path: str | Path | None = None) -> dict[str, Any] | None:
    """Load persisted CPTC change-point state from disk."""
    resolved = Path(path) if path is not None else DEFAULT_CPTC_STATE_PATH
    if not resolved.exists():
        return None

    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid CPTC state payload at {resolved}")

    return dict(payload)


def save_cptc_state(
    *,
    change_point_detected: bool,
    change_point_index: int | None,
    test_statistic: float,
    threshold: float,
    n_pre: int,
    n_post: int,
    conformal_method: str = "cptc",
    path: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Persist CPTC change-point detection state to disk."""
    resolved = Path(path) if path is not None else DEFAULT_CPTC_STATE_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "conformal_method": conformal_method,
        "change_point": {
            "detected": change_point_detected,
            "index": change_point_index,
            "test_statistic": test_statistic,
            "threshold": threshold,
            "n_pre": n_pre,
            "n_post": n_post,
        },
        "metadata": dict(metadata or {}),
    }
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return resolved


__all__ = [
    "DEFAULT_CONFORMAL_STATE_PATH",
    "DEFAULT_CPTC_STATE_PATH",
    "load_conformal_adjustment",
    "load_conformal_adjustments_by_segment",
    "load_cptc_state",
    "save_conformal_adjustment",
    "save_cptc_state",
]
