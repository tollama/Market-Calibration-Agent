from pathlib import Path

import pytest

from reports.postmortem import build_postmortem_markdown, write_postmortem_markdown


def test_build_postmortem_markdown_is_deterministic() -> None:
    event = {
        "title": "Postmortem mkt-42",
        "incident_summary": "Band breach persisted for three hours.",
        "timeline": [
            "2026-02-19T09:00:00Z alert triggered",
            {"ts": "2026-02-19T10:15:00Z", "event": "triage started"},
        ],
        "evidence": {"z_score": 2.4, "p_yes": 0.81},
        "calibration_impact": "Trust score dropped from 72.1 to 64.0.",
        "action_items": ["Tune fallback priors", "Add drift monitor"],
    }

    expected = "\n".join(
        [
            "# Title",
            "Postmortem mkt-42",
            "",
            "## Incident Summary",
            "Band breach persisted for three hours.",
            "",
            "## Timeline",
            "- 2026-02-19T09:00:00Z alert triggered",
            '- {"event": "triage started", "ts": "2026-02-19T10:15:00Z"}',
            "",
            "## Evidence",
            "- p_yes: 0.81",
            "- z_score: 2.4",
            "",
            "## Calibration Impact",
            "Trust score dropped from 72.1 to 64.0.",
            "",
            "## Action Items",
            "- Tune fallback priors",
            "- Add drift monitor",
            "",
        ]
    )

    first = build_postmortem_markdown(event)
    second = build_postmortem_markdown(event)

    assert first == expected
    assert second == expected


def test_build_postmortem_markdown_uses_placeholders_when_fields_missing() -> None:
    expected = "\n".join(
        [
            "# Title",
            "Untitled Incident",
            "",
            "## Incident Summary",
            "No incident summary provided.",
            "",
            "## Timeline",
            "- No timeline details provided.",
            "",
            "## Evidence",
            "- No supporting evidence provided.",
            "",
            "## Calibration Impact",
            "No calibration impact provided.",
            "",
            "## Action Items",
            "- No action items provided.",
            "",
        ]
    )

    assert build_postmortem_markdown({}) == expected


def test_write_postmortem_markdown_writes_file_and_returns_path(tmp_path: Path) -> None:
    event = {
        "title": "Postmortem mkt-90",
        "incident_summary": "Summary text.",
        "timeline": ["2026-02-20T10:00:00Z alert fired"],
        "resolved_date": "2026-02-20",
    }

    path = write_postmortem_markdown(event, root=tmp_path, market_id="mkt-90")
    expected_path = (
        tmp_path / "derived" / "reports" / "postmortem" / "mkt-90_2026-02-20.md"
    )

    assert path == str(expected_path)
    assert expected_path.exists()
    assert expected_path.read_text(encoding="utf-8") == build_postmortem_markdown(event)


@pytest.mark.parametrize(
    ("event", "expected_filename"),
    [
        (
            {
                "resolved_date": "2026-02-21",
                "resolved_at": "2026-02-20T12:00:00Z",
                "date": "2026-02-19",
            },
            "mkt-1_2026-02-21.md",
        ),
        (
            {
                "resolved_at": "2026-02-20T12:00:00Z",
                "date": "2026-02-19",
            },
            "mkt-1_2026-02-20.md",
        ),
        (
            {
                "resolved_at": {"date": "2026-02-18"},
                "date": "2026-02-19",
            },
            "mkt-1_2026-02-18.md",
        ),
        (
            {
                "date": "2026-02-19",
            },
            "mkt-1_2026-02-19.md",
        ),
        ({}, "mkt-1_unknown-date.md"),
    ],
)
def test_write_postmortem_markdown_resolved_date_priority(
    tmp_path: Path, event: dict, expected_filename: str
) -> None:
    path = write_postmortem_markdown(event, root=tmp_path, market_id="mkt-1")

    expected_path = tmp_path / "derived" / "reports" / "postmortem" / expected_filename
    assert path == str(expected_path)
    assert expected_path.exists()
