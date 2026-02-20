from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from runners.tollama_adapter import TollamaAdapter, TollamaConfig
from runners.tsfm_service import TSFMRunnerService


def _is_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_live_tollama() -> tuple[str, str | None]:
    if not _is_enabled(os.getenv("LIVE_TOLLAMA_TESTS")):
        pytest.skip("Live tollama integration disabled (set LIVE_TOLLAMA_TESTS=1).")

    base_url = os.getenv("TOLLAMA_BASE_URL", "http://localhost:11435")
    token = os.getenv("TOLLAMA_TOKEN") or None

    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError as exc:
        pytest.skip(f"Live tollama runtime unavailable at {host}:{port}: {exc}")

    return base_url, token


def _build_adapter() -> TollamaAdapter:
    base_url, token = _require_live_tollama()
    return TollamaAdapter(
        TollamaConfig(
            base_url=base_url,
            endpoint=os.getenv("TOLLAMA_ENDPOINT", "/v1/timeseries/forecast"),
            token=token,
            timeout_s=float(os.getenv("TOLLAMA_TIMEOUT_S", "8")),
            retry_count=int(os.getenv("TOLLAMA_RETRY_COUNT", "0")),
        )
    )


def test_live_tollama_adapter_forecast_shape() -> None:
    adapter = _build_adapter()
    try:
        quantiles, meta = adapter.forecast(
            series=[0.45, 0.47, 0.46, 0.49, 0.5, 0.52] * 12,
            horizon_steps=4,
            freq="5m",
            quantiles=[0.1, 0.5, 0.9],
            model_name=os.getenv("TOLLAMA_MODEL_NAME", "chronos"),
            model_version=os.getenv("TOLLAMA_MODEL_VERSION"),
            params={"temperature": 0.0},
        )
    finally:
        adapter.close()

    assert set(quantiles) == {0.1, 0.5, 0.9}
    assert all(len(path) == 4 for path in quantiles.values())
    assert meta["runtime"] == "tollama"
    assert "latency_ms" in meta


def test_live_tollama_service_path_without_fallback() -> None:
    adapter = _build_adapter()
    service = TSFMRunnerService(adapter=adapter)
    try:
        response = service.forecast(
            {
                "market_id": "live-smoke",
                "as_of_ts": "2026-02-21T00:00:00Z",
                "freq": "5m",
                "horizon_steps": 3,
                "quantiles": [0.1, 0.5, 0.9],
                "y": [0.42, 0.43, 0.44, 0.46, 0.48, 0.5] * 12,
                "transform": {"space": "logit", "eps": 1e-6},
                "model": {
                    "provider": "tollama",
                    "model_name": os.getenv("TOLLAMA_MODEL_NAME", "chronos"),
                    "model_version": os.getenv("TOLLAMA_MODEL_VERSION", "live"),
                    "params": {"temperature": 0.0},
                },
                "liquidity_bucket": "high",
            }
        )
    finally:
        adapter.close()

    assert response["meta"]["fallback_used"] is False
    assert response["meta"]["runtime"] == "tollama"
    assert set(response["yhat_q"]) == {"0.1", "0.5", "0.9"}
