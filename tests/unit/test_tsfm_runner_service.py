from __future__ import annotations

from datetime import datetime, timezone

from calibration.conformal import ConformalAdjustment
from calibration.conformal_state import save_conformal_adjustment
from runners.tollama_adapter import TollamaError
from runners.tsfm_service import TSFMRunnerService, TSFMServiceConfig


class _FakeAdapter:
    def __init__(self, quantiles: dict[float, list[float]] | None = None, *, fail: bool = False):
        self._quantiles = quantiles or {0.1: [0.2, 0.3], 0.5: [0.4, 0.5], 0.9: [0.6, 0.7]}
        self._fail = fail

    def forecast(self, **_: object):
        if self._fail:
            raise TollamaError("down")
        return self._quantiles, {"runtime": "tollama", "latency_ms": 1.0}


class _FlakyAdapter:
    def __init__(self) -> None:
        self.fail = False

    def forecast(self, **_: object):
        if self.fail:
            raise TollamaError("boom")
        return {0.1: [0.2, 0.3], 0.5: [0.4, 0.5], 0.9: [0.6, 0.7]}, {"runtime": "tollama", "latency_ms": 1.0}


def _request() -> dict[str, object]:
    return {
        "market_id": "m-1",
        "as_of_ts": datetime(2026, 2, 20, tzinfo=timezone.utc).isoformat(),
        "freq": "5m",
        "horizon_steps": 2,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.3] * 64,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"model_name": "chronos", "model_version": "v1", "params": {}},
    }


def test_tsfm_service_happy_path_returns_quantiles() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter())

    response = service.forecast(_request())

    assert response["market_id"] == "m-1"
    assert response["meta"]["runtime"] == "tollama"
    assert response["meta"]["fallback_used"] is False
    assert set(response["yhat_q"]) == {"0.1", "0.5", "0.9"}


def test_tsfm_service_falls_back_to_baseline_on_adapter_error() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter(fail=True))

    response = service.forecast(_request())

    assert response["meta"]["fallback_used"] is True
    assert response["meta"]["runtime"] == "baseline"
    assert response["meta"]["fallback_reason"].startswith("tollama_error:")
    assert "fallback_reason=" in " ".join(response["meta"]["warnings"])


def test_tsfm_service_fixes_quantile_crossing_and_clips() -> None:
    adapter = _FakeAdapter(quantiles={0.1: [1.2, 0.9], 0.5: [0.1, 0.5], 0.9: [-0.2, 0.1]})
    service = TSFMRunnerService(adapter=adapter)

    response = service.forecast(_request())

    for idx in range(2):
        q10 = response["yhat_q"]["0.1"][idx]
        q50 = response["yhat_q"]["0.5"][idx]
        q90 = response["yhat_q"]["0.9"][idx]
        assert 0 <= q10 <= q50 <= q90 <= 1


def test_tsfm_service_cache_hit_sets_meta_flag() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter())
    req = _request()

    first = service.forecast(req)
    second = service.forecast(req)

    assert first["meta"]["cache_hit"] is False
    assert second["meta"]["cache_hit"] is True
    assert second["meta"]["cache_stale"] is False


def test_tsfm_service_stale_if_error_uses_expired_cache() -> None:
    adapter = _FlakyAdapter()
    service = TSFMRunnerService(
        adapter=adapter,
        config=TSFMServiceConfig(cache_ttl_s=0, cache_stale_if_error_s=30),
    )
    req = _request()

    first = service.forecast(req)
    assert first["meta"]["fallback_used"] is False

    adapter.fail = True
    second = service.forecast(req)

    assert second["meta"]["fallback_used"] is True
    assert second["meta"]["fallback_reason"] == "stale_if_error"
    assert second["meta"]["cache_hit"] is True
    assert second["meta"]["cache_stale"] is True


def test_tsfm_service_circuit_breaker_opens_and_recovers_via_half_open_probes() -> None:
    adapter = _FlakyAdapter()
    config = TSFMServiceConfig(
        circuit_breaker_window_s=120,
        circuit_breaker_min_requests=3,
        circuit_breaker_failure_rate_to_open=1.0,
        circuit_breaker_cooldown_s=0,
        circuit_breaker_half_open_probe_requests=2,
        circuit_breaker_half_open_successes_to_close=2,
    )
    service = TSFMRunnerService(adapter=adapter, config=config)
    req = _request()

    adapter.fail = True
    service.forecast(req)
    service.forecast({**req, "as_of_ts": "2026-02-20T00:05:00Z"})
    opened = service.forecast({**req, "as_of_ts": "2026-02-20T00:10:00Z"})
    assert opened["meta"]["circuit_breaker_state"] == "open"

    adapter.fail = False
    probe_1 = service.forecast({**req, "as_of_ts": "2026-02-20T00:15:00Z"})
    assert probe_1["meta"]["runtime"] == "tollama"

    probe_2 = service.forecast({**req, "as_of_ts": "2026-02-20T00:20:00Z"})
    assert probe_2["meta"]["circuit_breaker_state"] == "closed"


def test_tsfm_service_fallbacks_on_invalid_adapter_shape() -> None:
    adapter = _FakeAdapter(quantiles={0.1: [0.2], 0.5: [0.3], 0.9: [0.4]})
    service = TSFMRunnerService(adapter=adapter)

    response = service.forecast(_request())

    assert response["meta"]["fallback_used"] is True
    assert any("horizon_mismatch" in w for w in response["meta"]["warnings"])


def test_tsfm_service_reverts_to_default_quantiles_when_unsupported_requested() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter())
    req = {**_request(), "quantiles": [0.2, 0.5, 0.8]}

    response = service.forecast(req)

    assert response["quantiles"] == [0.1, 0.5, 0.9]
    assert "unsupported_quantiles_requested;using_default" in response["meta"]["warnings"]


def test_tsfm_service_fast_gate_max_gap_before_tollama() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter())
    req = {
        **_request(),
        "y_ts": [
            "2026-02-20T00:00:00Z",
            "2026-02-20T00:05:00Z",
            "2026-02-20T03:00:00Z",
        ],
    }

    response = service.forecast(req)

    assert response["meta"]["runtime"] == "baseline"
    assert response["meta"]["fallback_reason"] == "max_gap_exceeded"


def test_tsfm_service_degradation_state_machine_is_deterministic() -> None:
    adapter = _FlakyAdapter()
    config = TSFMServiceConfig(
        degradation_window_s=600,
        degradation_min_requests=4,
        degraded_enter_failure_rate=0.25,
        baseline_only_enter_failure_rate=0.5,
        degraded_exit_failure_rate=0.10,
        baseline_only_exit_failure_rate=0.20,
        circuit_breaker_min_requests=100,
    )
    service = TSFMRunnerService(adapter=adapter, config=config)
    req = _request()

    adapter.fail = True
    service.forecast(req)
    service.forecast({**req, "as_of_ts": "2026-02-20T00:05:00Z"})
    state3 = service.forecast({**req, "as_of_ts": "2026-02-20T00:10:00Z"})
    assert state3["meta"]["degradation_state"] == "normal"

    state4 = service.forecast({**req, "as_of_ts": "2026-02-20T00:15:00Z"})
    assert state4["meta"]["degradation_state"] == "baseline-only"

    adapter.fail = False
    recovered = service.forecast({**req, "as_of_ts": "2026-02-20T00:20:00Z"})
    assert recovered["meta"]["degradation_state"] in {"baseline-only", "degraded"}

    for i in range(10):
        res = service.forecast({**req, "as_of_ts": f"2026-02-20T00:{25 + i:02d}:00Z"})
    assert res["meta"]["degradation_state"] in {"baseline-only", "degraded", "normal"}


def test_tsfm_service_loads_conformal_state_when_present(tmp_path) -> None:
    state_path = tmp_path / "conformal_state.json"
    save_conformal_adjustment(
        adjustment=ConformalAdjustment(
            target_coverage=0.8,
            quantile_level=0.9,
            center_shift=0.05,
            width_scale=1.3,
            sample_size=200,
        ),
        path=state_path,
        metadata={"source": "test"},
    )

    config = TSFMServiceConfig(conformal_state_path=str(state_path))
    service = TSFMRunnerService(adapter=_FakeAdapter(), config=config)
    response = service.forecast(_request())

    assert response["meta"]["conformal_state_loaded"] is True
    assert "conformal_last_step" in response


def test_tsfm_service_conformal_state_missing_keeps_default_behavior(tmp_path) -> None:
    missing_path = tmp_path / "not_there.json"
    config = TSFMServiceConfig(conformal_state_path=str(missing_path))

    service = TSFMRunnerService(adapter=_FakeAdapter(), config=config)
    response = service.forecast(_request())

    assert response["meta"]["conformal_state_loaded"] is False
    assert "conformal_last_step" not in response


def test_tsfm_service_runtime_config_builds_adapter_from_adapter_block(tmp_path) -> None:
    runtime_path = tmp_path / "tsfm_runtime.yaml"
    runtime_path.write_text(
        """
 tsfm:
   adapter:
     timeout_s: 2.0
     retry_count: 1
     retry_backoff_ms: 250
     retry_jitter_ms: 40
     max_connections: 111
     max_keepalive_connections: 22
   cache:
     ttl_s: 15
     stale_if_error_s: 45
     max_entries: 77
 """.strip(),
        encoding="utf-8",
    )

    service = TSFMRunnerService.from_runtime_config(path=runtime_path)

    assert service.adapter.config.timeout_s == 2.0
    assert service.adapter.config.retry_count == 1
    assert service.adapter.config.retry_backoff_base_s == 0.25
    assert service.adapter.config.retry_jitter_s == 0.04
    assert service.adapter.config.max_connections == 111
    assert service.adapter.config.max_keepalive_connections == 22
    assert service.config.cache_ttl_s == 15
    assert service.config.cache_stale_if_error_s == 45
    assert service.config.cache_max_entries == 77


def test_tsfm_service_cache_max_entries_is_enforced() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter(), config=TSFMServiceConfig(cache_max_entries=2))

    for i in range(5):
        service.forecast({**_request(), "as_of_ts": f"2026-02-20T00:{i:02d}:00Z"})

    assert len(service._cache) <= 2


def test_tsfm_service_emits_prometheus_metrics_after_forecast() -> None:
    service = TSFMRunnerService(adapter=_FakeAdapter())

    service.forecast(_request())
    payload = service.render_prometheus_metrics()

    assert "tsfm_request_total" in payload
    assert "tsfm_request_latency_ms_bucket" in payload
