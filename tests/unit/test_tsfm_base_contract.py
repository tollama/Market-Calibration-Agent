from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest
from pydantic import ValidationError

from runners.tsfm_base import ForecastResult, RunnerConfig, TSFMRunnerBase


def _forecast_result_with(quantiles: dict[float, list[float]]) -> ForecastResult:
    return ForecastResult(
        ts=datetime(2026, 2, 20, tzinfo=timezone.utc),
        market_id="market-1",
        horizon_steps=2,
        step_seconds=300,
        quantiles=quantiles,
        method="TSFM",
        model_id="model-1",
    )


class _FakeTSFMRunner(TSFMRunnerBase):
    def forecast_quantiles(
        self,
        series: Sequence[float],
        horizon: int,
        step: int,
        quantiles: Sequence[float],
        covariates: Mapping[str, Sequence[float]] | None = None,
        market_id: str | None = None,
    ) -> ForecastResult:
        last = float(series[-1]) if series else 0.0
        quantile_values = {float(q): [last] * horizon for q in quantiles}
        return ForecastResult(
            ts=datetime(2026, 2, 20, tzinfo=timezone.utc),
            market_id=market_id,
            horizon_steps=horizon,
            step_seconds=step,
            quantiles=quantile_values,
            method=self.config.method,
            model_id=self.config.model_id,
            metadata={"covariate_count": 0 if covariates is None else len(covariates)},
        )


def test_quantile_at_returns_requested_quantile_and_step() -> None:
    result = _forecast_result_with(
        {
            0.1: [0.10, 0.11],
            0.5: [0.50, 0.51],
            0.9: [0.90, 0.91],
        }
    )

    assert result.quantile_at(0.5) == pytest.approx(0.51)
    assert result.quantile_at(0.5, step_index=0) == pytest.approx(0.50)


def test_quantile_at_raises_for_missing_quantile_series() -> None:
    result = _forecast_result_with({0.5: [0.3, 0.4]})

    with pytest.raises(KeyError, match="Missing quantile 0.1"):
        result.quantile_at(0.1)


def test_quantile_at_raises_for_empty_quantile_series() -> None:
    result = _forecast_result_with({0.1: []})

    with pytest.raises(ValueError, match="Quantile 0.1 has no forecast values"):
        result.quantile_at(0.1)


def test_to_forecast_band_returns_expected_keys_and_values() -> None:
    result = _forecast_result_with(
        {
            0.1: [0.12, 0.13],
            0.5: [0.52, 0.53],
            0.9: [0.92, 0.93],
        }
    )

    band = result.to_forecast_band()

    assert set(band) == {
        "ts",
        "market_id",
        "horizon_steps",
        "step_seconds",
        "method",
        "model_id",
        "band_calibration",
        "q10",
        "q50",
        "q90",
    }
    assert band["ts"] == "2026-02-20T00:00:00+00:00"
    assert band["market_id"] == "market-1"
    assert band["horizon_steps"] == 2
    assert band["step_seconds"] == 300
    assert band["method"] == "TSFM"
    assert band["model_id"] == "model-1"
    assert band["band_calibration"] == "raw"
    assert band["q10"] == pytest.approx(0.13)
    assert band["q50"] == pytest.approx(0.53)
    assert band["q90"] == pytest.approx(0.93)


def test_runner_config_validates_and_forbids_extra_fields() -> None:
    config = RunnerConfig(model_id="model-a")

    assert config.model_id == "model-a"
    assert config.method == "TSFM"
    assert config.context_length == 256
    assert config.device == "cpu"
    assert config.metadata == {}

    with pytest.raises(ValidationError) as type_error:
        RunnerConfig(model_id="model-a", context_length="not-an-int")
    assert any(
        err["loc"] == ("context_length",) for err in type_error.value.errors()
    )

    with pytest.raises(ValidationError) as extra_error:
        RunnerConfig(model_id="model-a", unsupported="value")
    assert any(err["type"] == "extra_forbidden" for err in extra_error.value.errors())


def test_fake_runner_subclass_matches_tsfm_base_contract() -> None:
    runner = _FakeTSFMRunner(RunnerConfig(model_id="fake-model", method="TSFM_FAKE"))

    result = runner.forecast_quantiles(
        series=[0.2, 0.3, 0.4],
        horizon=3,
        step=60,
        quantiles=[0.1, 0.5, 0.9],
        covariates={"volume": [1.0, 2.0, 3.0]},
        market_id="market-abc",
    )

    assert isinstance(result, ForecastResult)
    assert result.market_id == "market-abc"
    assert result.horizon_steps == 3
    assert result.step_seconds == 60
    assert result.method == "TSFM_FAKE"
    assert result.model_id == "fake-model"
    assert result.quantiles[0.1] == pytest.approx([0.4, 0.4, 0.4])
    assert result.quantiles[0.5] == pytest.approx([0.4, 0.4, 0.4])
    assert result.quantiles[0.9] == pytest.approx([0.4, 0.4, 0.4])
