from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from calibration.conformal import ConformalAdjustment, apply_conformal_adjustment
from runners.baselines import forecast_baseline_band
from runners.tollama_adapter import TollamaAdapter, TollamaConfig


def _parse_freq_to_seconds(freq: str) -> int:
    text = freq.strip().lower()
    if text.endswith("m"):
        return int(text[:-1]) * 60
    if text.endswith("h"):
        return int(text[:-1]) * 3600
    raise ValueError(f"Unsupported freq: {freq}")


def _logit(p: float, eps: float) -> float:
    p = max(eps, min(1 - eps, p))
    return math.log(p / (1 - p))


def _inv_logit(v: float) -> float:
    return 1 / (1 + math.exp(-v))


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _fix_quantile_crossing(quantiles: dict[float, list[float]]) -> tuple[dict[float, list[float]], bool]:
    if not quantiles:
        return quantiles, False
    keys = sorted(quantiles)
    horizon = len(next(iter(quantiles.values())))
    crossed = False
    fixed: dict[float, list[float]] = {k: [0.0] * horizon for k in keys}
    for step in range(horizon):
        vals = [quantiles[k][step] for k in keys]
        ordered = sorted(vals)
        if ordered != vals:
            crossed = True
        for k, v in zip(keys, ordered):
            fixed[k][step] = v
    return fixed, crossed


def _validate_quantile_payload(
    quantile_paths: Mapping[float, list[float]],
    *,
    expected_quantiles: list[float],
    expected_horizon_steps: int,
) -> None:
    expected = set(expected_quantiles)
    got = set(quantile_paths.keys())
    if expected != got:
        raise ValueError(
            f"quantile_set_mismatch: expected={sorted(expected)} got={sorted(got)}"
        )

    for q in expected_quantiles:
        path = quantile_paths[q]
        if len(path) != expected_horizon_steps:
            raise ValueError(
                f"horizon_mismatch:q={q} expected={expected_horizon_steps} got={len(path)}"
            )
        if any(not math.isfinite(v) for v in path):
            raise ValueError(f"non_finite_value:q={q}")


@dataclass(frozen=True)
class TSFMServiceConfig:
    default_freq: str = "5m"
    input_len_steps: int = 288
    default_horizon_steps: int = 12
    default_quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)
    transform_space: str = "logit"
    transform_eps: float = 1e-6
    max_gap_minutes: int = 60
    min_points_for_tsfm: int = 32
    min_interval_width: float = 0.02
    max_interval_width: float = 0.6
    baseline_method: str = "EWMA"
    baseline_only_liquidity: str = "low"
    # performance defaults
    cache_ttl_s: int = 60
    circuit_breaker_failures: int = 5
    circuit_breaker_cooldown_s: int = 120


class TSFMRunnerService:
    def __init__(
        self,
        *,
        adapter: TollamaAdapter | None = None,
        config: TSFMServiceConfig | None = None,
        conformal_adjustment: ConformalAdjustment | None = None,
    ) -> None:
        self.adapter = adapter or TollamaAdapter(TollamaConfig())
        self.config = config or TSFMServiceConfig()
        self.conformal_adjustment = conformal_adjustment
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._consecutive_failures = 0
        self._breaker_open_until = 0.0

    def _cache_key(self, request: Mapping[str, Any]) -> str:
        stable = {
            "market_id": request.get("market_id"),
            "as_of_ts": request.get("as_of_ts"),
            "freq": request.get("freq"),
            "horizon_steps": request.get("horizon_steps"),
            "quantiles": request.get("quantiles"),
            "y": request.get("y"),
            "x_past": request.get("x_past"),
            "x_future": request.get("x_future"),
            "transform": request.get("transform"),
            "model": request.get("model"),
            "liquidity_bucket": request.get("liquidity_bucket"),
        }
        encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        row = self._cache.get(key)
        if row is None:
            return None
        expires_at, value = row
        if time.time() > expires_at:
            self._cache.pop(key, None)
            return None
        return dict(value)

    def _write_cache(self, key: str, value: dict[str, Any]) -> None:
        self._cache[key] = (time.time() + self.config.cache_ttl_s, dict(value))

    def forecast(self, request: Mapping[str, Any]) -> dict[str, Any]:
        cache_key = self._cache_key(request)
        cached = self._read_cache(cache_key)
        if cached is not None:
            cached_meta = dict(cached.get("meta", {}))
            cached_meta["cache_hit"] = True
            cached["meta"] = cached_meta
            return cached

        market_id = str(request["market_id"])
        as_of_ts = str(request.get("as_of_ts") or datetime.now(timezone.utc).isoformat())
        freq = str(request.get("freq") or self.config.default_freq)
        step_seconds = _parse_freq_to_seconds(freq)
        horizon_steps = int(request.get("horizon_steps") or self.config.default_horizon_steps)
        quantiles = [float(q) for q in (request.get("quantiles") or self.config.default_quantiles)]
        quantiles = sorted(quantiles)
        y_raw = [float(v) for v in request.get("y", [])]
        transform = request.get("transform") or {}
        space = str(transform.get("space") or self.config.transform_space)
        eps = float(transform.get("eps") or self.config.transform_eps)

        warnings: list[str] = []
        fallback_reason: str | None = None

        if len(y_raw) < self.config.min_points_for_tsfm:
            fallback_reason = "too_few_points"

        if request.get("liquidity_bucket", "").lower() == self.config.baseline_only_liquidity:
            fallback_reason = "baseline_only_liquidity_bucket"

        if set(quantiles) != set(self.config.default_quantiles):
            warnings.append("unsupported_quantiles_requested;using_default")
            quantiles = sorted(self.config.default_quantiles)

        now = time.time()
        if now < self._breaker_open_until:
            fallback_reason = "circuit_breaker_open"

        y_input = y_raw[-self.config.input_len_steps :]
        use_logit = space.lower() == "logit"
        y_model = [_logit(v, eps) if use_logit else v for v in y_input]

        quantile_paths: dict[float, list[float]]
        meta: dict[str, Any] = {
            "runtime": "tollama",
            "model_name": ((request.get("model") or {}).get("model_name") or "chronos"),
            "model_version": ((request.get("model") or {}).get("model_version") or "unknown"),
            "input_len": len(y_input),
            "transform": space,
            "warnings": warnings,
            "fallback_used": False,
            "cache_hit": False,
            "circuit_breaker_open": now < self._breaker_open_until,
        }

        if fallback_reason is None:
            try:
                quantile_paths, adapter_meta = self.adapter.forecast(
                    series=y_model,
                    horizon_steps=horizon_steps,
                    freq=freq,
                    quantiles=quantiles,
                    model_name=meta["model_name"],
                    model_version=meta["model_version"],
                    x_past=request.get("x_past") or {},
                    x_future=request.get("x_future") or {},
                    params=((request.get("model") or {}).get("params") or {}),
                )
                _validate_quantile_payload(
                    quantile_paths,
                    expected_quantiles=quantiles,
                    expected_horizon_steps=horizon_steps,
                )
                meta.update(adapter_meta)
                self._consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.config.circuit_breaker_failures:
                    self._breaker_open_until = time.time() + self.config.circuit_breaker_cooldown_s
                fallback_reason = f"tollama_error:{exc}"

        if fallback_reason is not None:
            band = forecast_baseline_band(
                y_input,
                method=self.config.baseline_method,
                horizon_steps=horizon_steps,
                step_seconds=step_seconds,
                market_id=market_id,
                ts=as_of_ts,
                use_logit=use_logit,
                eps=eps,
            )
            quantile_paths = {
                0.1: [float(band["q10"])] * horizon_steps,
                0.5: [float(band["q50"])] * horizon_steps,
                0.9: [float(band["q90"])] * horizon_steps,
            }
            meta["runtime"] = "baseline"
            meta["fallback_used"] = True
            meta["fallback_reason"] = fallback_reason
            warnings.append(f"fallback_reason={fallback_reason}")

        if use_logit and meta["runtime"] != "baseline":
            quantile_paths = {
                q: [_inv_logit(v) for v in values] for q, values in quantile_paths.items()
            }

        quantile_paths = {q: [_clip01(v) for v in values] for q, values in quantile_paths.items()}
        quantile_paths, had_crossing = _fix_quantile_crossing(quantile_paths)
        if had_crossing:
            warnings.append("quantile_crossing_fixed")

        lower = quantile_paths.get(0.1)
        upper = quantile_paths.get(0.9)
        if lower and upper:
            for idx, (_, _) in enumerate(zip(lower, upper)):
                width = quantile_paths[0.9][idx] - quantile_paths[0.1][idx]
                if width < self.config.min_interval_width:
                    center = quantile_paths[0.5][idx]
                    quantile_paths[0.1][idx] = _clip01(center - self.config.min_interval_width / 2)
                    quantile_paths[0.9][idx] = _clip01(center + self.config.min_interval_width / 2)
                    warnings.append("interval_min_width_enforced")
                elif width > self.config.max_interval_width:
                    center = quantile_paths[0.5][idx]
                    quantile_paths[0.1][idx] = _clip01(center - self.config.max_interval_width / 2)
                    quantile_paths[0.9][idx] = _clip01(center + self.config.max_interval_width / 2)
                    warnings.append("interval_max_width_clamped")

        response = {
            "market_id": market_id,
            "as_of_ts": as_of_ts,
            "freq": freq,
            "horizon_steps": horizon_steps,
            "quantiles": quantiles,
            "yhat_q": {str(q): quantile_paths[q] for q in sorted(quantile_paths)},
            "meta": meta,
        }

        if self.conformal_adjustment is not None:
            last_band = {
                "q10": response["yhat_q"]["0.1"][-1],
                "q50": response["yhat_q"]["0.5"][-1],
                "q90": response["yhat_q"]["0.9"][-1],
            }
            adjusted = apply_conformal_adjustment(last_band, self.conformal_adjustment)
            response["conformal_last_step"] = adjusted

        self._write_cache(cache_key, response)
        return response
