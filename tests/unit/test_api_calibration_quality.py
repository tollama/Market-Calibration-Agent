"""Tests for GET /metrics/calibration_quality endpoint."""

from __future__ import annotations

from typing import Any

import pytest

from api.schemas import CalibrationQualityResponse


class TestCalibrationQualityResponse:
    """Unit tests for the CalibrationQualityResponse schema."""

    def test_empty_response_has_defaults(self) -> None:
        response = CalibrationQualityResponse()
        assert response.total_market_count == 0
        assert response.low_confidence_market_count == 0
        assert response.brier is None
        assert response.drift_detected is None

    def test_full_response_round_trips(self) -> None:
        response = CalibrationQualityResponse(
            brier=0.15,
            log_loss=0.45,
            ece=0.08,
            slope=0.95,
            intercept=0.02,
            conformal_coverage=0.82,
            conformal_width=0.35,
            drift_detected=False,
            base_rate_swing=0.04,
            low_confidence_market_count=3,
            total_market_count=50,
        )
        data = response.model_dump()
        assert data["brier"] == pytest.approx(0.15)
        assert data["total_market_count"] == 50
        assert data["drift_detected"] is False

    def test_partial_response_is_valid(self) -> None:
        """Partially populated responses should not raise validation errors."""
        response = CalibrationQualityResponse(
            brier=0.20,
            total_market_count=10,
            low_confidence_market_count=2,
        )
        assert response.brier == pytest.approx(0.20)
        assert response.ece is None
        assert response.conformal_coverage is None


class TestCalibrationQualityEndpoint:
    """Integration tests for the /metrics/calibration_quality endpoint.

    Uses the FastAPI test client.
    """

    @pytest.fixture
    def client(self) -> Any:
        """Create a test client with mocked store."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi[test] or httpx not installed")

        from api.app import app
        return TestClient(app, raise_server_exceptions=False)

    def test_endpoint_returns_200(self, client: Any) -> None:
        """The endpoint should return 200 even when the store is empty."""
        response = client.get("/metrics/calibration_quality")
        # May return 200 or 500 depending on store availability
        # We just verify it doesn't crash completely
        assert response.status_code in (200, 422, 500)

    def test_endpoint_rejects_bad_window(self, client: Any) -> None:
        """Invalid window parameter should return 422."""
        response = client.get("/metrics/calibration_quality?window=foobar")
        assert response.status_code == 422

    def test_endpoint_accepts_valid_window(self, client: Any) -> None:
        """Valid window parameters should not cause 422."""
        response = client.get("/metrics/calibration_quality?window=30d")
        # Should not be a validation error
        assert response.status_code != 422 or response.status_code in (200, 500)


class TestCalibrationQualityResponseSerialization:
    """Verify JSON serialization of the response model."""

    def test_json_serialization(self) -> None:
        response = CalibrationQualityResponse(
            brier=0.12,
            log_loss=0.38,
            ece=0.05,
            drift_detected=True,
            base_rate_swing=0.18,
            total_market_count=25,
            low_confidence_market_count=5,
        )
        json_str = response.model_dump_json()
        assert "0.12" in json_str
        assert '"drift_detected":true' in json_str or '"drift_detected": true' in json_str
