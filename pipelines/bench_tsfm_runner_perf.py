from __future__ import annotations

import argparse
import statistics
import time

from runners.tsfm_service import TSFMRunnerService


class _BenchAdapter:
    def __init__(self, latency_ms: float = 15.0) -> None:
        self.latency_ms = latency_ms

    def forecast(self, **_: object):
        time.sleep(self.latency_ms / 1000.0)
        return {0.1: [0.2] * 12, 0.5: [0.5] * 12, 0.9: [0.8] * 12}, {"runtime": "tollama", "latency_ms": self.latency_ms}


def _make_request(idx: int, unique: int) -> dict[str, object]:
    as_of_min = idx % max(1, unique)
    return {
        "market_id": f"m-{idx % 20}",
        "as_of_ts": f"2026-02-20T00:{as_of_min:02d}:00Z",
        "freq": "5m",
        "horizon_steps": 12,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.45] * 288,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"model_name": "chronos", "model_version": "bench", "params": {}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TSFM runner perf smoke benchmark")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--unique", type=int, default=20, help="unique request keys; lower means more cache hits")
    parser.add_argument("--adapter-latency-ms", type=float, default=15.0)
    parser.add_argument("--budget-p95-ms", type=float, default=300.0)
    parser.add_argument("--budget-cycle-s", type=float, default=60.0)
    args = parser.parse_args()

    service = TSFMRunnerService(adapter=_BenchAdapter(latency_ms=args.adapter_latency_ms))

    latencies_ms: list[float] = []
    started = time.perf_counter()
    fallback_count = 0
    cache_hits = 0

    for idx in range(args.requests):
        req = _make_request(idx, args.unique)
        t0 = time.perf_counter()
        res = service.forecast(req)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        if res["meta"].get("fallback_used"):
            fallback_count += 1
        if res["meta"].get("cache_hit"):
            cache_hits += 1

    elapsed_s = time.perf_counter() - started
    p95 = sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]
    p50 = statistics.median(latencies_ms)

    print(f"requests={args.requests}")
    print(f"unique={args.unique}")
    print(f"elapsed_s={elapsed_s:.3f}")
    print(f"throughput_rps={args.requests / max(elapsed_s, 1e-9):.2f}")
    print(f"latency_p50_ms={p50:.2f}")
    print(f"latency_p95_ms={p95:.2f}")
    print(f"cache_hit_rate={cache_hits / max(args.requests, 1):.3f}")
    print(f"fallback_rate={fallback_count / max(args.requests, 1):.3f}")

    ok = True
    if p95 > args.budget_p95_ms:
        print(f"SLO_FAIL: p95 {p95:.2f}ms > budget {args.budget_p95_ms:.2f}ms")
        ok = False
    if elapsed_s > args.budget_cycle_s:
        print(f"SLO_FAIL: cycle {elapsed_s:.2f}s > budget {args.budget_cycle_s:.2f}s")
        ok = False

    if ok:
        print("SLO_PASS")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
