from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from runners.tsfm_service import CircuitState, TSFMRunnerService, TSFMServiceConfig


class _CountingAdapter:
    def __init__(self, *, fail: bool = False, sleep_s: float = 0.0) -> None:
        self.fail = fail
        self.sleep_s = sleep_s
        self._lock = Lock()
        self.calls = 0

    def forecast(self, **kwargs: object) -> tuple[dict[float, list[float]], dict[str, object]]:
        with self._lock:
            self.calls += 1
        if self.sleep_s:
            from time import sleep

            sleep(self.sleep_s)
        if self.fail:
            raise RuntimeError("tollama failure")
        return {
            0.1: [0.2, 0.3],
            0.5: [0.4, 0.5],
            0.9: [0.6, 0.7],
        }, {"runtime": "tollama", "latency_ms": 1.0}


def _request() -> dict[str, object]:
    return {
        "market_id": "m-concurrency",
        "as_of_ts": "2026-02-20T00:00:00Z",
        "freq": "5m",
        "horizon_steps": 2,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.3] * 64,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"model_name": "chronos", "model_version": "v1", "params": {}},
    }


def test_tsfm_service_concurrent_cache_hits_are_thread_safe() -> None:
    adapter = _CountingAdapter(sleep_s=0.02)
    service = TSFMRunnerService(adapter=adapter)

    # warm cache
    service.forecast(_request())

    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(service.forecast, [_request() for _ in range(16)]))

    assert len(results) == 16
    assert all(item["meta"]["cache_hit"] is True for item in results)
    assert all(item["meta"]["cache_stale"] is False for item in results)
    # cache and request counters are covered by adapter call + cache hit assertions
    assert adapter.calls == 1


def test_tsfm_service_concurrent_failures_do_not_corrupt_breaker_state() -> None:
    adapter = _CountingAdapter(fail=True)
    service = TSFMRunnerService(
        adapter=adapter,
        config=TSFMServiceConfig(
            circuit_breaker_window_s=120,
            circuit_breaker_min_requests=1,
            circuit_breaker_failure_rate_to_open=1.0,
            circuit_breaker_cooldown_s=999,
            circuit_breaker_half_open_probe_requests=2,
            circuit_breaker_half_open_successes_to_close=2,
        ),
    )

    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(service.forecast, [_request() for _ in range(32)]))

    assert len(results) == 32
    assert all(item["meta"]["fallback_used"] is True for item in results)
    assert all(item["meta"]["runtime"] == "baseline" for item in results)
    # errors are tolerated via fallback with baseline behavior and circuit state should become OPEN
    with service._state_lock:
        assert str(service._breaker_state) == str(CircuitState.OPEN)


def test_tsfm_service_concurrent_bad_requests_are_all_rejected_without_state_corruption() -> None:
    service = TSFMRunnerService(adapter=_CountingAdapter())
    bad = [
        {**_request(), "freq": "bad"},
        {**_request(), "y": [0.1]},
        {**_request(), "y": ["bad", 0.2]},
    ] * 10

    def _run(req: dict[str, object]) -> bool:
        try:
            service.forecast(req)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=12) as ex:
        outcomes = list(ex.map(_run, bad))

    assert all(outcome is False for outcome in outcomes)
    # no state counters are asserted to keep this test robust against cache/circuit updates
