import importlib.util
from pathlib import Path
import sys

_MODULE_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "build_cutoff_snapshots.py"
_SPEC = importlib.util.spec_from_file_location("build_cutoff_snapshots", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

DEFAULT_CUTOFF_TYPES = _MODULE.DEFAULT_CUTOFF_TYPES
DEFAULT_SELECTION_RULE = _MODULE.DEFAULT_SELECTION_RULE
CutoffSnapshot = _MODULE.CutoffSnapshot
build_cutoff_snapshots = _MODULE.build_cutoff_snapshots
stage_build_cutoff_snapshots = _MODULE.stage_build_cutoff_snapshots


class _StageContext:
    def __init__(self, *, market_ids: list[str]) -> None:
        self.state = {"market_ids": market_ids}


def test_build_cutoff_snapshots_selects_nearest_before_per_market_and_cutoff() -> None:
    market_ids = ["MKT-1", "MKT-2"]
    source_rows = [
        {
            "market_id": "MKT-1",
            "cutoff_type": "T-24h",
            "cutoff_ts": "2026-02-20T12:00:00Z",
            "ts": "2026-02-20T11:57:00Z",
        },
        {
            "market_id": "MKT-1",
            "cutoff_type": "T-24h",
            "cutoff_ts": "2026-02-20T12:00:00Z",
            "ts": "2026-02-20T11:59:30Z",
        },
        {
            "market_id": "MKT-1",
            "cutoff_type": "T-24h",
            "cutoff_ts": "2026-02-20T12:00:00Z",
            "ts": "2026-02-20T12:00:05Z",
        },
        {
            "market_id": "MKT-1",
            "cutoff_type": "T-1h",
            "cutoff_ts": "2026-02-20T13:00:00Z",
            "ts": "2026-02-20T12:50:00Z",
        },
        {
            "market_id": "MKT-1",
            "cutoff_type": "T-1h",
            "cutoff_ts": "2026-02-20T13:00:00Z",
            "ts": "2026-02-20T12:59:00Z",
        },
        {
            "market_id": "MKT-2",
            "cutoff_type": "DAILY",
            "cutoff_ts": "2026-02-20T01:00:00Z",
            "ts": "2026-02-20T00:30:00Z",
        },
        {
            "market_id": "MKT-2",
            "cutoff_type": "DAILY",
            "cutoff_ts": "2026-02-20T01:00:00Z",
            "ts": "2026-02-20T00:52:00Z",
        },
    ]

    expected = [
        CutoffSnapshot(
            market_id="MKT-1",
            cutoff_type="T-24h",
            selected_ts="2026-02-20T11:59:30+00:00",
            selection_rule=DEFAULT_SELECTION_RULE,
        ),
        CutoffSnapshot(
            market_id="MKT-1",
            cutoff_type="T-1h",
            selected_ts="2026-02-20T12:59:00+00:00",
            selection_rule=DEFAULT_SELECTION_RULE,
        ),
        CutoffSnapshot(
            market_id="MKT-2",
            cutoff_type="DAILY",
            selected_ts="2026-02-20T00:52:00+00:00",
            selection_rule=DEFAULT_SELECTION_RULE,
        ),
    ]

    baseline = build_cutoff_snapshots(market_ids=market_ids, source_rows=source_rows)
    shuffled = build_cutoff_snapshots(
        market_ids=market_ids, source_rows=list(reversed(source_rows))
    )

    assert baseline == expected
    assert shuffled == expected


def test_build_cutoff_snapshots_skips_cutoffs_without_eligible_candidates() -> None:
    snapshots = build_cutoff_snapshots(
        market_ids=["MKT-3"],
        source_rows=[
            {
                "market_id": "MKT-3",
                "cutoff_type": "T-24h",
                "cutoff_ts": "2026-02-20T09:00:00Z",
                "ts": "2026-02-20T08:44:59Z",
            },
            {
                "market_id": "MKT-3",
                "cutoff_type": "T-1h",
                "cutoff_ts": "2026-02-20T09:00:00Z",
                "ts": "2026-02-20T09:00:05Z",
            },
        ],
    )

    assert snapshots == []


def test_build_cutoff_snapshots_without_source_rows_keeps_placeholder_behavior() -> None:
    market_ids = ["MKT-10", "MKT-11"]

    first = build_cutoff_snapshots(market_ids=market_ids)
    second = build_cutoff_snapshots(market_ids=market_ids)

    assert first == second
    assert len(first) == len(market_ids) * len(DEFAULT_CUTOFF_TYPES)
    assert {(snapshot.market_id, snapshot.cutoff_type) for snapshot in first} == {
        ("MKT-10", "T-24h"),
        ("MKT-10", "T-1h"),
        ("MKT-10", "DAILY"),
        ("MKT-11", "T-24h"),
        ("MKT-11", "T-1h"),
        ("MKT-11", "DAILY"),
    }
    assert {snapshot.selection_rule for snapshot in first} == {DEFAULT_SELECTION_RULE}
    assert len({snapshot.selected_ts for snapshot in first}) == 1


def test_stage_build_cutoff_snapshots_with_market_ids_only_returns_stable_summary() -> None:
    context = _StageContext(market_ids=["MKT-1", "MKT-2"])

    summary = stage_build_cutoff_snapshots(context)

    assert summary == {
        "cutoff_types": list(DEFAULT_CUTOFF_TYPES),
        "snapshot_count": 2 * len(DEFAULT_CUTOFF_TYPES),
    }
    assert len(context.state["cutoff_snapshots"]) == summary["snapshot_count"]
