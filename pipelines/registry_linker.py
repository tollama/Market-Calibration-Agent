"""Link registry metadata into snapshot rows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

_ENRICHMENT_FIELDS = ("event_id", "category_tags", "status", "outcomes")


def _canonical_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _canonical_slug(value: Any) -> str:
    return _canonical_text(value).lower()


def _stable_value_key(value: Any) -> Any:
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: str(item[0]))
        return (
            "mapping",
            tuple((str(key), _stable_value_key(item_value)) for key, item_value in items),
        )
    if isinstance(value, list):
        return ("list", tuple(_stable_value_key(item) for item in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_stable_value_key(item) for item in value))
    if isinstance(value, set):
        normalized_items = sorted(
            (_stable_value_key(item) for item in value),
            key=repr,
        )
        return ("set", tuple(normalized_items))
    if value is None:
        return ("none", "")
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    return ("repr", repr(value))


def _registry_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _canonical_text(row.get("market_id")),
        _canonical_slug(row.get("slug")),
        _stable_value_key(row),
    )


def _snapshot_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _canonical_text(row.get("market_id")),
        _canonical_slug(row.get("slug")),
        _stable_value_key(row),
    )


def _build_registry_indexes(
    registry_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_market_id: dict[str, dict[str, Any]] = {}
    by_slug: dict[str, dict[str, Any]] = {}

    for row in sorted(registry_rows, key=_registry_sort_key):
        market_id = _canonical_text(row.get("market_id"))
        if market_id and market_id not in by_market_id:
            by_market_id[market_id] = row

        slug = _canonical_slug(row.get("slug"))
        if slug and slug not in by_slug:
            by_slug[slug] = row

    return by_market_id, by_slug


def _select_registry_row(
    snapshot_row: Mapping[str, Any],
    *,
    by_market_id: Mapping[str, dict[str, Any]],
    by_slug: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    market_id = _canonical_text(snapshot_row.get("market_id"))
    if market_id:
        return by_market_id.get(market_id)

    slug = _canonical_slug(snapshot_row.get("slug"))
    if not slug:
        return None
    return by_slug.get(slug)


def link_registry_to_snapshots(
    snapshot_rows: list[dict[str, Any]],
    registry_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Enrich snapshot rows with registry metadata.

    Matching precedence:
    1) market_id
    2) slug (only when snapshot market_id is missing/empty)
    """

    by_market_id, by_slug = _build_registry_indexes(registry_rows)
    enriched_rows: list[dict[str, Any]] = []

    for snapshot_row in snapshot_rows:
        enriched_row = deepcopy(snapshot_row)
        registry_row = _select_registry_row(
            snapshot_row,
            by_market_id=by_market_id,
            by_slug=by_slug,
        )

        if registry_row is not None:
            for field in _ENRICHMENT_FIELDS:
                if field in registry_row:
                    enriched_row[field] = deepcopy(registry_row[field])

        enriched_rows.append(enriched_row)

    return sorted(enriched_rows, key=_snapshot_sort_key)
