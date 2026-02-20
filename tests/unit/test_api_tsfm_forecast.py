from __future__ import annotations

from fastapi.testclient import TestClient

import importlib

from api.app import app

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


def test_post_tsfm_forecast_contract(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_tsfm_service", _FakeService())
    client = TestClient(app)

    response = client.post(
        "/tsfm/forecast",
        json={
            "market_id": "m-1",
            "as_of_ts": "2026-02-20T00:00:00Z",
            "freq": "5m",
            "horizon_steps": 2,
            "quantiles": [0.1, 0.5, 0.9],
            "y": [0.4, 0.5, 0.55, 0.56],
            "x_past": {},
            "x_future": {},
            "transform": {"space": "logit", "eps": 1e-6},
            "model": {"provider": "tollama", "model_name": "chronos", "params": {}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["market_id"] == "m-1"
    assert set(body["yhat_q"]) == {"0.1", "0.5", "0.9"}
