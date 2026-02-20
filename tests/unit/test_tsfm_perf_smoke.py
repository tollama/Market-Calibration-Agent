from __future__ import annotations

import time

from runners.tsfm_service import TSFMRunnerService


class _FastBenchAdapter:
    def forecast(self, **_: object):
        return (
            {0.1: [0.2] * 12, 0.5: [0.5] * 12, 0.9: [0.8] * 12},
            {"runtime": "tollama", "latency_ms": 0.1},
        )


def _request(as_of_idx: int) -> dict[str, object]:
    return {
        "market_id": "bench-market",
        "as_of_ts": f"2026-02-20T00:{as_of_idx % 10:02d}:00Z",
        "freq": "5m",
        "horizon_steps": 12,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.45] * 288,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"model_name": "chronos", "model_version": "bench", "params": {}},
    }


def test_tsfm_perf_smoke_cache_and_p95_budget() -> None:
    service = TSFMRunnerService(adapter=_FastBenchAdapter())

    latencies_ms: list[float] = []
    cache_hits = 0
    for idx in range(200):
        req = _request(idx)
        t0 = time.perf_counter()
        res = service.forecast(req)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        if res["meta"].get("cache_hit"):
            cache_hits += 1

    p95 = sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]
    assert cache_hits >= 180
    assert p95 < 25.0
