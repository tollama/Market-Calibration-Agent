#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from runners.tsfm_service import TSFMRunnerService, TSFMServiceConfig


class FaultInjectingAdapter:
    """Mock adapter for local/staging chaos drills."""

    def __init__(self, mode: str) -> None:
        self.mode = mode.strip().lower()
        self.calls = 0

    def forecast(self, **_: Any):
        self.calls += 1

        if self.mode == "timeout":
            raise httpx.ReadTimeout("chaos: simulated tollama timeout")

        if self.mode == "5xx":
            request = httpx.Request("POST", "http://chaos.local/v1/timeseries/forecast")
            response = httpx.Response(503, request=request, json={"error": "chaos-503"})
            raise httpx.HTTPStatusError("chaos: simulated 503", request=request, response=response)

        if self.mode in {"connection_drop", "connection-drop", "drop"}:
            raise httpx.RemoteProtocolError("chaos: simulated connection drop")

        return {
            0.1: [0.25, 0.25, 0.25],
            0.5: [0.5, 0.5, 0.5],
            0.9: [0.75, 0.75, 0.75],
        }, {"runtime": "tollama", "latency_ms": 0.1}


def _request() -> dict[str, Any]:
    return {
        "market_id": "prd2-chaos-drill",
        "as_of_ts": datetime(2026, 2, 21, tzinfo=timezone.utc).isoformat(),
        "freq": "5m",
        "horizon_steps": 3,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.42, 0.44, 0.45, 0.47, 0.49, 0.5] * 12,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"provider": "tollama", "model_name": "chronos", "model_version": "chaos"},
        "liquidity_bucket": "high",
    }


def _validate_response_safety(response: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    yhat_q = response["yhat_q"]
    q10 = yhat_q["0.1"]
    q50 = yhat_q["0.5"]
    q90 = yhat_q["0.9"]

    for idx in range(len(q50)):
        a, b, c = q10[idx], q50[idx], q90[idx]
        if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)):
            errors.append(f"non_finite@{idx}")
            continue
        if not (0.0 <= a <= b <= c <= 1.0):
            errors.append(f"quantile_order_or_bounds@{idx}")

    return errors


def main() -> int:
    mode = os.getenv("CHAOS_MODE", "timeout").strip().lower()
    repeats = int(os.getenv("CHAOS_REPEATS", "2"))

    adapter = FaultInjectingAdapter(mode)
    service = TSFMRunnerService(
        adapter=adapter,
        config=TSFMServiceConfig(
            cache_ttl_s=0,
            circuit_breaker_window_s=300,
            circuit_breaker_min_requests=2,
            circuit_breaker_failure_rate_to_open=1.0,
            circuit_breaker_cooldown_s=300,
        ),
    )

    responses: list[dict[str, Any]] = []
    req = _request()

    for i in range(repeats):
        run_req = {**req, "as_of_ts": f"2026-02-21T00:{i:02d}:00Z"}
        responses.append(service.forecast(run_req))

    safety_errors: list[str] = []
    for response in responses:
        safety_errors.extend(_validate_response_safety(response))

    fallback_expected = mode in {"timeout", "5xx", "connection_drop", "connection-drop", "drop"}
    fallback_all = all(r["meta"]["fallback_used"] for r in responses)
    baseline_all = all(r["meta"]["runtime"] == "baseline" for r in responses)
    deterministic = len({json.dumps(r["yhat_q"], sort_keys=True) for r in responses}) == 1

    report = {
        "mode": mode,
        "repeats": repeats,
        "adapter_calls": adapter.calls,
        "fallback_expected": fallback_expected,
        "fallback_all": fallback_all,
        "baseline_all": baseline_all,
        "deterministic": deterministic,
        "safety_errors": safety_errors,
        "fallback_reasons": [r["meta"].get("fallback_reason") for r in responses],
    }

    ok = True
    if fallback_expected and not (fallback_all and baseline_all):
        ok = False
    if fallback_expected and not deterministic:
        ok = False
    if safety_errors:
        ok = False

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
