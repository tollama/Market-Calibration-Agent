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


def test_p2_11_tsfm_forecast_enforces_rate_limit_with_retry_after(monkeypatch) -> None:
    """Traceability: PRD2 P2-11 (inbound rate-limit + Retry-After semantics)."""
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    monkeypatch.setenv("TSFM_FORECAST_API_TOKEN", "secret")
    monkeypatch.setattr(app_module, "_tsfm_guard", app_module._TSFMInboundGuard())
    client = TestClient(app)

    payload = fixture_request("D1_normal")
    payload["x_past"] = {}
    payload["x_future"] = {}

    # Burst calls; expectation is at least one 429 with retry-after metadata.
    responses = [
        client.post(
            "/tsfm/forecast",
            json=payload,
            headers={"Authorization": "Bearer secret"},
        )
        for _ in range(8)
    ]

    assert any(r.status_code == 429 for r in responses)
    limited = next(r for r in responses if r.status_code == 429)
    assert "retry-after" in {k.lower() for k in limited.headers.keys()}
    assert int(limited.headers["Retry-After"]) >= 1
