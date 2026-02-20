from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

_TITLE_PLACEHOLDER = "Untitled Incident"
_SUMMARY_PLACEHOLDER = "No incident summary provided."
_TIMELINE_PLACEHOLDER = "No timeline details provided."
_EVIDENCE_PLACEHOLDER = "No supporting evidence provided."
_CALIBRATION_IMPACT_PLACEHOLDER = "No calibration impact provided."
_ACTION_ITEMS_PLACEHOLDER = "No action items provided."


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, Mapping):
        return len(value) == 0
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    return False


def _first_present(event: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        candidate = event.get(key)
        if not _is_missing(candidate):
            return candidate
    return None


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_for_json(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, set):
        normalized = [_normalize_for_json(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    return value


def _format_inline(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if _is_missing(value):
        return ""
    if isinstance(value, (Mapping, list, tuple, set)):
        normalized = _normalize_for_json(value)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_paragraph(value: Any, placeholder: str) -> str:
    rendered = _format_inline(value)
    return rendered if rendered else placeholder


def _render_bullets(value: Any, placeholder: str) -> list[str]:
    if _is_missing(value):
        return [f"- {placeholder}"]

    if isinstance(value, Mapping):
        lines: list[str] = []
        for key in sorted(value, key=lambda item: str(item)):
            rendered = _format_inline(value[key]) or "N/A"
            lines.append(f"- {key}: {rendered}")
        return lines or [f"- {placeholder}"]

    if isinstance(value, set):
        iterable = sorted(value, key=lambda item: _format_inline(item))
    elif isinstance(value, (list, tuple)):
        iterable = value
    else:
        rendered = _format_inline(value)
        return [f"- {rendered if rendered else placeholder}"]

    lines = []
    for item in iterable:
        rendered = _format_inline(item)
        if rendered:
            lines.append(f"- {rendered}")
    return lines or [f"- {placeholder}"]


def build_postmortem_markdown(event: dict) -> str:
    payload = event if isinstance(event, Mapping) else {}

    title_value = _first_present(payload, "title", "incident_title", "market_title")
    if title_value is None:
        market_id_value = _first_present(payload, "market_id")
        if market_id_value is not None:
            title_value = f"Postmortem {_format_inline(market_id_value)}"

    summary_value = _first_present(payload, "incident_summary", "summary")
    timeline_value = _first_present(payload, "timeline")
    evidence_value = _first_present(payload, "evidence")
    calibration_impact_value = _first_present(
        payload,
        "calibration_impact",
        "impact",
    )
    action_items_value = _first_present(payload, "action_items", "remediation_items")

    lines = [
        "# Title",
        _render_paragraph(title_value, _TITLE_PLACEHOLDER),
        "",
        "## Incident Summary",
        _render_paragraph(summary_value, _SUMMARY_PLACEHOLDER),
        "",
        "## Timeline",
        *_render_bullets(timeline_value, _TIMELINE_PLACEHOLDER),
        "",
        "## Evidence",
        *_render_bullets(evidence_value, _EVIDENCE_PLACEHOLDER),
        "",
        "## Calibration Impact",
        _render_paragraph(calibration_impact_value, _CALIBRATION_IMPACT_PLACEHOLDER),
        "",
        "## Action Items",
        *_render_bullets(action_items_value, _ACTION_ITEMS_PLACEHOLDER),
        "",
    ]
    return "\n".join(lines)


def write_postmortem_markdown(event: dict, *, root: str | Path, market_id: str) -> str:
    output_path = Path(root) / "derived" / "reports" / "postmortem" / f"{market_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_postmortem_markdown(event), encoding="utf-8")
    return str(output_path)
