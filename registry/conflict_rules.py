"""Conflict and merge helpers for market registry upserts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

REQUIRED_REGISTRY_FIELDS = {
    "market_id",
    "event_id",
    "slug",
    "outcomes",
    "enableOrderBook",
    "status",
}

CONFLICT_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
CONFLICT_MARKET_ID_MISMATCH = "MARKET_ID_MISMATCH"
CONFLICT_EVENT_ID_MISMATCH = "EVENT_ID_MISMATCH"
CONFLICT_OUTCOMES_MISMATCH = "OUTCOMES_MISMATCH"
CONFLICT_ENABLE_ORDERBOOK_MISMATCH = "ENABLE_ORDERBOOK_MISMATCH"
CONFLICT_SLUG_REUSED = "SLUG_REUSED"

ALLOWED_STATUS = {"ACTIVE", "RESOLVED", "VOID", "UNRESOLVED"}
STATUS_PRIORITY = {
    "ACTIVE": 1,
    "RESOLVED": 2,
    "VOID": 3,
    "UNRESOLVED": 3,
}


def canonicalize_id(value: Any) -> str:
    """Return a canonical string id."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_slug(value: Any) -> str:
    """Return a normalized slug for deterministic comparisons."""
    return canonicalize_id(value).lower()


def normalize_outcomes(value: Any) -> list[str]:
    """Normalize outcome values to a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Iterable):
        cleaned: list[str] = []
        for item in value:
            item_str = canonicalize_id(item)
            if item_str:
                cleaned.append(item_str)
        return cleaned
    text = canonicalize_id(value)
    return [text] if text else []


def normalize_bool(value: Any) -> bool:
    """Normalize common truthy/falsy values into a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return bool(value)


def normalize_status(value: Any) -> str:
    """Normalize status to one of the allowed enum values."""
    status = canonicalize_id(value).upper()
    if status in ALLOWED_STATUS:
        return status
    return "ACTIVE"


def canonicalize_market_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize a registry record shape and value types."""
    return {
        "market_id": canonicalize_id(
            record.get("market_id", record.get("marketId", record.get("id")))
        ),
        "event_id": canonicalize_id(record.get("event_id", record.get("eventId"))),
        "slug": normalize_slug(record.get("slug")),
        "category_tags": list(record.get("category_tags", record.get("categoryTags", []))),
        "outcomes": normalize_outcomes(record.get("outcomes")),
        "enableOrderBook": normalize_bool(
            record.get("enableOrderBook", record.get("enable_order_book"))
        ),
        "start_ts": canonicalize_id(record.get("start_ts", record.get("startDate"))),
        "end_ts": canonicalize_id(record.get("end_ts", record.get("endDate"))),
        "status": normalize_status(record.get("status")),
    }


def missing_required_fields(record: Mapping[str, Any]) -> list[str]:
    """Return required field names missing from the canonical record."""
    missing: list[str] = []
    for field in REQUIRED_REGISTRY_FIELDS:
        value = record.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value:
            missing.append(field)
            continue
        if isinstance(value, list) and not value:
            missing.append(field)
    return sorted(missing)


def make_conflict(
    code: str,
    market_id: str,
    field: str | None = None,
    existing: Any = None,
    incoming: Any = None,
    **details: Any,
) -> dict[str, Any]:
    """Create a structured conflict event."""
    payload: dict[str, Any] = {"code": code, "market_id": market_id}
    if field is not None:
        payload["field"] = field
    if existing is not None:
        payload["existing"] = existing
    if incoming is not None:
        payload["incoming"] = incoming
    payload.update(details)
    return payload


def _pick_status(existing: str, incoming: str) -> str:
    """Pick the status with higher finality precedence."""
    if STATUS_PRIORITY.get(incoming, 0) >= STATUS_PRIORITY.get(existing, 0):
        return incoming
    return existing


def _pick_start_ts(existing: str, incoming: str) -> str:
    """Prefer the earliest start timestamp if both exist."""
    if not existing:
        return incoming
    if not incoming:
        return existing
    return min(existing, incoming)


def _pick_end_ts(existing: str, incoming: str) -> str:
    """Prefer the latest end timestamp if both exist."""
    if not existing:
        return incoming
    if not incoming:
        return existing
    return max(existing, incoming)


def _merge_tags(existing: list[str], incoming: list[str]) -> list[str]:
    """Union category tags with deterministic ordering."""
    merged = {canonicalize_id(tag) for tag in existing if canonicalize_id(tag)}
    merged.update(canonicalize_id(tag) for tag in incoming if canonicalize_id(tag))
    return sorted(merged)


def merge_canonical_records(
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Merge two canonical records keyed by market_id.

    Rules:
    - market_id is canonical and immutable.
    - event_id/outcomes/enableOrderBook keep existing values on mismatch (emit conflict).
    - slug and status can evolve (slug history is handled by caller).
    """
    left = canonicalize_market_record(existing)
    right = canonicalize_market_record(incoming)
    conflicts: list[dict[str, Any]] = []

    if left["market_id"] != right["market_id"]:
        conflicts.append(
            make_conflict(
                CONFLICT_MARKET_ID_MISMATCH,
                left["market_id"] or right["market_id"],
                field="market_id",
                existing=left["market_id"],
                incoming=right["market_id"],
            )
        )
        return left, conflicts

    market_id = left["market_id"]
    merged = dict(left)

    if right["event_id"] and left["event_id"] and right["event_id"] != left["event_id"]:
        conflicts.append(
            make_conflict(
                CONFLICT_EVENT_ID_MISMATCH,
                market_id,
                field="event_id",
                existing=left["event_id"],
                incoming=right["event_id"],
            )
        )
    elif right["event_id"]:
        merged["event_id"] = right["event_id"]

    if right["outcomes"] and left["outcomes"] and right["outcomes"] != left["outcomes"]:
        conflicts.append(
            make_conflict(
                CONFLICT_OUTCOMES_MISMATCH,
                market_id,
                field="outcomes",
                existing=left["outcomes"],
                incoming=right["outcomes"],
            )
        )
    elif right["outcomes"]:
        merged["outcomes"] = right["outcomes"]

    if right["enableOrderBook"] != left["enableOrderBook"]:
        conflicts.append(
            make_conflict(
                CONFLICT_ENABLE_ORDERBOOK_MISMATCH,
                market_id,
                field="enableOrderBook",
                existing=left["enableOrderBook"],
                incoming=right["enableOrderBook"],
            )
        )

    if right["slug"]:
        merged["slug"] = right["slug"]
    merged["status"] = _pick_status(left["status"], right["status"])
    merged["start_ts"] = _pick_start_ts(left["start_ts"], right["start_ts"])
    merged["end_ts"] = _pick_end_ts(left["end_ts"], right["end_ts"])
    merged["category_tags"] = _merge_tags(
        list(left.get("category_tags", [])),
        list(right.get("category_tags", [])),
    )
    return merged, conflicts


def should_record_slug_change(previous_slug: str, current_slug: str) -> bool:
    """Whether a slug update should be appended to slug history."""
    return bool(previous_slug and current_slug and previous_slug != current_slug)


def build_slug_history_row(
    market_id: str,
    old_slug: str,
    new_slug: str,
    changed_at: str,
    source: str = "registry_upsert",
) -> dict[str, Any]:
    """Build a canonical slug history record."""
    return {
        "market_id": market_id,
        "old_slug": old_slug,
        "new_slug": new_slug,
        "changed_at": changed_at,
        "source": source,
    }


def utc_now_iso() -> str:
    """UTC timestamp in stable ISO format."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# Backward-compatible aliases that may be imported by downstream modules.
merge_canonical_ids = merge_canonical_records
