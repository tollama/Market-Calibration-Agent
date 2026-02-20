from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "prd2"


def fixture_path(name: str) -> Path:
    return _FIXTURE_DIR / f"{name}.json"


def load_prd2_fixture(name: str) -> dict[str, Any]:
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def fixture_request(name: str) -> dict[str, Any]:
    payload = load_prd2_fixture(name)
    return dict(payload["request"])


def fixture_adapter_quantiles(name: str) -> dict[float, list[float]]:
    payload = load_prd2_fixture(name)
    raw = payload.get("adapter", {}).get("quantiles", {})
    return {float(k): [float(v) for v in values] for k, values in raw.items()}


def fixture_expectation(name: str) -> dict[str, Any]:
    payload = load_prd2_fixture(name)
    return dict(payload.get("expect", {}))
