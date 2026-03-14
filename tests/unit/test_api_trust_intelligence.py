"""Tests for Trust Intelligence API endpoint."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import LocalDerivedStore, get_derived_store


def _make_store(tmp_path: Path) -> LocalDerivedStore:
    derived = tmp_path / "derived"
    derived.mkdir()
    return LocalDerivedStore(derived_root=derived)


def _write_scoreboard(store: LocalDerivedStore, rows: list[dict]) -> None:
    store.scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
    store.scoreboard_path.write_text(json.dumps(rows), encoding="utf-8")


def _write_trust_intelligence(store: LocalDerivedStore, rows: list[dict]) -> None:
    store.trust_intelligence_path.parent.mkdir(parents=True, exist_ok=True)
    store.trust_intelligence_path.write_text(json.dumps(rows), encoding="utf-8")


class TestTrustIntelligenceEndpoint:
    def test_persisted_result(self, tmp_path):
        store = _make_store(tmp_path)
        _write_scoreboard(store, [
            {"market_id": "mkt-1", "trust_score": 72.5, "window": "90d"},
        ])
        _write_trust_intelligence(store, [
            {
                "market_id": "mkt-1",
                "uncertainty": {
                    "entropy": 0.88,
                    "normalized_uncertainty": 0.88,
                    "prediction_probability": 0.7,
                },
                "conformal": {
                    "p_low": 0.4, "p_high": 0.9,
                    "confidence_level": 0.9,
                    "coverage_validity": True,
                    "coverage_tightness": 0.5,
                    "method": "split",
                    "sample_size": 50,
                },
                "shap": {
                    "feature_contributions": [
                        {"feature_name": "liquidity_depth", "shap_value": 0.1, "rank": 1, "direction": "positive"},
                    ],
                    "interaction_effects": {},
                    "shap_stability": 0.92,
                    "iterations_used": 3,
                    "base_value": 0.5,
                },
                "constraints": {
                    "constraint_satisfied": True,
                    "violations": [],
                    "risk_category": "GREEN",
                    "constraints_checked": 5,
                },
                "trust": {
                    "trust_score": 0.72,
                    "weights": {"uncertainty": 0.25, "coverage": 0.25, "shap": 0.25, "constraint": 0.25},
                    "component_scores": {"uncertainty": 0.12, "coverage": 0.5, "shap": 0.92, "constraint": 1.0},
                    "calibration_status": "well_calibrated",
                    "ece": 0.03,
                    "ocr": 0.1,
                    "version": "v3.0",
                },
                "chain_of_trust": [],
            },
        ])

        app.dependency_overrides[get_derived_store] = lambda: store
        try:
            client = TestClient(app)
            response = client.get("/trust-intelligence/mkt-1")
            assert response.status_code == 200

            data = response.json()
            assert data["market_id"] == "mkt-1"
            assert data["trust_score"] == 0.72
            assert data["risk_category"] == "GREEN"
            assert data["constraint_satisfied"] is True
            assert data["shap_stability"] == 0.92
            assert data["conformal_method"] == "split"
            assert len(data["top_features"]) == 1
            assert data["top_features"][0]["feature_name"] == "liquidity_depth"
        finally:
            app.dependency_overrides.clear()

    def test_on_demand_computation(self, tmp_path):
        """When no persisted result, endpoint computes on-demand."""
        store = _make_store(tmp_path)
        _write_scoreboard(store, [
            {
                "market_id": "mkt-2",
                "trust_score": 65.0,
                "window": "90d",
                "pred": 0.7,
                "liquidity_depth": 0.8,
            },
        ])

        app.dependency_overrides[get_derived_store] = lambda: store
        try:
            client = TestClient(app)
            response = client.get("/trust-intelligence/mkt-2")
            assert response.status_code == 200

            data = response.json()
            assert data["market_id"] == "mkt-2"
            assert 0.0 <= data["trust_score"] <= 1.0
            assert data["pipeline_version"] == "3.0"
            assert data["trust_score_v1"] == 65.0
        finally:
            app.dependency_overrides.clear()

    def test_market_not_found(self, tmp_path):
        store = _make_store(tmp_path)
        _write_scoreboard(store, [])

        app.dependency_overrides[get_derived_store] = lambda: store
        try:
            client = TestClient(app)
            response = client.get("/trust-intelligence/nonexistent")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
