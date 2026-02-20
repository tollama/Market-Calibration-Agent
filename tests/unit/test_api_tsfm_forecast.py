from __future__ import annotations

from fastapi.testclient import TestClient

import importlib

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

    def render_prometheus_metrics(self) -> str:
        return "# TYPE tsfm_request_total counter\ntsfm_request_total 1\n"


def test_post_tsfm_forecast_contract(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard(require_auth=False, rate_limit_per_minute=120))
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}

    response = client.post("/tsfm/forecast", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["market_id"] == "prd2-d1-normal"
    assert set(body["yhat_q"]) == {"0.1", "0.5", "0.9"}


def test_post_tsfm_forecast_accepts_gap_metadata_fields(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _CaptureService:
        def forecast(self, payload: dict[str, object]) -> dict[str, object]:
            captured.update(payload)
            return _FakeService().forecast(payload)

    monkeypatch.setattr(app_module, "_tsfm_service", _CaptureService())
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard(require_auth=False, rate_limit_per_minute=120))
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}
    payload["y_ts"] = ["2026-02-20T00:00:00Z", "2026-02-20T00:05:00Z"]
    payload["max_gap_minutes"] = 120

    response = client.post("/tsfm/forecast", json=payload)

    assert response.status_code == 200
    assert captured["y_ts"] == payload["y_ts"]
    assert captured["max_gap_minutes"] == 120


def test_post_tsfm_forecast_requires_bearer_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setenv("TSFM_FORECAST_API_TOKEN", "secret")
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard(require_auth=True, rate_limit_per_minute=120))
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}

    denied = client.post("/tsfm/forecast", json=payload)
    assert denied.status_code == 401

    allowed = client.post(
        "/tsfm/forecast",
        json=payload,
        headers={"Authorization": "Bearer secret"},
    )
    assert allowed.status_code == 200


def test_post_tsfm_forecast_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.delenv("TSFM_FORECAST_API_TOKEN", raising=False)
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard(require_auth=False, rate_limit_per_minute=1))
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}

    first = client.post("/tsfm/forecast", json=payload, headers={"X-API-Key": "caller-1"})
    second = client.post("/tsfm/forecast", json=payload, headers={"X-API-Key": "caller-1"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_get_tsfm_metrics_exposes_prometheus_payload(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    client = TestClient(app)

    response = client.get("/tsfm/metrics")

    assert response.status_code == 200
    assert "tsfm_request_total" in response.text
