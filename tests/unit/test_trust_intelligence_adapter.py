"""Tests for Trust Intelligence Pipeline adapter."""

from __future__ import annotations

import pytest

from calibration.trust_intelligence_adapter import (
    extract_context,
    extract_features,
    extract_prediction_probability,
    run_trust_intelligence_for_market,
)


class TestExtractFeatures:
    def test_maps_volume_24h(self):
        row = {"volume_24h": 50000.0}
        features = extract_features(row)
        assert features["volume_change_24h"] == 50000.0

    def test_maps_liquidity_depth(self):
        row = {"liquidity_depth": 0.8}
        features = extract_features(row)
        assert features["liquidity_depth"] == 0.8

    def test_skips_none_values(self):
        row = {"volume_24h": None, "liquidity_depth": 0.5}
        features = extract_features(row)
        assert "volume_change_24h" not in features
        assert features["liquidity_depth"] == 0.5

    def test_skips_nan(self):
        row = {"volume_24h": float("nan")}
        features = extract_features(row)
        assert "volume_change_24h" not in features

    def test_empty_row(self):
        assert extract_features({}) == {}


class TestExtractContext:
    def test_maps_trust_score(self):
        row = {"trust_score": 0.8}
        context = extract_context(row)
        assert context["trust_score"] == 0.8

    def test_maps_volume(self):
        row = {"volume_24h": 100000.0}
        context = extract_context(row)
        assert context["market_volume_24h"] == 100000.0

    def test_v1_trust_score_fallback(self):
        row = {}
        context = extract_context(row, v1_trust_score=75.0)
        assert context["trust_score"] == 0.75  # 75/100

    def test_explicit_trust_score_overrides_v1(self):
        row = {"trust_score": 0.9}
        context = extract_context(row, v1_trust_score=50.0)
        assert context["trust_score"] == 0.9  # from row, not v1


class TestExtractPredictionProbability:
    def test_extracts_pred(self):
        assert extract_prediction_probability({"pred": 0.7}) == 0.7

    def test_extracts_p_yes(self):
        assert extract_prediction_probability({"p_yes": 0.55}) == 0.55

    def test_clips_to_unit(self):
        assert extract_prediction_probability({"pred": 1.5}) == 1.0
        assert extract_prediction_probability({"pred": -0.1}) == 0.0

    def test_returns_none_when_missing(self):
        assert extract_prediction_probability({}) is None


class TestRunTrustIntelligenceForMarket:
    def test_runs_pipeline(self):
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()
        rows = [{"pred": 0.7, "liquidity_depth": 0.8}]
        result = run_trust_intelligence_for_market(
            pipeline, market_rows=rows, v1_trust_score=70.0,
        )
        assert result is not None
        assert 0.0 <= result.trust.trust_score <= 1.0

    def test_empty_rows_returns_none(self):
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()
        result = run_trust_intelligence_for_market(
            pipeline, market_rows=[], v1_trust_score=50.0,
        )
        assert result is None

    def test_no_pred_uses_fallback(self):
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()
        rows = [{"liquidity_depth": 0.8}]  # no pred field
        result = run_trust_intelligence_for_market(
            pipeline, market_rows=rows, v1_trust_score=50.0,
        )
        assert result is not None
        # Should use 0.5 fallback
        assert result.uncertainty.prediction_probability == 0.5

    def test_averages_features_across_rows(self):
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()
        rows = [
            {"pred": 0.7, "liquidity_depth": 0.6},
            {"pred": 0.8, "liquidity_depth": 0.8},
        ]
        result = run_trust_intelligence_for_market(
            pipeline, market_rows=rows, v1_trust_score=70.0,
        )
        assert result is not None
        # Uses last row's pred (0.8)
        assert result.uncertainty.prediction_probability == 0.8
