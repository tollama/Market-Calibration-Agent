from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx


class TollamaError(RuntimeError):
    """Raised when tollama call fails after retries."""


@dataclass(frozen=True)
class TollamaConfig:
    base_url: str = "http://localhost:11435"
    endpoint: str = "/v1/timeseries/forecast"
    timeout_s: float = 2.0
    retry_count: int = 1
    retry_jitter_s: float = 0.2
    token: str | None = None


class TollamaAdapter:
    """Thin adapter around tollama runtime API with retry/jitter."""

    def __init__(self, config: TollamaConfig | None = None) -> None:
        self.config = config or TollamaConfig()

    def forecast(
        self,
        *,
        series: Sequence[float],
        horizon_steps: int,
        freq: str,
        quantiles: Sequence[float],
        model_name: str,
        model_version: str | None = None,
        x_past: Mapping[str, Sequence[float]] | None = None,
        x_future: Mapping[str, Sequence[float]] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[dict[float, list[float]], dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model_name,
            "model_version": model_version,
            "series": list(series),
            "horizon_steps": int(horizon_steps),
            "freq": freq,
            "quantiles": [float(q) for q in quantiles],
            "x_past": dict(x_past or {}),
            "x_future": dict(x_future or {}),
            "params": dict(params or {}),
        }

        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        attempts = max(0, int(self.config.retry_count)) + 1
        last_error: Exception | None = None
        for idx in range(attempts):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=self.config.timeout_s) as client:
                    response = client.post(
                        f"{self.config.base_url.rstrip('/')}{self.config.endpoint}",
                        json=payload,
                        headers=headers,
                    )
                response.raise_for_status()
                body = response.json()
                quantile_payload = body.get("quantiles", body.get("yhat_q", {}))
                if not isinstance(quantile_payload, Mapping):
                    raise TollamaError("Invalid tollama response: quantiles payload missing")

                parsed: dict[float, list[float]] = {}
                for key, values in quantile_payload.items():
                    q = float(key)
                    parsed[q] = [float(v) for v in values]

                latency_ms = (time.perf_counter() - started) * 1000
                meta = {
                    "runtime": "tollama",
                    "latency_ms": latency_ms,
                    "raw_response_meta": body.get("meta", {}),
                }
                return parsed, meta
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if idx < attempts - 1:
                    jitter = random.random() * self.config.retry_jitter_s
                    time.sleep(jitter)
                    continue
                break

        raise TollamaError(f"tollama forecast failed: {last_error}")
