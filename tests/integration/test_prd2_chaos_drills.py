from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from runners.tsfm_service import TSFMRunnerService, TSFMServiceConfig


class _FaultingAdapter:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    def forecast(self, **_: Any):
        self.calls += 1

        if self.mode == "timeout":
            raise httpx.ReadTimeout("simulated timeout")
        if self.mode == "5xx":
            request = httpx.Request("POST", "http://chaos.local/v1/timeseries/forecast")
            response = httpx.Response(503, request=request, json={"error": "simulated"})
            raise httpx.HTTPStatusError("simulated 503", request=request, response=response)
        if self.mode == "connection_drop":
            raise httpx.RemoteProtocolError("simulated connection drop")

        raise AssertionError(f"Unsupported mode for test: {self.mode}")


def _request(as_of_ts: str) -> dict[str, Any]:
    return {
        "market_id": "prd2-chaos-test",
        "as_of_ts": as_of_ts,
        "freq": "5m",
        "horizon_steps": 3,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.41, 0.43, 0.45, 0.46, 0.48, 0.49] * 12,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"provider": "tollama", "model_name": "chronos", "model_version": "chaos-test"},
        "liquidity_bucket": "high",
    }


@pytest.mark.parametrize("mode", ["timeout", "5xx", "connection_drop"])
def test_chaos_modes_force_deterministic_baseline_fallback(mode: str) -> None:
    adapter = _FaultingAdapter(mode)
    service = TSFMRunnerService(
        adapter=adapter,
        config=TSFMServiceConfig(
            cache_ttl_s=0,
            circuit_breaker_window_s=300,
            circuit_breaker_min_requests=100,
            circuit_breaker_failure_rate_to_open=1.0,
            circuit_breaker_cooldown_s=300,
        ),
    )

    first = service.forecast(_request(datetime(2026, 2, 21, tzinfo=timezone.utc).isoformat()))
    second = service.forecast(_request("2026-02-21T00:05:00Z"))

    assert first["meta"]["fallback_used"] is True
    assert second["meta"]["fallback_used"] is True
    assert first["meta"]["runtime"] == "baseline"
    assert second["meta"]["runtime"] == "baseline"
    assert first["meta"]["fallback_reason"].startswith("tollama_error:")
    assert second["meta"]["fallback_reason"].startswith("tollama_error:")
    assert first["yhat_q"] == second["yhat_q"]


@pytest.mark.parametrize("mode", ["timeout", "5xx", "connection_drop"])
def test_chaos_mode_response_safety_guards_hold(mode: str) -> None:
    service = TSFMRunnerService(
        adapter=_FaultingAdapter(mode),
        config=TSFMServiceConfig(
            cache_ttl_s=0,
            circuit_breaker_window_s=300,
            circuit_breaker_min_requests=100,
            circuit_breaker_failure_rate_to_open=1.0,
        ),
    )

    response = service.forecast(_request("2026-02-21T00:10:00Z"))

    q10 = response["yhat_q"]["0.1"]
    q50 = response["yhat_q"]["0.5"]
    q90 = response["yhat_q"]["0.9"]
    assert len(q10) == len(q50) == len(q90) == response["horizon_steps"]

    for a, b, c in zip(q10, q50, q90):
        assert math.isfinite(a) and math.isfinite(b) and math.isfinite(c)
        assert 0.0 <= a <= b <= c <= 1.0


def test_chaos_circuit_breaker_short_circuits_adapter_after_threshold() -> None:
    adapter = _FaultingAdapter("timeout")
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

    first = service.forecast(_request("2026-02-21T00:00:00Z"))
    second = service.forecast(_request("2026-02-21T00:01:00Z"))
    third = service.forecast(_request("2026-02-21T00:02:00Z"))

    assert first["meta"]["fallback_reason"].startswith("tollama_error:")
    assert second["meta"]["fallback_reason"].startswith("tollama_error:")
    assert third["meta"]["fallback_reason"] == "circuit_breaker_open"
    assert adapter.calls == 2
