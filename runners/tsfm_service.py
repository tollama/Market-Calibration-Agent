from __future__ import annotations

import hashlib
import json
import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

from calibration.conformal import ConformalAdjustment, apply_conformal_adjustment
from calibration.conformal_state import load_conformal_adjustment
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


class DegradationState(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    BASELINE_ONLY = "baseline-only"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


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

    cache_ttl_s: int = 60
    cache_stale_if_error_s: int = 120

    circuit_breaker_window_s: int = 300
    circuit_breaker_min_requests: int = 5
    circuit_breaker_failure_rate_to_open: float = 1.0
    circuit_breaker_cooldown_s: int = 120
    circuit_breaker_half_open_probe_requests: int = 2
    circuit_breaker_half_open_successes_to_close: int = 2

    degradation_window_s: int = 300
    degradation_min_requests: int = 5
    degraded_enter_failure_rate: float = 0.30
    baseline_only_enter_failure_rate: float = 0.70
    degraded_exit_failure_rate: float = 0.15
    baseline_only_exit_failure_rate: float = 0.25
    degradation_probe_every_n_requests: int = 1
    conformal_state_path: str = "data/derived/calibration/conformal_state.json"


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
        if conformal_adjustment is not None:
            self.conformal_adjustment = conformal_adjustment
            self._conformal_loaded_from_state = False
        else:
            try:
                self.conformal_adjustment = load_conformal_adjustment(self.config.conformal_state_path)
                self._conformal_loaded_from_state = self.conformal_adjustment is not None
            except Exception:  # noqa: BLE001
                self.conformal_adjustment = None
                self._conformal_loaded_from_state = False
        self._cache: dict[str, tuple[float, float, dict[str, Any]]] = {}
        self._breaker_state = CircuitState.CLOSED
        self._breaker_open_until = 0.0
        self._half_open_probe_count = 0
        self._half_open_success_count = 0
        self._events: deque[tuple[float, bool]] = deque()
        self._degradation_state = DegradationState.NORMAL
        self._degradation_probe_counter = 0

    @classmethod
    def from_runtime_config(
        cls,
        *,
        path: str | Path = "configs/tsfm_runtime.yaml",
        adapter: TollamaAdapter | None = None,
        conformal_adjustment: ConformalAdjustment | None = None,
    ) -> "TSFMRunnerService":
        config_path = Path(path)
        if not config_path.exists():
            return cls(adapter=adapter, config=TSFMServiceConfig(), conformal_adjustment=conformal_adjustment)

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        tsfm = raw.get("tsfm") or {}
        transform = tsfm.get("transform") or {}
        missing = tsfm.get("missing") or {}
        cache = tsfm.get("cache") or {}
        circuit = tsfm.get("circuit_breaker") or {}
        fallback = tsfm.get("fallback") or {}
        interval = tsfm.get("interval_sanity") or {}
        degradation = tsfm.get("degradation") or {}
        conformal = tsfm.get("conformal") or {}

        config = TSFMServiceConfig(
            default_freq=str(tsfm.get("freq", "5m")),
            input_len_steps=int(tsfm.get("input_len_steps", 288)),
            default_horizon_steps=int(tsfm.get("horizon_steps", 12)),
            default_quantiles=tuple(float(q) for q in tsfm.get("quantiles", [0.1, 0.5, 0.9])),
            transform_space=str(transform.get("space", "logit")),
            transform_eps=float(transform.get("eps", 1e-6)),
            max_gap_minutes=int(missing.get("max_gap_minutes", 60)),
            min_points_for_tsfm=int(missing.get("min_points_for_tsfm", 32)),
            min_interval_width=float(interval.get("min_width", 0.02)),
            max_interval_width=float(interval.get("max_width", 0.6)),
            baseline_method=str(fallback.get("baseline_method", "EWMA")),
            baseline_only_liquidity=str(fallback.get("baseline_only_liquidity_bucket", "low")),
            cache_ttl_s=int(cache.get("ttl_s", 60)),
            cache_stale_if_error_s=int(cache.get("stale_if_error_s", cache.get("stale_while_revalidate_s", 120))),
            circuit_breaker_window_s=int(circuit.get("window_s", 300)),
            circuit_breaker_min_requests=int(circuit.get("min_requests", 5)),
            circuit_breaker_failure_rate_to_open=float(circuit.get("failure_rate_to_open", 1.0)),
            circuit_breaker_cooldown_s=int(circuit.get("cooldown_s", 120)),
            circuit_breaker_half_open_probe_requests=int(circuit.get("half_open_probe_requests", 2)),
            circuit_breaker_half_open_successes_to_close=int(circuit.get("half_open_successes_to_close", 2)),
            degradation_window_s=int(degradation.get("window_s", 300)),
            degradation_min_requests=int(degradation.get("min_requests", 5)),
            degraded_enter_failure_rate=float(degradation.get("degraded_enter_failure_rate", 0.30)),
            baseline_only_enter_failure_rate=float(degradation.get("baseline_only_enter_failure_rate", 0.70)),
            degraded_exit_failure_rate=float(degradation.get("degraded_exit_failure_rate", 0.15)),
            baseline_only_exit_failure_rate=float(degradation.get("baseline_only_exit_failure_rate", 0.25)),
            degradation_probe_every_n_requests=int(degradation.get("probe_every_n_requests", 1)),
            conformal_state_path=str(conformal.get("state_path", "data/derived/calibration/conformal_state.json")),
        )
        return cls(adapter=adapter, config=config, conformal_adjustment=conformal_adjustment)

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

    def _read_cache(self, key: str, *, allow_stale: bool = False) -> tuple[dict[str, Any], bool] | None:
        row = self._cache.get(key)
        if row is None:
            return None
        expires_at, stale_until, value = row
        now = time.time()
        if now <= expires_at:
            return dict(value), False
        if now <= stale_until:
            if allow_stale:
                return dict(value), True
            return None
        self._cache.pop(key, None)
        return None

    def _write_cache(self, key: str, value: dict[str, Any]) -> None:
        now = time.time()
        self._cache[key] = (
            now + self.config.cache_ttl_s,
            now + self.config.cache_ttl_s + self.config.cache_stale_if_error_s,
            dict(value),
        )

    def _extract_max_gap_minutes(self, request: Mapping[str, Any], *, freq_seconds: int) -> float | None:
        if isinstance(request.get("max_gap_minutes"), (int, float)):
            return float(request["max_gap_minutes"])

        ts_candidates = request.get("y_ts") or request.get("observed_ts")
        if not isinstance(ts_candidates, list) or len(ts_candidates) < 2:
            return None

        parsed: list[datetime] = []
        for token in ts_candidates:
            if not isinstance(token, str):
                return None
            try:
                parsed.append(datetime.fromisoformat(token.replace("Z", "+00:00")))
            except ValueError:
                return None

        if len(parsed) < 2:
            return None

        max_gap_s = max(
            max((parsed[idx] - parsed[idx - 1]).total_seconds(), 0.0)
            for idx in range(1, len(parsed))
        )
        expected_step = max(freq_seconds, 1)
        return max_gap_s / 60.0 if max_gap_s > expected_step else 0.0

    def _prune_events(self, *, now: float, window_s: int) -> None:
        threshold = now - max(window_s, 1)
        while self._events and self._events[0][0] < threshold:
            self._events.popleft()

    def _failure_rate(self, *, now: float, window_s: int, min_requests: int) -> float | None:
        self._prune_events(now=now, window_s=window_s)
        if len(self._events) < min_requests:
            return None
        failures = sum(0 if success else 1 for _, success in self._events)
        return failures / max(len(self._events), 1)

    def _record_outcome(self, *, now: float, success: bool) -> None:
        self._events.append((now, success))
        self._prune_events(now=now, window_s=max(self.config.circuit_breaker_window_s, self.config.degradation_window_s))

    def _update_degradation_state(self, *, now: float) -> None:
        failure_rate = self._failure_rate(
            now=now,
            window_s=self.config.degradation_window_s,
            min_requests=self.config.degradation_min_requests,
        )
        if failure_rate is None:
            return

        state = self._degradation_state
        if state == DegradationState.NORMAL:
            if failure_rate >= self.config.baseline_only_enter_failure_rate:
                self._degradation_state = DegradationState.BASELINE_ONLY
            elif failure_rate >= self.config.degraded_enter_failure_rate:
                self._degradation_state = DegradationState.DEGRADED
            return

        if state == DegradationState.DEGRADED:
            if failure_rate >= self.config.baseline_only_enter_failure_rate:
                self._degradation_state = DegradationState.BASELINE_ONLY
            elif failure_rate <= self.config.degraded_exit_failure_rate:
                self._degradation_state = DegradationState.NORMAL
            return

        # baseline-only state recovery is intentionally stepwise: baseline-only -> degraded -> normal
        if state == DegradationState.BASELINE_ONLY:
            if failure_rate <= self.config.baseline_only_exit_failure_rate and self._breaker_state != CircuitState.OPEN:
                self._degradation_state = DegradationState.DEGRADED

    def _can_attempt_tollama(self, *, now: float) -> bool:
        if self._breaker_state == CircuitState.OPEN:
            if now < self._breaker_open_until:
                return False
            self._breaker_state = CircuitState.HALF_OPEN
            self._half_open_probe_count = 0
            self._half_open_success_count = 0

        if self._breaker_state == CircuitState.HALF_OPEN:
            if self._half_open_probe_count >= self.config.circuit_breaker_half_open_probe_requests:
                self._breaker_state = CircuitState.OPEN
                self._breaker_open_until = now + self.config.circuit_breaker_cooldown_s
                return False
            self._half_open_probe_count += 1

        return True

    def _on_tollama_success(self, *, now: float) -> None:
        self._record_outcome(now=now, success=True)

        if self._breaker_state == CircuitState.HALF_OPEN:
            self._half_open_success_count += 1
            if self._half_open_success_count >= self.config.circuit_breaker_half_open_successes_to_close:
                self._breaker_state = CircuitState.CLOSED
                self._half_open_probe_count = 0
                self._half_open_success_count = 0
        self._update_degradation_state(now=now)

    def _on_tollama_failure(self, *, now: float) -> None:
        self._record_outcome(now=now, success=False)

        if self._breaker_state == CircuitState.HALF_OPEN:
            self._breaker_state = CircuitState.OPEN
            self._breaker_open_until = now + self.config.circuit_breaker_cooldown_s
        else:
            failure_rate = self._failure_rate(
                now=now,
                window_s=self.config.circuit_breaker_window_s,
                min_requests=self.config.circuit_breaker_min_requests,
            )
            if failure_rate is not None and failure_rate >= self.config.circuit_breaker_failure_rate_to_open:
                self._breaker_state = CircuitState.OPEN
                self._breaker_open_until = now + self.config.circuit_breaker_cooldown_s

        self._update_degradation_state(now=now)

    def forecast(self, request: Mapping[str, Any]) -> dict[str, Any]:
        cache_key = self._cache_key(request)
        cached = self._read_cache(cache_key)
        if cached is not None:
            cached_value, _ = cached
            cached_meta = dict(cached_value.get("meta", {}))
            cached_meta["cache_hit"] = True
            cached_meta["cache_stale"] = False
            cached_value["meta"] = cached_meta
            return cached_value

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

        inferred_max_gap = self._extract_max_gap_minutes(request, freq_seconds=step_seconds)
        if inferred_max_gap is not None and inferred_max_gap > self.config.max_gap_minutes:
            fallback_reason = "max_gap_exceeded"

        if set(quantiles) != set(self.config.default_quantiles):
            warnings.append("unsupported_quantiles_requested;using_default")
            quantiles = sorted(self.config.default_quantiles)

        now = time.time()
        if self._degradation_state == DegradationState.BASELINE_ONLY and fallback_reason is None:
            self._degradation_probe_counter += 1
            probe_every = max(int(self.config.degradation_probe_every_n_requests), 1)
            if self._degradation_probe_counter % probe_every != 0:
                fallback_reason = "degradation_baseline_only"

        if fallback_reason is None and not self._can_attempt_tollama(now=now):
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
            "cache_stale": False,
            "circuit_breaker_state": self._breaker_state,
            "degradation_state": self._degradation_state,
            "conformal_state_loaded": self._conformal_loaded_from_state,
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
                self._on_tollama_success(now=now)
            except Exception as exc:  # noqa: BLE001
                self._on_tollama_failure(now=now)
                stale = self._read_cache(cache_key, allow_stale=True)
                if stale is not None:
                    stale_value, _ = stale
                    stale_meta = dict(stale_value.get("meta", {}))
                    stale_meta["cache_hit"] = True
                    stale_meta["cache_stale"] = True
                    stale_meta["fallback_used"] = True
                    stale_meta["fallback_reason"] = "stale_if_error"
                    stale_meta["warnings"] = list(stale_meta.get("warnings", [])) + [
                        "fallback_reason=stale_if_error"
                    ]
                    stale_meta["circuit_breaker_state"] = self._breaker_state
                    stale_meta["degradation_state"] = self._degradation_state
                    stale_value["meta"] = stale_meta
                    return stale_value
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

        meta["circuit_breaker_state"] = self._breaker_state
        meta["degradation_state"] = self._degradation_state

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
