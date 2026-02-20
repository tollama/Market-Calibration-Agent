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

    adjustment_payload = payload.get("adjustment", payload)
    if not isinstance(adjustment_payload, Mapping):
        raise ValueError(f"Invalid conformal adjustment object at {resolved}")

    return ConformalAdjustment(
        target_coverage=_to_float(adjustment_payload.get("target_coverage"), field="target_coverage"),
        quantile_level=_to_float(adjustment_payload.get("quantile_level"), field="quantile_level"),
        center_shift=_to_float(adjustment_payload.get("center_shift"), field="center_shift"),
        width_scale=_to_float(adjustment_payload.get("width_scale"), field="width_scale"),
        sample_size=_to_int(adjustment_payload.get("sample_size"), field="sample_size"),
    )


def save_conformal_adjustment(
    adjustment: ConformalAdjustment,
    *,
    path: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    resolved = _normalize_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "adjustment": asdict(adjustment),
        "metadata": dict(metadata or {}),
    }
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return resolved


__all__ = [
    "DEFAULT_CONFORMAL_STATE_PATH",
    "load_conformal_adjustment",
    "save_conformal_adjustment",
]
