from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app


class _MetricsFakeService:
    def render_prometheus_metrics(self) -> str:
        return 'tsfm_request_total{rollout_stage="canary_5",status="success"} 2\n'


def test_metrics_endpoint_returns_prometheus_payload(monkeypatch) -> None:
    import importlib

    app_module = importlib.import_module("api.app")
    monkeypatch.setattr(app_module, "_tsfm_service", _MetricsFakeService())

    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.text.startswith("tsfm_request_total")
    assert "rollout_stage=\"canary_5\"" in response.text
