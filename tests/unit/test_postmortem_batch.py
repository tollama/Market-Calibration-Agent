from __future__ import annotations

from pathlib import Path

import pytest

from pipelines import build_postmortem_batch as postmortem_batch


def test_build_and_write_postmortems_mixed_events_with_stable_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {"market_id": "mkt-20", "title": "Second"},
        {"title": "Missing market id"},
        {"market_id": ""},
        {"market_id": None},
        123,
        {"market_id": "mkt-10", "title": "First"},
    ]

    calls: list[dict[str, object]] = []

    def fake_write_postmortem_markdown(event: dict, *, root: str | Path, market_id: str) -> str:
        calls.append({"event": dict(event), "root": root, "market_id": market_id})
        output_path = Path(root) / "derived" / "reports" / "postmortem" / f"{market_id}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"# {market_id}\n", encoding="utf-8")
        return str(output_path)

    monkeypatch.setattr(
        postmortem_batch,
        "write_postmortem_markdown",
        fake_write_postmortem_markdown,
        raising=True,
    )

    summary = postmortem_batch.build_and_write_postmortems(events, root=tmp_path)

    expected_paths = [
        str(tmp_path / "derived" / "reports" / "postmortem" / "mkt-10.md"),
        str(tmp_path / "derived" / "reports" / "postmortem" / "mkt-20.md"),
    ]

    assert [call["market_id"] for call in calls] == ["mkt-20", "mkt-10"]
    assert all(call["root"] == tmp_path for call in calls)
    assert summary == {
        "written_count": 2,
        "skipped_count": 4,
        "output_paths": expected_paths,
    }
    assert all(Path(path).exists() for path in expected_paths)
