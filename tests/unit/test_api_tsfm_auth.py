from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from api.app import app
from tests.helpers.prd2_fixtures import fixture_request

app_module = importlib.import_module("api.app")


class _FakeService:
    def forecast(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "market_id": payload["market_id"],
            "as_of_ts": payload["as_of_ts"],
            "freq": payload["freq"],
            "horizon_steps": payload["horizon_steps"],
            "quantiles": [0.1, 0.5, 0.9],
            "yhat_q": {"0.1": [0.1, 0.2], "0.5": [0.3, 0.4], "0.9": [0.6, 0.7]},
            "meta": {"runtime": "tollama", "fallback_used": False, "warnings": []},
        }



def _forecast_payload() -> dict[str, object]:
    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}
    return payload


def test_p2_11_tsfm_forecast_requires_inbound_auth_token(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (inbound auth control for /tsfm/forecast)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setenv("TSFM_FORECAST_API_TOKEN", "secret")
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard())
    client = TestClient(app)

    response = client.post("/tsfm/forecast", json=_forecast_payload())
    assert response.status_code == 401

    wrong = client.post(
        "/tsfm/forecast",
        json=_forecast_payload(),
        headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 401


def test_p2_11_tsfm_forecast_accepts_valid_inbound_token(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (inbound auth success path)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setenv("TSFM_FORECAST_API_TOKEN", "secret")
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard())
    client = TestClient(app)

    response = client.post(
        "/tsfm/forecast",
        json=_forecast_payload(),
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200


def test_p2_11_tsfm_forecast_rejects_auth_when_env_missing(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (environment token is required when auth is enabled)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.delenv("TSFM_FORECAST_API_TOKEN", raising=False)
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard())
    client = TestClient(app)

    response = client.post(
        "/tsfm/forecast",
        json=_forecast_payload(),
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 401


def test_p2_11_tsfm_forecast_rejects_placeholder_token_in_env(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (placeholder tokens are not accepted for auth)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setenv("TSFM_FORECAST_API_TOKEN", "tsfm-dev-token")
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard())
    client = TestClient(app)

    response = client.post(
        "/tsfm/forecast",
        json=_forecast_payload(),
        headers={"Authorization": "Bearer tsfm-dev-token"},
    )

    assert response.status_code == 401
