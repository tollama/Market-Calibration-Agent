import copy
import importlib.util
from pathlib import Path
import sys

_MODULE_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "registry_linker.py"
_SPEC = importlib.util.spec_from_file_location("registry_linker", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

link_registry_to_snapshots = _MODULE.link_registry_to_snapshots


def test_link_registry_to_snapshots_matches_by_market_id_before_slug() -> None:
    snapshot_rows = [
        {
            "market_id": "mkt-1",
            "slug": "shared-slug",
            "selected_ts": "2026-02-20T12:00:00Z",
            "snapshot_only": "keep-me",
            "event_id": "snapshot-event",
        }
    ]
    registry_rows = [
        {
            "market_id": "mkt-2",
            "slug": "shared-slug",
            "event_id": "event-from-slug",
            "category_tags": ["Sports"],
            "status": "RESOLVED",
            "outcomes": ["Up", "Down"],
        },
        {
            "market_id": "mkt-1",
            "slug": "different-slug",
            "event_id": "event-from-id",
            "category_tags": ["Politics"],
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        },
    ]

    rows = link_registry_to_snapshots(snapshot_rows, registry_rows)

    assert rows == [
        {
            "market_id": "mkt-1",
            "slug": "shared-slug",
            "selected_ts": "2026-02-20T12:00:00Z",
            "snapshot_only": "keep-me",
            "event_id": "event-from-id",
            "category_tags": ["Politics"],
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        }
    ]


def test_link_registry_to_snapshots_falls_back_to_slug_when_market_id_missing() -> None:
    snapshot_rows = [
        {
            "slug": "Election-2026",
            "selected_ts": "2026-02-20T09:00:00Z",
            "cutoff_type": "T-24h",
        }
    ]
    registry_rows = [
        {
            "market_id": "mkt-election",
            "slug": "election-2026",
            "event_id": "event-election",
            "category_tags": ["Politics", "US"],
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        }
    ]

    rows = link_registry_to_snapshots(snapshot_rows, registry_rows)

    assert rows == [
        {
            "slug": "Election-2026",
            "selected_ts": "2026-02-20T09:00:00Z",
            "cutoff_type": "T-24h",
            "event_id": "event-election",
            "category_tags": ["Politics", "US"],
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        }
    ]


def test_link_registry_to_snapshots_missing_registry_passthrough_deterministic_and_pure() -> None:
    snapshot_rows = [
        {"market_id": "mkt-2", "slug": "slug-2", "feature": 2},
        {"market_id": "mkt-1", "slug": "slug-1", "feature": 1},
        {
            "market_id": "mkt-missing",
            "slug": "slug-missing",
            "feature": 999,
            "event_id": "keep-existing",
        },
    ]
    registry_rows = [
        {
            "market_id": "mkt-1",
            "slug": "slug-1",
            "event_id": "event-1",
            "category_tags": ["Macro"],
            "status": "ACTIVE",
            "outcomes": ["Yes", "No"],
        },
        {
            "market_id": "mkt-2",
            "slug": "slug-2",
            "event_id": "event-2",
            "category_tags": ["Sports"],
            "status": "RESOLVED",
            "outcomes": ["A", "B"],
        },
    ]

    snapshot_rows_original = copy.deepcopy(snapshot_rows)
    registry_rows_original = copy.deepcopy(registry_rows)

    baseline = link_registry_to_snapshots(snapshot_rows, registry_rows)
    shuffled = link_registry_to_snapshots(
        list(reversed(snapshot_rows)),
        list(reversed(registry_rows)),
    )

    assert baseline == shuffled
    assert snapshot_rows == snapshot_rows_original
    assert registry_rows == registry_rows_original

    by_market_id = {row["market_id"]: row for row in baseline}
    assert by_market_id["mkt-missing"] == {
        "market_id": "mkt-missing",
        "slug": "slug-missing",
        "feature": 999,
        "event_id": "keep-existing",
    }
    assert by_market_id["mkt-1"]["outcomes"] == ["Yes", "No"]
    assert by_market_id["mkt-1"]["outcomes"] is not registry_rows[0]["outcomes"]
