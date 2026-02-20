from __future__ import annotations

from runners.tsfm_service import TSFMRunnerService


class _AdapterOK:
    def forecast(self, **kwargs):
        h = int(kwargs["horizon_steps"])
        return (
            {
                0.1: [0.2] * h,
                0.5: [0.4] * h,
                0.9: [0.6] * h,
            },
            {"runtime": "tollama"},
        )


class _AdapterCrossing:
    def forecast(self, **kwargs):
        h = int(kwargs["horizon_steps"])
        return (
            {
                0.1: [0.7] * h,
                0.5: [0.4] * h,
                0.9: [0.3] * h,
            },
            {"runtime": "tollama"},
        )


def _request() -> dict[str, object]:
    return {
        "market_id": "m-obs-1",
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


def test_service_emits_core_runtime_metrics() -> None:
    service = TSFMRunnerService(adapter=_AdapterOK())
    service.forecast(_request())

    text = service.render_prometheus_metrics()
    assert 'tsfm_request_total{rollout_stage="canary_5",status="success"} 1.0' in text
    assert 'tsfm_request_latency_ms_bucket' in text
    assert 'tsfm_cycle_time_seconds_bucket' in text
    assert 'tsfm_target_coverage{bucket="high",rollout_stage="canary_5"}' in text
    assert 'tsfm_interval_width{bucket="high",rollout_stage="canary_5"}' in text


def test_service_emits_crossing_and_cache_metrics() -> None:
    service = TSFMRunnerService(adapter=_AdapterCrossing())
    req = _request()
    service.forecast(req)
    service.forecast(req)  # cache hit

    text = service.render_prometheus_metrics()
    assert 'tsfm_quantile_crossing_total{rollout_stage="canary_5"} 1.0' in text
    assert 'tsfm_cache_hit_total{rollout_stage="canary_5"} 1.0' in text
