from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

import importlib

api_app = importlib.import_module("api.app")


def _write_fixture_files(tmp_path) -> None:
    derived = tmp_path / "derived"

    metrics_dir = derived / "metrics"
    metrics_dir.mkdir(parents=True)
    scoreboard_payload = [
        {
            "market_id": "mkt-90",
            "window": "90d",
            "trust_score": 74.2,
            "brier": 0.18,
            "logloss": 0.54,
            "ece": 0.06,
            "liquidity_bucket": "MID",
            "category": "politics",
            "as_of": "2026-02-20T00:00:00Z",
        },
        {
            "market_id": "mkt-90",
            "window": "30d",
            "trust_score": 70.0,
            "brier": 0.2,
            "logloss": 0.6,
            "ece": 0.08,
            "liquidity_bucket": "MID",
            "category": "politics",
            "as_of": "2026-02-20T00:00:00Z",
        },
    ]
    (metrics_dir / "scoreboard.json").write_text(json.dumps(scoreboard_payload), encoding="utf-8")

    alerts_dir = derived / "alerts"
    alerts_dir.mkdir(parents=True)
    alerts_payload = [
        {
            "alert_id": "a-1",
            "market_id": "mkt-90",
            "ts": "2026-02-20T11:00:00Z",
            "severity": "HIGH",
            "reason_codes": ["BAND_BREACH"],
            "evidence": {"p_yes": 0.81},
            "llm_explain_5lines": ["1", "2", "3", "4", "5"],
        }
    ]
    (alerts_dir / "alerts.json").write_text(json.dumps(alerts_payload), encoding="utf-8")


def test_markets_and_detail_and_metrics(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(api_app.app)

    markets = client.get("/markets")
    assert markets.status_code == 200
    assert markets.json()["total"] == 1

    detail = client.get("/markets/mkt-90")
    assert detail.status_code == 200
    assert detail.json()["market_id"] == "mkt-90"

    metrics = client.get("/markets/mkt-90/metrics")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["alert_total"] == 1
    assert payload["alert_severity_counts"]["HIGH"] == 1


def test_market_comparison_endpoint(monkeypatch):
    class StubService:
        def forecast(self, request):
            runtime = "baseline" if request.get("liquidity_bucket") == "low" else "tollama"
            q50 = 0.5 if runtime == "baseline" else 0.6
            return {
                "market_id": request["market_id"],
                "as_of_ts": request["as_of_ts"],
                "freq": request["freq"],
                "horizon_steps": request["horizon_steps"],
                "quantiles": [0.1, 0.5, 0.9],
                "yhat_q": {"0.1": [0.4] * 3, "0.5": [q50] * 3, "0.9": [0.7] * 3},
                "meta": {"runtime": runtime},
            }

    monkeypatch.setattr(api_app, "_tsfm_service", StubService())
    client = TestClient(api_app.app)

    body = {
        "forecast": {
            "market_id": "mkt-90",
            "as_of_ts": "2026-02-21T00:00:00Z",
            "freq": "5m",
            "horizon_steps": 3,
            "quantiles": [0.1, 0.5, 0.9],
            "y": [0.45, 0.46, 0.47, 0.48],
        },
        "baseline_liquidity_bucket": "low",
    }
    response = client.post("/markets/mkt-90/comparison", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"]["meta"]["runtime"] == "baseline"
    assert payload["tollama"]["meta"]["runtime"] == "tollama"
    assert payload["delta_last_q50"] == pytest.approx(0.1)
