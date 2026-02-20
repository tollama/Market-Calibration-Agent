from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field


class RunnerConfig(BaseModel):
    """Shared runtime config for TSFM runners."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    method: str = "TSFM"
    context_length: int = 256
    device: str = "cpu"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ForecastResult(BaseModel):
    """Quantile forecast payload from runner implementations."""

    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    market_id: Optional[str] = None
    horizon_steps: int
    step_seconds: int
    quantiles: dict[float, list[float]]
    method: str
    model_id: str
    band_calibration: str = "raw"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def quantile_at(self, quantile: float, step_index: int = -1) -> float:
        series = self.quantiles.get(float(quantile))
        if series is None:
            raise KeyError(f"Missing quantile {quantile}")
        if not series:
            raise ValueError(f"Quantile {quantile} has no forecast values")
        return float(series[step_index])

    def to_forecast_band(
        self,
        *,
        step_index: int = -1,
        quantile_key_map: Optional[Mapping[float, str]] = None,
    ) -> dict[str, Any]:
        q_map = quantile_key_map or {0.1: "q10", 0.5: "q50", 0.9: "q90"}
        result: dict[str, Any] = {
            "ts": self.ts.isoformat(),
            "market_id": self.market_id,
            "horizon_steps": self.horizon_steps,
            "step_seconds": self.step_seconds,
            "method": self.method,
            "model_id": self.model_id,
            "band_calibration": self.band_calibration,
        }
        for quantile, key in q_map.items():
            result[key] = self.quantile_at(quantile, step_index=step_index)
        return result


class TSFMRunnerBase(ABC):
    """Contract for model-specific quantile forecasters."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

    @abstractmethod
    def forecast_quantiles(
        self,
        series: Sequence[float],
        horizon: int,
        step: int,
        quantiles: Sequence[float],
        covariates: Optional[Mapping[str, Sequence[float]]] = None,
        market_id: Optional[str] = None,
    ) -> ForecastResult:
        """Return quantile forecasts for `horizon` steps."""
        raise NotImplementedError
