from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Dict, Iterable, Literal, Optional, Union

ForecastMethod = Literal["EWMA", "KALMAN", "ROLLING_QUANTILE"]
ForecastBand = Dict[str, Union[float, int, str, None]]

_STANDARD_NORMAL = NormalDist()
_Z10 = _STANDARD_NORMAL.inv_cdf(0.10)
_Z90 = _STANDARD_NORMAL.inv_cdf(0.90)


def _empirical_quantile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot compute quantiles from an empty sequence")
    if quantile <= 0:
        return min(values)
    if quantile >= 1:
        return max(values)

    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]

    weight = rank - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _to_model_space(value: float, *, use_logit: bool, eps: float) -> float:
    if not use_logit:
        return value
    p = _clip(value, eps, 1 - eps)
    return math.log(p / (1 - p))


def _from_model_space(value: float, *, use_logit: bool) -> float:
    if not use_logit:
        return value
    return 1 / (1 + math.exp(-value))


def _clean_series(series: Iterable[float]) -> list[float]:
    cleaned: list[float] = []
    for raw in series:
        value = float(raw)
        if math.isnan(value) or math.isinf(value):
            continue
        cleaned.append(value)
    if len(cleaned) < 2:
        raise ValueError("At least two finite observations are required")
    return cleaned


def _format_ts(ts: Union[datetime, str, None]) -> str:
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts)


def _build_forecast_band(
    *,
    q10: float,
    q50: float,
    q90: float,
    market_id: Optional[str],
    horizon_steps: int,
    step_seconds: int,
    method: ForecastMethod,
    model_id: str,
    ts: Union[datetime, str, None],
    band_calibration: str = "raw",
) -> ForecastBand:
    q10, q50, q90 = sorted((_clip(q10), _clip(q50), _clip(q90)))
    return {
        "ts": _format_ts(ts),
        "market_id": market_id,
        "horizon_steps": int(horizon_steps),
        "step_seconds": int(step_seconds),
        "q10": q10,
        "q50": q50,
        "q90": q90,
        "method": method,
        "model_id": model_id,
        "band_calibration": band_calibration,
    }


def ewma_band(
    series: Iterable[float],
    *,
    horizon_steps: int = 1,
    step_seconds: int = 300,
    alpha: float = 0.2,
    market_id: Optional[str] = None,
    ts: Union[datetime, str, None] = None,
    use_logit: bool = False,
    eps: float = 1e-6,
) -> ForecastBand:
    """EWMA level + variance band with normal quantile projection."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")

    values = _clean_series(series)
    transformed = [_to_model_space(v, use_logit=use_logit, eps=eps) for v in values]

    level = transformed[0]
    variance = 0.0
    for observation in transformed[1:]:
        prev_level = level
        level = alpha * observation + (1 - alpha) * prev_level
        innovation = observation - prev_level
        variance = alpha * innovation * innovation + (1 - alpha) * variance

    sigma = math.sqrt(max(variance, eps))
    sigma *= math.sqrt(max(int(horizon_steps), 1))

    q10 = _from_model_space(level + _Z10 * sigma, use_logit=use_logit)
    q50 = _from_model_space(level, use_logit=use_logit)
    q90 = _from_model_space(level + _Z90 * sigma, use_logit=use_logit)

    return _build_forecast_band(
        q10=q10,
        q50=q50,
        q90=q90,
        market_id=market_id,
        horizon_steps=horizon_steps,
        step_seconds=step_seconds,
        method="EWMA",
        model_id="baseline-ewma-v1",
        ts=ts,
    )


def kalman_band(
    series: Iterable[float],
    *,
    horizon_steps: int = 1,
    step_seconds: int = 300,
    process_var: Optional[float] = None,
    measurement_var: Optional[float] = None,
    market_id: Optional[str] = None,
    ts: Union[datetime, str, None] = None,
    use_logit: bool = False,
    eps: float = 1e-6,
) -> ForecastBand:
    """Local-level Kalman baseline band."""
    values = _clean_series(series)
    transformed = [_to_model_space(v, use_logit=use_logit, eps=eps) for v in values]

    diffs = [transformed[idx] - transformed[idx - 1] for idx in range(1, len(transformed))]
    if process_var is None:
        mean_diff = sum(diffs) / len(diffs)
        process_var = max(
            sum((x - mean_diff) ** 2 for x in diffs) / max(len(diffs) - 1, 1),
            eps,
        )
    if measurement_var is None:
        mean_level = sum(transformed) / len(transformed)
        measurement_var = max(
            sum((x - mean_level) ** 2 for x in transformed) / max(len(transformed) - 1, 1),
            eps,
        )

    level = transformed[0]
    covariance = 1.0
    for observation in transformed[1:]:
        pred_level = level
        pred_covariance = covariance + process_var
        gain = pred_covariance / (pred_covariance + measurement_var)
        level = pred_level + gain * (observation - pred_level)
        covariance = (1 - gain) * pred_covariance

    forecast_var = covariance + max(horizon_steps - 1, 0) * process_var
    sigma = math.sqrt(max(forecast_var, eps))
    q10 = _from_model_space(level + _Z10 * sigma, use_logit=use_logit)
    q50 = _from_model_space(level, use_logit=use_logit)
    q90 = _from_model_space(level + _Z90 * sigma, use_logit=use_logit)

    return _build_forecast_band(
        q10=q10,
        q50=q50,
        q90=q90,
        market_id=market_id,
        horizon_steps=horizon_steps,
        step_seconds=step_seconds,
        method="KALMAN",
        model_id="baseline-kalman-v1",
        ts=ts,
    )


def rolling_quantile_band(
    series: Iterable[float],
    *,
    horizon_steps: int = 1,
    step_seconds: int = 300,
    window: int = 64,
    market_id: Optional[str] = None,
    ts: Union[datetime, str, None] = None,
    use_logit: bool = False,
    eps: float = 1e-6,
) -> ForecastBand:
    """Empirical rolling quantile band from a trailing window."""
    if window <= 0:
        raise ValueError("window must be positive")

    values = _clean_series(series)
    transformed = [_to_model_space(v, use_logit=use_logit, eps=eps) for v in values]
    window_values = transformed[-window:]

    q10 = _from_model_space(_empirical_quantile(window_values, 0.10), use_logit=use_logit)
    q50 = _from_model_space(_empirical_quantile(window_values, 0.50), use_logit=use_logit)
    q90 = _from_model_space(_empirical_quantile(window_values, 0.90), use_logit=use_logit)

    return _build_forecast_band(
        q10=q10,
        q50=q50,
        q90=q90,
        market_id=market_id,
        horizon_steps=horizon_steps,
        step_seconds=step_seconds,
        method="ROLLING_QUANTILE",
        model_id="baseline-rolling-quantile-v1",
        ts=ts,
    )


def forecast_baseline_band(
    series: Iterable[float],
    *,
    method: str,
    **kwargs: object,
) -> ForecastBand:
    method_upper = method.upper()
    if method_upper == "EWMA":
        return ewma_band(series, **kwargs)
    if method_upper == "KALMAN":
        return kalman_band(series, **kwargs)
    if method_upper == "ROLLING_QUANTILE":
        return rolling_quantile_band(series, **kwargs)
    raise ValueError(f"Unsupported baseline method: {method}")


__all__ = [
    "ForecastMethod",
    "ewma_band",
    "kalman_band",
    "rolling_quantile_band",
    "forecast_baseline_band",
]
