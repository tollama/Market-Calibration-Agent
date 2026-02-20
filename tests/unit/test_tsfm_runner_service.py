from __future__ import annotations

from datetime import datetime, timezone

from runners.tollama_adapter import TollamaError
from runners.tsfm_service import TSFMRunnerService


class _FakeAdapter:
    def __init__(self, quantiles: dict[float, list[float]] | None = None, *, fail: bool = False):
        self._quantiles = quantiles or {0.1: [0.2, 0.3], 0.5: [0.4, 0.5], 0.9: [0.6, 0.7]}
        self._fail = fail

    def forecast(self, **_: object):
        if self._fail:
            raise TollamaError("down")
        return self._quantiles, {"runtime": "tollama", "latency_ms": 1.0}


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
