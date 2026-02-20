from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.app import app


def _write_fixture_files(tmp_path) -> None:
    derived = tmp_path / "derived"

    metrics_dir = derived / "metrics"
    metrics_dir.mkdir(parents=True)
    scoreboard_payload = [
        {
            "market_id": "mkt-high",
            "window": "90d",
            "trust_score": 82.4,
            "brier": 0.15,
            "logloss": 0.51,
            "ece": 0.04,
            "liquidity_bucket": "HIGH",
            "category": "politics",
            "as_of": "2026-02-20T00:00:00Z",
        },
        {
            "market_id": "mkt-mid",
            "window": "90d",
            "trust_score": 64.9,
            "brier": 0.23,
            "logloss": 0.66,
            "ece": 0.10,
            "liquidity_bucket": "MID",
            "category": "sports",
            "as_of": "2026-02-20T00:00:00Z",
        },
        {
            "market_id": "mkt-none",
            "window": "90d",
            "trust_score": None,
            "brier": 0.31,
            "logloss": 0.77,
            "ece": 0.15,
            "liquidity_bucket": "LOW",
            "category": "crypto",
            "as_of": "2026-02-20T00:00:00Z",
        },
        {
            "market_id": "mkt-30",
            "window": "30d",
            "trust_score": 90.0,
            "brier": 0.12,
            "logloss": 0.43,
            "ece": 0.03,
            "liquidity_bucket": "HIGH",
            "category": "politics",
            "as_of": "2026-02-20T00:00:00Z",
        },
    ]
    (metrics_dir / "scoreboard.json").write_text(
        json.dumps(scoreboard_payload),
        encoding="utf-8",
    )

    alerts_dir = derived / "alerts"
    alerts_dir.mkdir(parents=True)
    alerts_payload = [
        {
            "alert_id": "a-high",
            "market_id": "mkt-high",
            "ts": "2026-02-20T11:00:00Z",
            "severity": "HIGH",
            "reason_codes": ["BAND_BREACH"],
            "evidence": {"p_yes": 0.81},
            "llm_explain_5lines": ["line1", "line2", "line3", "line4", "line5"],
        },
        {
            "alert_id": "a-med",
            "market_id": "mkt-mid",
            "ts": "2026-02-20T10:00:00Z",
            "severity": "MED",
            "reason_codes": ["DRIFT_SPIKE"],
            "evidence": {"drift_z": 2.3},
            "llm_explain_5lines": ["line1", "line2", "line3", "line4", "line5"],
        },
        {
            "alert_id": "a-fyi",
            "market_id": "mkt-none",
            "ts": "2026-02-20T09:00:00Z",
            "severity": "FYI",
            "reason_codes": ["LOW_OI"],
            "evidence": {"open_interest": 5},
            "llm_explain_5lines": ["line1", "line2", "line3", "line4", "line5"],
        },
    ]
    (alerts_dir / "alerts.json").write_text(
        json.dumps(alerts_payload),
        encoding="utf-8",
    )


def test_scoreboard_min_trust_score_filter(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)

    baseline = client.get("/scoreboard", params={"window": "90d"})
    assert baseline.status_code == 200
    assert baseline.json()["total"] == 3

    response = client.get(
        "/scoreboard",
        params={"window": "90d", "min_trust_score": 70.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["market_id"] == "mkt-high"


def test_alerts_severity_filter_is_case_insensitive(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)

    baseline = client.get("/alerts")
    assert baseline.status_code == 200
    assert baseline.json()["total"] == 3

    response = client.get("/alerts", params={"severity": "high"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["alert_id"] == "a-high"
