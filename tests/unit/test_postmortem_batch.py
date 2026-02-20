from __future__ import annotations

from pathlib import Path

import pytest

from pipelines import build_postmortem_batch as postmortem_batch


def test_build_and_write_postmortems_mixed_events_with_stable_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {"market_id": "mkt-20", "title": "Second", "resolved_date": "2026-02-20"},
        {"title": "Missing market id"},
        {"market_id": ""},
        {"market_id": None},
        123,
        {"market_id": "mkt-10", "title": "First", "resolved_at": "2026-02-19T03:00:00Z"},
        {"market_id": "mkt-30", "title": "Third"},
    ]

    calls: list[dict[str, object]] = []

    def _resolved_date_for_test(event: dict) -> str:
        resolved_date = event.get("resolved_date")
        if isinstance(resolved_date, str) and resolved_date.strip():
            return resolved_date.strip()[:10]

        resolved_at = event.get("resolved_at")
        if isinstance(resolved_at, dict):
            nested_date = resolved_at.get("date")
            if isinstance(nested_date, str) and nested_date.strip():
                return nested_date.strip()[:10]

        if isinstance(resolved_at, str) and resolved_at.strip():
            return resolved_at.strip()[:10]

        date_value = event.get("date")
        if isinstance(date_value, str) and date_value.strip():
            return date_value.strip()[:10]

        return "unknown-date"

    def fake_write_postmortem_markdown(event: dict, *, root: str | Path, market_id: str) -> str:
        calls.append({"event": dict(event), "root": root, "market_id": market_id})
        output_path = (
            Path(root)
            / "derived"
            / "reports"
            / "postmortem"
            / f"{market_id}_{_resolved_date_for_test(event)}.md"
        )
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
        str(tmp_path / "derived" / "reports" / "postmortem" / "mkt-10_2026-02-19.md"),
        str(tmp_path / "derived" / "reports" / "postmortem" / "mkt-20_2026-02-20.md"),
        str(tmp_path / "derived" / "reports" / "postmortem" / "mkt-30_unknown-date.md"),
    ]

    assert [call["market_id"] for call in calls] == ["mkt-20", "mkt-10", "mkt-30"]
    assert all(call["root"] == tmp_path for call in calls)
    assert summary == {
        "written_count": 3,
        "skipped_count": 4,
        "output_paths": expected_paths,
    }
    assert all(Path(path).exists() for path in expected_paths)
