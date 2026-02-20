#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runners.tsfm_service import TSFMRunnerService


class _Adapter:
    def forecast(self, **kwargs):
        h = int(kwargs["horizon_steps"])
        return ({0.1: [0.2] * h, 0.5: [0.4] * h, 0.9: [0.6] * h}, {"runtime": "tollama"})


def main() -> int:
    service = TSFMRunnerService(adapter=_Adapter())
    payload = {
        "market_id": "m-smoke-metrics",
        "as_of_ts": "2026-02-21T00:00:00Z",
        "freq": "5m",
        "horizon_steps": 3,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.45] * 64,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"provider": "tollama", "model_name": "chronos", "params": {}},
        "rollout_stage": "canary_5",
        "liquidity_bucket": "high",
    }

    service.forecast(payload)
    service.forecast(payload)  # cache-hit path
    body = service.render_prometheus_metrics()

    required_tokens = [
        "tsfm_request_total",
        "tsfm_request_latency_ms_bucket",
        "tsfm_cycle_time_seconds_bucket",
        "tsfm_cache_hit_total",
        "tsfm_target_coverage",
        "tsfm_interval_width",
    ]

    missing = [t for t in required_tokens if t not in body]
    if missing:
        print("METRICS_SMOKE_FAIL")
        print("missing=" + ",".join(missing))
        return 1

    print("METRICS_SMOKE_PASS")
    for token in required_tokens:
        print(f"found={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
