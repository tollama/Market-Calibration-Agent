from __future__ import annotations

import math

import pytest

from calibration.trust_components import (
    TrustComponentConfig,
    derive_liquidity_depth,
    derive_manipulation_suspect,
    derive_question_quality,
    derive_stability,
    derive_trust_components,
)
from calibration.trust_score import compute_trust_score


# ---- derive_liquidity_depth ----


def test_liquidity_depth_from_bucket_and_volume() -> None:
    row = {"liquidity_bucket": "HIGH", "volume_24h": 200_000, "open_interest": 50_000}
    result = derive_liquidity_depth(row)
    # 0.4 * 0.8 (HIGH) + 0.6 * min(200000/100000, 1.0) = 0.32 + 0.6 = 0.92
    assert result == pytest.approx(0.92, abs=1e-6)


def test_liquidity_depth_low_bucket_low_volume() -> None:
    row = {"liquidity_bucket": "LOW", "volume_24h": 5_000, "open_interest": 3_000}
    result = derive_liquidity_depth(row)
    # 0.4 * 0.2 + 0.6 * (5000/100000) = 0.08 + 0.03 = 0.11
    assert result == pytest.approx(0.11, abs=1e-6)


def test_liquidity_depth_bucket_only() -> None:
    row = {"liquidity_bucket": "MID"}
    result = derive_liquidity_depth(row)
    assert result == pytest.approx(0.5, abs=1e-6)


def test_liquidity_depth_no_data_returns_fallback() -> None:
    assert derive_liquidity_depth({}) == 0.5


def test_liquidity_depth_uses_oi_when_volume_missing() -> None:
    row = {"liquidity_bucket": "MID", "open_interest": 80_000}
    result = derive_liquidity_depth(row)
    # 0.4 * 0.5 + 0.6 * (80000/100000) = 0.2 + 0.48 = 0.68
    assert result == pytest.approx(0.68, abs=1e-6)


# ---- derive_stability ----


def test_stability_low_volatility_is_high_stability() -> None:
    result = derive_stability({"vol": 0.05})
    # 1.0 - min(0.05/0.3, 1.0) = 1.0 - 0.1667 ≈ 0.833
    assert result == pytest.approx(1.0 - 0.05 / 0.3, abs=1e-6)


def test_stability_high_volatility_is_low_stability() -> None:
    result = derive_stability({"vol": 0.5})
    # 1.0 - min(0.5/0.3, 1.0) = 1.0 - 1.0 = 0.0
    assert result == pytest.approx(0.0, abs=1e-6)


def test_stability_zero_volatility() -> None:
    assert derive_stability({"vol": 0.0}) == pytest.approx(1.0, abs=1e-6)


def test_stability_missing_vol_returns_fallback() -> None:
    assert derive_stability({}) == 0.5


# ---- derive_question_quality ----


def test_question_quality_both_scores() -> None:
    row = {"ambiguity_score": 0.2, "resolution_risk_score": 0.3}
    result = derive_question_quality(row)
    # 1.0 - (0.6*0.2 + 0.4*0.3) = 1.0 - 0.24 = 0.76
    assert result == pytest.approx(0.76, abs=1e-6)


def test_question_quality_ambiguity_only() -> None:
    row = {"ambiguity_score": 0.4}
    result = derive_question_quality(row)
    assert result == pytest.approx(0.6, abs=1e-6)


def test_question_quality_resolution_risk_only() -> None:
    row = {"resolution_risk_score": 0.5}
    result = derive_question_quality(row)
    assert result == pytest.approx(0.5, abs=1e-6)


def test_question_quality_no_data_returns_fallback() -> None:
    assert derive_question_quality({}) == 0.5


# ---- derive_manipulation_suspect ----


def test_manipulation_suspect_high_oi_change() -> None:
    row = {"oi_change": 0.6, "volume_velocity": 0.5}
    result = derive_manipulation_suspect(row)
    # max(0.6/0.30, 0.5/3.0) = max(2.0→clipped to 1.0, 0.167) = 1.0
    assert result == pytest.approx(1.0, abs=1e-6)


def test_manipulation_suspect_low_values() -> None:
    row = {"oi_change": 0.03, "volume_velocity": 0.3}
    result = derive_manipulation_suspect(row)
    # max(0.03/0.30, 0.3/3.0) = max(0.1, 0.1) = 0.1
    assert result == pytest.approx(0.1, abs=1e-6)


def test_manipulation_suspect_no_data() -> None:
    assert derive_manipulation_suspect({}) == 0.0


def test_manipulation_suspect_negative_oi_change() -> None:
    row = {"oi_change": -0.15, "volume_velocity": 0.0}
    result = derive_manipulation_suspect(row)
    # abs(-0.15)/0.30 = 0.5
    assert result == pytest.approx(0.5, abs=1e-6)


# ---- derive_trust_components (orchestrator) ----


def test_derive_trust_components_returns_all_keys() -> None:
    row = {
        "liquidity_bucket": "HIGH",
        "volume_24h": 150_000,
        "open_interest": 50_000,
        "vol": 0.1,
        "ambiguity_score": 0.2,
        "resolution_risk_score": 0.1,
        "oi_change": 0.05,
        "volume_velocity": 0.5,
    }
    components = derive_trust_components(row)
    assert set(components) == {"liquidity_depth", "stability", "question_quality", "manipulation_suspect"}
    for value in components.values():
        assert 0.0 <= value <= 1.0


def test_derive_trust_components_empty_row_uses_fallbacks() -> None:
    components = derive_trust_components({})
    assert components["liquidity_depth"] == 0.5
    assert components["stability"] == 0.5
    assert components["question_quality"] == 0.5
    assert components["manipulation_suspect"] == 0.0


def test_derive_trust_components_custom_config() -> None:
    config = TrustComponentConfig(
        liquidity_high=50_000,
        volatility_ceiling=0.1,
        oi_spike_threshold=0.10,
        velocity_spike_threshold=1.0,
    )
    row = {"vol": 0.05, "oi_change": 0.05, "volume_velocity": 0.5}
    components = derive_trust_components(row, config=config)
    # stability: 1.0 - 0.05/0.1 = 0.5
    assert components["stability"] == pytest.approx(0.5, abs=1e-6)
    # manipulation: max(0.05/0.10, 0.5/1.0) = max(0.5, 0.5) = 0.5
    assert components["manipulation_suspect"] == pytest.approx(0.5, abs=1e-6)


# ---- integration with trust score formula ----


def test_derived_components_produce_valid_trust_score() -> None:
    row = {
        "liquidity_bucket": "MID",
        "volume_24h": 60_000,
        "open_interest": 40_000,
        "vol": 0.15,
        "oi_change": 0.02,
        "volume_velocity": 0.1,
    }
    components = derive_trust_components(row)
    score = compute_trust_score(components)
    assert 0.0 <= score <= 100.0
    # With real data, score should differ from the uniform-defaults 50.0
    assert score != pytest.approx(50.0, abs=1.0)


def test_empty_row_still_produces_valid_trust_score() -> None:
    components = derive_trust_components({})
    score = compute_trust_score(components)
    assert 0.0 <= score <= 100.0


def test_derived_components_nan_handling() -> None:
    row = {"vol": float("nan"), "oi_change": float("inf"), "volume_velocity": None}
    components = derive_trust_components(row)
    for value in components.values():
        assert not math.isnan(value)
        assert not math.isinf(value)
