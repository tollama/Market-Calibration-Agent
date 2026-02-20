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


def test_p2_11_tsfm_forecast_requires_inbound_auth_token(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (inbound auth control for /tsfm/forecast)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}

    response = client.post("/tsfm/forecast", json=payload)

    # Expected contract per gap matrix: unauthorized without inbound credentials.
    assert response.status_code == 401
