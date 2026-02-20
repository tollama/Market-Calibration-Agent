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
            "market_id": "mkt-30",
            "window": "30d",
            "trust_score": 61.1,
            "brier": 0.24,
            "logloss": 0.69,
            "ece": 0.11,
            "liquidity_bucket": "LOW",
            "category": "crypto",
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
            "alert_id": "a-1",
            "market_id": "mkt-90",
            "ts": "2026-02-20T11:00:00Z",
            "severity": "HIGH",
            "reason_codes": ["BAND_BREACH"],
            "evidence": {"p_yes": 0.81},
            "llm_explain_5lines": [
                "line1",
                "line2",
                "line3",
                "line4",
                "line5",
            ],
        },
        {
            "alert_id": "a-2",
            "market_id": "mkt-30",
            "ts": "2026-02-19T11:00:00Z",
            "severity": "FYI",
            "reason_codes": ["LOW_OI"],
            "evidence": {"open_interest": 5},
            "llm_explain_5lines": [
                "line1",
                "line2",
                "line3",
                "line4",
                "line5",
            ],
        },
    ]
    (alerts_dir / "alerts.json").write_text(
        json.dumps(alerts_payload),
        encoding="utf-8",
    )

    reports_dir = derived / "reports" / "postmortem"
    reports_dir.mkdir(parents=True)
    (reports_dir / "mkt-90.md").write_text(
        "# Postmortem mkt-90\n\n- summary\n",
        encoding="utf-8",
    )


def test_scoreboard_filters_window_and_tag(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/scoreboard", params={"window": "90d", "tag": "politics"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["market_id"] == "mkt-90"


def test_alerts_since_and_pagination(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get(
        "/alerts",
        params={"since": "2026-02-20T00:00:00Z", "limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["alert_id"] == "a-1"


def test_postmortem_returns_markdown(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/postmortem/mkt-90")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_id"] == "mkt-90"
    assert "Postmortem mkt-90" in payload["content"]


def test_postmortem_returns_404_for_missing_market(monkeypatch, tmp_path):
    _write_fixture_files(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/postmortem/unknown-market")

    assert response.status_code == 404
