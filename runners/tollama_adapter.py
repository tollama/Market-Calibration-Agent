from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import httpx

DEFAULT_MAX_CONNECTIONS = 200
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 50


class TollamaError(RuntimeError):
    """Raised when tollama call fails after retries."""


@dataclass(frozen=True)
class TollamaConfig:
    base_url: str = "http://localhost:11435"
    endpoint: str = "/v1/timeseries/forecast"
    timeout_s: float = 1.2
    retry_count: int = 1
    retry_backoff_base_s: float = 0.12
    retry_backoff_cap_s: float = 0.8
    retry_jitter_s: float = 0.08
    token: str | None = None
    max_connections: int = DEFAULT_MAX_CONNECTIONS
    max_keepalive_connections: int = DEFAULT_MAX_KEEPALIVE_CONNECTIONS


class TollamaAdapter:
    """Thin adapter around tollama runtime API with retry/jitter and pooled connections."""

    def __init__(self, config: TollamaConfig | None = None) -> None:
        self.config = config or TollamaConfig()
        self._client = httpx.Client(
            timeout=self.config.timeout_s,
            limits=httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_keepalive_connections,
            ),
        )

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _build_timestamps(length: int, freq: str) -> list[str]:
        if length <= 0:
            return []
        step = timedelta(minutes=5)
        text = str(freq).strip().lower()
        try:
            if text.endswith("m"):
                step = timedelta(minutes=max(1, int(text[:-1])))
            elif text.endswith("h"):
                step = timedelta(hours=max(1, int(text[:-1])))
        except Exception:  # noqa: BLE001
            step = timedelta(minutes=5)

        start = datetime.now(timezone.utc) - step * (length - 1)
        return [(start + step * i).replace(microsecond=0).isoformat().replace("+00:00", "Z") for i in range(length)]

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
        # Support both legacy tollama TSFM payloads and current Ollama-style forecast payloads.
        if self.config.endpoint in {"/v1/forecast", "/api/forecast"}:
            payload: dict[str, Any] = {
                "model": model_name,
                "horizon": int(horizon_steps),
                "quantiles": [float(q) for q in quantiles],
                "series": [
                    {
                        "id": "series-0",
                        "freq": freq,
                        "timestamps": self._build_timestamps(len(series), freq),
                        "target": [float(v) for v in series],
                        "past_covariates": dict(x_past or {}) or None,
                        "future_covariates": dict(x_future or {}) or None,
                    }
                ],
                "options": dict(params or {}),
                "parameters": {},
            }
        else:
            payload = {
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
                response = self._client.post(
                    f"{self.config.base_url.rstrip('/')}{self.config.endpoint}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                body = response.json()
                quantile_payload = body.get("quantiles", body.get("yhat_q", {}))
                if (not isinstance(quantile_payload, Mapping)) or (isinstance(quantile_payload, Mapping) and not quantile_payload):
                    forecasts = body.get("forecasts") if isinstance(body, Mapping) else None
                    if isinstance(forecasts, list) and forecasts:
                        first = forecasts[0] if isinstance(forecasts[0], Mapping) else {}
                        quantile_payload = first.get("quantiles", {}) if isinstance(first, Mapping) else {}
                if (not isinstance(quantile_payload, Mapping)) or not quantile_payload:
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
            except httpx.HTTPStatusError as exc:
                last_error = exc
                code = exc.response.status_code
                retryable = code in {429, 502, 503, 504}
                if idx < attempts - 1 and retryable:
                    backoff = min(
                        self.config.retry_backoff_base_s * (2**idx),
                        self.config.retry_backoff_cap_s,
                    )
                    jitter = random.random() * self.config.retry_jitter_s
                    time.sleep(backoff + jitter)
                    continue
                break
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if idx < attempts - 1:
                    backoff = min(
                        self.config.retry_backoff_base_s * (2**idx),
                        self.config.retry_backoff_cap_s,
                    )
                    jitter = random.random() * self.config.retry_jitter_s
                    time.sleep(backoff + jitter)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break

        raise TollamaError(f"tollama forecast failed: {type(last_error).__name__}: {last_error}")
