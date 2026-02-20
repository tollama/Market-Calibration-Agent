from __future__ import annotations

from pathlib import Path

import pytest

from api.dependencies import LocalDerivedStore


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_postmortem_picks_latest_resolved_date_pattern(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    report_dir = derived / "reports" / "postmortem"
    older = report_dir / "mkt-10_2026-02-19.md"
    newer = report_dir / "mkt-10_2026-02-20.md"
    legacy = report_dir / "mkt-10.md"
    _write_markdown(older, "older")
    _write_markdown(newer, "newer")
    _write_markdown(legacy, "legacy")

    store = LocalDerivedStore(derived_root=derived)
    content, path = store.load_postmortem(market_id="mkt-10")

    assert path == newer
    assert path.parent == report_dir
    assert path.name == "mkt-10_2026-02-20.md"
    assert content == "newer"


def test_load_postmortem_falls_back_to_legacy_filename(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    legacy = derived / "reports" / "postmortem" / "mkt-20.md"
    _write_markdown(legacy, "legacy-only")

    store = LocalDerivedStore(derived_root=derived)
    content, path = store.load_postmortem(market_id="mkt-20")

    assert path == legacy
    assert content == "legacy-only"


def test_load_postmortem_ignores_non_date_artifacts_and_uses_legacy(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    report_dir = derived / "reports" / "postmortem"
    invalid = report_dir / "mkt-30_unknown-date.md"
    legacy = report_dir / "mkt-30.md"
    _write_markdown(invalid, "invalid-pattern")
    _write_markdown(legacy, "legacy-fallback")

    store = LocalDerivedStore(derived_root=derived)
    content, path = store.load_postmortem(market_id="mkt-30")

    assert path == legacy
    assert path.name == "mkt-30.md"
    assert content == "legacy-fallback"


def test_load_postmortem_raises_when_no_matching_file(tmp_path: Path) -> None:
    store = LocalDerivedStore(derived_root=tmp_path / "derived")

    with pytest.raises(FileNotFoundError):
        store.load_postmortem(market_id="missing")
