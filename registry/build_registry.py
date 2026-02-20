"""Market registry builder/upserter with conflict-aware merge rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .conflict_rules import (
    CONFLICT_MISSING_REQUIRED_FIELD,
    CONFLICT_SLUG_REUSED,
    build_slug_history_row,
    canonicalize_id,
    canonicalize_market_record,
    make_conflict,
    merge_canonical_records,
    missing_required_fields,
    normalize_slug,
    should_record_slug_change,
    utc_now_iso,
)


@dataclass(frozen=True)
class RegistryBuildResult:
    """Output container for registry build/update runs."""

    registry_rows: list[dict[str, Any]]
    history_rows: list[dict[str, Any]]
    conflict_rows: list[dict[str, Any]]


def _index_events(events: Iterable[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Build an event_id -> event payload map."""
    indexed: dict[str, dict[str, Any]] = {}
    if not events:
        return indexed
    for event in events:
        event_id = canonicalize_id(event.get("event_id", event.get("id")))
        if not event_id:
            continue
        indexed[event_id] = {
            "event_id": event_id,
            "category_tags": list(event.get("category_tags", event.get("tags", []))),
            "start_ts": canonicalize_id(event.get("start_ts", event.get("startDate"))),
            "end_ts": canonicalize_id(event.get("end_ts", event.get("endDate"))),
        }
    return indexed


def _enrich_with_event(
    canonical_market: dict[str, Any],
    event_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Add event-level fields when available."""
    event_id = canonical_market.get("event_id", "")
    event = event_index.get(event_id)
    if not event:
        return canonical_market
    enriched = dict(canonical_market)
    if not enriched.get("category_tags"):
        enriched["category_tags"] = list(event.get("category_tags", []))
    if not enriched.get("start_ts"):
        enriched["start_ts"] = canonicalize_id(event.get("start_ts"))
    if not enriched.get("end_ts"):
        enriched["end_ts"] = canonicalize_id(event.get("end_ts"))
    return enriched


def _upsert_slug_owner(
    slug_owner: dict[str, str],
    old_slug: str,
    new_slug: str,
    market_id: str,
) -> None:
    """Refresh current slug owner index."""
    if old_slug and slug_owner.get(old_slug) == market_id:
        del slug_owner[old_slug]
    if new_slug:
        slug_owner[new_slug] = market_id


def build_market_registry(
    gamma_markets: Iterable[Mapping[str, Any]],
    gamma_events: Iterable[Mapping[str, Any]] | None = None,
    existing_registry: Iterable[Mapping[str, Any]] | None = None,
    existing_history: Iterable[Mapping[str, Any]] | None = None,
    observed_at: str | None = None,
) -> RegistryBuildResult:
    """
    Build/update registry rows with canonical-ID merge and slug history tracking.

    Conflict resolution:
    - `market_id` is the canonical key.
    - `event_id`/`outcomes`/`enableOrderBook` mismatches are preserved from existing row.
    - slug changes append history.
    - slug reuse across different market_id is blocked and logged as conflict.
    """
    event_index = _index_events(gamma_events)
    as_of = observed_at or utc_now_iso()

    registry_by_market: dict[str, dict[str, Any]] = {}
    history_rows: list[dict[str, Any]] = [dict(item) for item in (existing_history or [])]
    conflict_rows: list[dict[str, Any]] = []
    slug_owner: dict[str, str] = {}

    for row in existing_registry or []:
        canonical = canonicalize_market_record(row)
        market_id = canonical["market_id"]
        if not market_id:
            continue
        registry_by_market[market_id] = canonical
        slug = normalize_slug(canonical.get("slug"))
        if slug and slug not in slug_owner:
            slug_owner[slug] = market_id

    for raw_market in gamma_markets:
        incoming = _enrich_with_event(canonicalize_market_record(raw_market), event_index)
        market_id = incoming["market_id"]
        missing = missing_required_fields(incoming)
        if missing:
            conflict_rows.append(
                make_conflict(
                    CONFLICT_MISSING_REQUIRED_FIELD,
                    market_id or "<unknown>",
                    field="required_fields",
                    incoming=missing,
                )
            )
            continue

        existing = registry_by_market.get(market_id)
        if not existing:
            slug = normalize_slug(incoming["slug"])
            owner = slug_owner.get(slug)
            if owner and owner != market_id:
                conflict_rows.append(
                    make_conflict(
                        CONFLICT_SLUG_REUSED,
                        market_id,
                        field="slug",
                        incoming=slug,
                        owner_market_id=owner,
                    )
                )
            else:
                slug_owner[slug] = market_id
            registry_by_market[market_id] = incoming
            continue

        previous_slug = normalize_slug(existing.get("slug"))
        merged, merge_conflicts = merge_canonical_records(existing, incoming)
        conflict_rows.extend(merge_conflicts)
        candidate_slug = normalize_slug(merged.get("slug"))

        owner = slug_owner.get(candidate_slug)
        if (
            candidate_slug
            and owner
            and owner != market_id
            and candidate_slug != previous_slug
        ):
            conflict_rows.append(
                make_conflict(
                    CONFLICT_SLUG_REUSED,
                    market_id,
                    field="slug",
                    existing=previous_slug,
                    incoming=candidate_slug,
                    owner_market_id=owner,
                )
            )
            merged["slug"] = previous_slug
            candidate_slug = previous_slug

        if should_record_slug_change(previous_slug, candidate_slug):
            history_rows.append(
                build_slug_history_row(
                    market_id=market_id,
                    old_slug=previous_slug,
                    new_slug=candidate_slug,
                    changed_at=as_of,
                )
            )

        _upsert_slug_owner(slug_owner, previous_slug, candidate_slug, market_id)
        registry_by_market[market_id] = merged

    registry_rows = sorted(registry_by_market.values(), key=lambda row: row["market_id"])
    history_rows = sorted(
        history_rows,
        key=lambda row: (
            canonicalize_id(row.get("changed_at")),
            canonicalize_id(row.get("market_id")),
            canonicalize_id(row.get("old_slug")),
        ),
    )
    conflict_rows = sorted(
        conflict_rows,
        key=lambda row: (
            canonicalize_id(row.get("code")),
            canonicalize_id(row.get("market_id")),
            canonicalize_id(row.get("field")),
        ),
    )
    return RegistryBuildResult(
        registry_rows=registry_rows,
        history_rows=history_rows,
        conflict_rows=conflict_rows,
    )


# Backward-compatible alias some callers may expect.
build_registry = build_market_registry
