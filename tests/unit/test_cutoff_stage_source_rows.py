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
DEFAULT_PLACEHOLDER_SELECTED_TS = _MODULE._DEFAULT_PLACEHOLDER_SELECTED_TS
stage_build_cutoff_snapshots = _MODULE.stage_build_cutoff_snapshots


class _StageContext:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = dict(state)


def test_stage_build_cutoff_snapshots_uses_snapshot_rows_with_derived_cutoffs() -> None:
    context = _StageContext(
        state={
            "market_ids": ["MKT-1"],
            "snapshot_rows": [
                {
                    "market_id": "MKT-1",
                    "ts": "2026-02-19T11:58:00Z",
                    "end_ts": "2026-02-20T12:00:00Z",
                },
                {
                    "market_id": "MKT-1",
                    "ts": "2026-02-20T10:58:30Z",
                    "end_ts": "2026-02-20T12:00:00Z",
                },
                {
                    "market_id": "MKT-1",
                    "ts": "2026-02-20T11:59:10Z",
                    "end_ts": "2026-02-20T12:00:00Z",
                },
            ],
        }
    )

    summary = stage_build_cutoff_snapshots(context)

    assert summary == {
        "cutoff_types": list(DEFAULT_CUTOFF_TYPES),
        "snapshot_count": len(DEFAULT_CUTOFF_TYPES),
    }
    snapshots = context.state["cutoff_snapshots"]
    assert len(snapshots) == len(DEFAULT_CUTOFF_TYPES)
    assert {snapshot.selection_rule for snapshot in snapshots} == {DEFAULT_SELECTION_RULE}
    assert {
        (snapshot.market_id, snapshot.cutoff_type): snapshot.selected_ts for snapshot in snapshots
    } == {
        ("MKT-1", "T-24h"): "2026-02-19T11:58:00+00:00",
        ("MKT-1", "T-1h"): "2026-02-20T10:58:30+00:00",
        ("MKT-1", "DAILY"): "2026-02-20T11:59:10+00:00",
    }


def test_stage_build_cutoff_snapshots_uses_normalized_records_when_snapshot_rows_missing() -> None:
    context = _StageContext(
        state={
            "normalized_records": [
                {
                    "market_id": "MKT-2",
                    "ts": "2026-02-28T05:59:40Z",
                    "event_end_ts": "2026-03-01T06:00:00Z",
                },
                {
                    "market_id": "MKT-2",
                    "ts": "2026-03-01T04:59:30Z",
                    "event_end_ts": "2026-03-01T06:00:00Z",
                },
                {
                    "market_id": "MKT-2",
                    "ts": "2026-03-01T05:59:10Z",
                    "event_end_ts": "2026-03-01T06:00:00Z",
                },
            ]
        }
    )

    summary = stage_build_cutoff_snapshots(context)

    assert summary == {
        "cutoff_types": list(DEFAULT_CUTOFF_TYPES),
        "snapshot_count": len(DEFAULT_CUTOFF_TYPES),
    }
    snapshots = context.state["cutoff_snapshots"]
    assert len(snapshots) == len(DEFAULT_CUTOFF_TYPES)
    assert {
        (snapshot.market_id, snapshot.cutoff_type): snapshot.selected_ts for snapshot in snapshots
    } == {
        ("MKT-2", "T-24h"): "2026-02-28T05:59:40+00:00",
        ("MKT-2", "T-1h"): "2026-03-01T04:59:30+00:00",
        ("MKT-2", "DAILY"): "2026-03-01T05:59:10+00:00",
    }


def test_stage_build_cutoff_snapshots_falls_back_to_placeholders_without_usable_rows() -> None:
    context = _StageContext(
        state={
            "market_ids": ["MKT-9"],
            "snapshot_rows": [
                {
                    "market_id": "MKT-9",
                    "ts": "2026-03-02T00:00:00Z",
                }
            ],
            "normalized_records": [
                {
                    "market_id": "MKT-9",
                    "end_ts": "2026-03-02T12:00:00Z",
                }
            ],
        }
    )

    summary = stage_build_cutoff_snapshots(context)

    assert summary == {
        "cutoff_types": list(DEFAULT_CUTOFF_TYPES),
        "snapshot_count": len(DEFAULT_CUTOFF_TYPES),
    }
    snapshots = context.state["cutoff_snapshots"]
    assert len(snapshots) == len(DEFAULT_CUTOFF_TYPES)
    assert {snapshot.cutoff_type for snapshot in snapshots} == set(DEFAULT_CUTOFF_TYPES)
    assert {snapshot.selection_rule for snapshot in snapshots} == {DEFAULT_SELECTION_RULE}
    assert {snapshot.selected_ts for snapshot in snapshots} == {DEFAULT_PLACEHOLDER_SELECTED_TS}
