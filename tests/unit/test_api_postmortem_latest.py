from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app


def _write_postmortem_fixtures(tmp_path) -> None:
    reports_dir = tmp_path / "derived" / "reports" / "postmortem"
    reports_dir.mkdir(parents=True)
    (reports_dir / "mkt-90_2026-02-19.md").write_text(
        "# Postmortem mkt-90 old\n",
        encoding="utf-8",
    )
    (reports_dir / "mkt-90_2026-02-20.md").write_text(
        "# Postmortem mkt-90 latest\n",
        encoding="utf-8",
    )
    (reports_dir / "mkt-90_unknown-date.md").write_text(
        "# Postmortem mkt-90 unknown\n",
        encoding="utf-8",
    )
    (reports_dir / "mkt-90.md").write_text(
        "# Postmortem mkt-90 legacy\n",
        encoding="utf-8",
    )


def test_postmortem_returns_latest_resolved_date_artifact(monkeypatch, tmp_path) -> None:
    _write_postmortem_fixtures(tmp_path)
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/postmortem/mkt-90")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_id"] == "mkt-90"
    assert payload["content"] == "# Postmortem mkt-90 latest\n"
    assert Path(payload["source_path"]) == (
        tmp_path / "derived" / "reports" / "postmortem" / "mkt-90_2026-02-20.md"
    )


def test_postmortem_falls_back_to_pattern_file_when_legacy_missing(
    monkeypatch,
    tmp_path,
) -> None:
    reports_dir = tmp_path / "derived" / "reports" / "postmortem"
    reports_dir.mkdir(parents=True)
    expected_path = reports_dir / "mkt-91_unknown-date.md"
    expected_path.write_text(
        "# Postmortem mkt-91 unknown\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/postmortem/mkt-91")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_id"] == "mkt-91"
    assert payload["content"] == "# Postmortem mkt-91 unknown\n"
    assert Path(payload["source_path"]) == expected_path


def test_postmortem_missing_market_keeps_legacy_404_shape(monkeypatch, tmp_path) -> None:
    reports_dir = tmp_path / "derived" / "reports" / "postmortem"
    reports_dir.mkdir(parents=True)
    (reports_dir / "mkt-92_2026-02-20.md").write_text(
        "# Postmortem mkt-92\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DERIVED_DIR", str(tmp_path / "derived"))

    client = TestClient(app)
    response = client.get("/postmortem/unknown-market")

    assert response.status_code == 404
    assert response.json() == {"detail": "Postmortem not found: unknown-market"}
