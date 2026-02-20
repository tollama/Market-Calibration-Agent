from registry.build_registry import build_market_registry
from registry.conflict_rules import (
    CONFLICT_ENABLE_ORDERBOOK_MISMATCH,
    CONFLICT_EVENT_ID_MISMATCH,
    CONFLICT_OUTCOMES_MISMATCH,
    CONFLICT_SLUG_REUSED,
    merge_canonical_records,
)


def _conflict_codes(conflicts):
    return {item["code"] for item in conflicts}


def test_merge_canonical_ids_market_id_priority_with_conflicts():
    existing = {
        "market_id": "m1",
        "event_id": "e1",
        "slug": "old-slug",
        "category_tags": ["Politics"],
        "outcomes": ["Yes", "No"],
        "enableOrderBook": True,
        "status": "ACTIVE",
    }
    incoming = {
        "market_id": "m1",
        "event_id": "e2",
        "slug": "new-slug",
        "category_tags": ["US"],
        "outcomes": ["Up", "Down"],
        "enableOrderBook": False,
        "status": "RESOLVED",
    }

    merged, conflicts = merge_canonical_records(existing, incoming)

    assert merged["market_id"] == "m1"
    assert merged["event_id"] == "e1"
    assert merged["outcomes"] == ["Yes", "No"]
    assert merged["enableOrderBook"] is True
    assert merged["slug"] == "new-slug"
    assert merged["status"] == "RESOLVED"
    assert merged["category_tags"] == ["Politics", "US"]

    assert _conflict_codes(conflicts) == {
        CONFLICT_EVENT_ID_MISMATCH,
        CONFLICT_OUTCOMES_MISMATCH,
        CONFLICT_ENABLE_ORDERBOOK_MISMATCH,
    }


def test_build_market_registry_records_slug_history_on_change():
    existing_registry = [
        {
            "market_id": "m1",
            "event_id": "e1",
            "slug": "old-slug",
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "status": "ACTIVE",
            "category_tags": [],
        }
    ]
    gamma_markets = [
        {
            "id": "m1",
            "eventId": "e1",
            "slug": "new-slug",
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "status": "ACTIVE",
        }
    ]

    result = build_market_registry(
        gamma_markets=gamma_markets,
        existing_registry=existing_registry,
        observed_at="2026-02-20T12:00:00Z",
    )

    assert result.registry_rows == [
        {
            "market_id": "m1",
            "event_id": "e1",
            "slug": "new-slug",
            "category_tags": [],
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "start_ts": "",
            "end_ts": "",
            "status": "ACTIVE",
        }
    ]
    assert result.history_rows == [
        {
            "market_id": "m1",
            "old_slug": "old-slug",
            "new_slug": "new-slug",
            "changed_at": "2026-02-20T12:00:00Z",
            "source": "registry_upsert",
        }
    ]
    assert result.conflict_rows == []


def test_build_market_registry_blocks_slug_takeover():
    existing_registry = [
        {
            "market_id": "m1",
            "event_id": "e1",
            "slug": "shared-slug",
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "status": "ACTIVE",
            "category_tags": [],
        },
        {
            "market_id": "m2",
            "event_id": "e2",
            "slug": "safe-slug",
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "status": "ACTIVE",
            "category_tags": [],
        },
    ]

    gamma_markets = [
        {
            "id": "m2",
            "eventId": "e2",
            "slug": "shared-slug",
            "outcomes": ["Yes", "No"],
            "enableOrderBook": True,
            "status": "ACTIVE",
        }
    ]

    result = build_market_registry(
        gamma_markets=gamma_markets,
        existing_registry=existing_registry,
        observed_at="2026-02-20T12:00:00Z",
    )

    by_market_id = {row["market_id"]: row for row in result.registry_rows}
    assert by_market_id["m1"]["slug"] == "shared-slug"
    assert by_market_id["m2"]["slug"] == "safe-slug"
    assert result.history_rows == []
    assert _conflict_codes(result.conflict_rows) == {CONFLICT_SLUG_REUSED}
