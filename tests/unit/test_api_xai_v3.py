"""Tests for XAI v3 API endpoints (constraint-verify and audit-trail)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app


class TestConstraintVerifyEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_all_pass(self):
        response = self.client.post(
            "/api/xai/v3/constraint-verify",
            json={
                "prediction": 0.8,
                "interval": [0.6, 0.9],
                "context": {
                    "trust_score": 0.8,
                    "market_volume_24h": 100000,
                    "days_to_resolution": 10,
                    "max_open_correlation": 0.5,
                    "is_restricted_category": 0.0,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["constraint_satisfied"] is True
        assert data["risk_category"] == "GREEN"
        assert len(data["violations"]) == 0
        assert data["constraints_checked"] == 5

    def test_critical_violation(self):
        response = self.client.post(
            "/api/xai/v3/constraint-verify",
            json={
                "prediction": 0.3,
                "interval": [0.1, 0.5],
                "context": {
                    "trust_score": 0.3,
                    "days_to_resolution": 1,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["constraint_satisfied"] is False
        assert data["risk_category"] == "RED"

    def test_custom_constraints(self):
        response = self.client.post(
            "/api/xai/v3/constraint-verify",
            json={
                "prediction": 0.5,
                "interval": [0.3, 0.7],
                "context": {"custom_field": 0.2},
                "constraints": [
                    {
                        "name": "custom_min",
                        "constraint_type": "risk_threshold",
                        "severity": "critical",
                        "field": "custom_field",
                        "operator": ">=",
                        "threshold": 0.5,
                    }
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["constraint_satisfied"] is False
        assert len(data["violations"]) == 1
        assert data["violations"][0]["constraint_name"] == "custom_min"

    def test_verification_time_included(self):
        response = self.client.post(
            "/api/xai/v3/constraint-verify",
            json={
                "prediction": 0.5,
                "interval": [0.3, 0.7],
                "context": {"trust_score": 0.8},
            },
        )
        data = response.json()
        assert "verification_time_ms" in data


class TestConstraintVerifyBatchEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_batch_verify(self):
        response = self.client.post(
            "/api/xai/v3/constraint-verify/batch",
            json={
                "items": [
                    {
                        "prediction": 0.8,
                        "interval": [0.6, 0.9],
                        "context": {"trust_score": 0.8, "days_to_resolution": 10},
                    },
                    {
                        "prediction": 0.3,
                        "interval": [0.1, 0.5],
                        "context": {"trust_score": 0.3, "days_to_resolution": 1},
                    },
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["constraint_satisfied"] is True
        assert data["results"][1]["constraint_satisfied"] is False


class TestAuditTrailEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_empty_trail(self):
        with patch("api.app._AUDIT_LOG_PATH", Path("/nonexistent/path.jsonl")):
            response = self.client.get("/api/xai/v3/audit-trail/any-session")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["entries"] == []
            assert data["chain_valid"] is True

    def test_trail_with_entries(self):
        from trust_intelligence.audit.chain_of_trust import ChainOfTrustLogger
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = ChainOfTrustLogger(
                log_path=log_path, agent_id="test", session_id="sess-123"
            )

            for p in [0.3, 0.7]:
                result = pipeline.run(prediction_probability=p)
                logger.record({"p": p}, result)

            with patch("api.app._AUDIT_LOG_PATH", log_path):
                response = self.client.get("/api/xai/v3/audit-trail/sess-123")
                assert response.status_code == 200
                data = response.json()
                assert data["session_id"] == "sess-123"
                assert data["total"] == 2
                assert len(data["entries"]) == 2
                assert data["chain_valid"] is True

    def test_trail_all_sessions(self):
        from trust_intelligence.audit.chain_of_trust import ChainOfTrustLogger
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"

            logger = ChainOfTrustLogger(
                log_path=log_path, agent_id="test", session_id="s1"
            )
            result = pipeline.run(prediction_probability=0.5)
            logger.record({"p": 0.5}, result)

            with patch("api.app._AUDIT_LOG_PATH", log_path):
                response = self.client.get("/api/xai/v3/audit-trail")
                assert response.status_code == 200
                data = response.json()
                assert data["total"] == 1
                assert data["chain_valid"] is True

    def test_trail_limit(self):
        from trust_intelligence.audit.chain_of_trust import ChainOfTrustLogger
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = ChainOfTrustLogger(
                log_path=log_path, agent_id="test", session_id="sess-1"
            )

            for p in [0.1, 0.2, 0.3, 0.4, 0.5]:
                result = pipeline.run(prediction_probability=p)
                logger.record({"p": p}, result)

            with patch("api.app._AUDIT_LOG_PATH", log_path):
                response = self.client.get(
                    "/api/xai/v3/audit-trail/sess-1?limit=2"
                )
                data = response.json()
                assert data["total"] == 5
                assert len(data["entries"]) == 2

    def test_nonexistent_session_returns_empty(self):
        from trust_intelligence.audit.chain_of_trust import ChainOfTrustLogger
        from trust_intelligence.pipeline.trust_pipeline import TrustIntelligencePipeline

        pipeline = TrustIntelligencePipeline()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = ChainOfTrustLogger(
                log_path=log_path, agent_id="test", session_id="sess-1"
            )
            result = pipeline.run(prediction_probability=0.5)
            logger.record({"p": 0.5}, result)

            with patch("api.app._AUDIT_LOG_PATH", log_path):
                response = self.client.get("/api/xai/v3/audit-trail/nonexistent")
                data = response.json()
                assert data["total"] == 0
                assert data["entries"] == []
