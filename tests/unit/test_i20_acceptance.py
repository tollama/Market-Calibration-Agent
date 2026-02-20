from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import LocalDerivedStore


def _write_postmortem(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_dated_postmortems(reports_dir: Path) -> None:
    _write_postmortem(reports_dir / "mkt-42_2026-02-18.md", "# mkt-42 old\n")
    _write_postmortem(reports_dir / "mkt-42_2026-02-19.md", "# mkt-42 middle\n")
    _write_postmortem(reports_dir / "mkt-42_2026-02-20.md", "# mkt-42 latest\n")
    _write_postmortem(reports_dir / "other_2026-02-21.md", "# other market\n")


def test_i20_loader_selects_latest_dated_postmortem(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    reports_dir = derived / "reports" / "postmortem"
    _write_dated_postmortems(reports_dir)

    store = LocalDerivedStore(derived_root=derived)
    first = store.load_postmortem(market_id="mkt-42")
    second = store.load_postmortem(market_id="mkt-42")

    assert first == second
    content, source_path = first
    assert "latest" in content.lower()
    assert source_path.name == "mkt-42_2026-02-20.md"


def test_i20_api_returns_latest_dated_postmortem_deterministically(
    monkeypatch,
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    reports_dir = derived / "reports" / "postmortem"
    _write_dated_postmortems(reports_dir)
    monkeypatch.setenv("DERIVED_DIR", str(derived))

    client = TestClient(app)
    first = client.get("/postmortem/mkt-42")
    second = client.get("/postmortem/mkt-42")

    assert first.status_code == 200
    assert second.status_code == 200

    payload = first.json()
    assert payload == second.json()
    assert payload["market_id"] == "mkt-42"
    assert "latest" in payload["content"].lower()
    assert Path(payload["source_path"]).name == "mkt-42_2026-02-20.md"

