import importlib.util
from pathlib import Path
from typing import Optional

import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[2] / "pipelines" / "build_feature_frame.py"
MODULE_SPEC = importlib.util.spec_from_file_location("build_feature_frame", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
build_feature_frame = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(build_feature_frame)

DEFAULT_VOL_WINDOW = build_feature_frame.DEFAULT_VOL_WINDOW
DEFAULT_LIQUIDITY_LOW = build_feature_frame.DEFAULT_LIQUIDITY_LOW
DEFAULT_LIQUIDITY_HIGH = build_feature_frame.DEFAULT_LIQUIDITY_HIGH
stage_build_features = build_feature_frame.stage_build_features


class _Context:
    def __init__(self, state: Optional[dict[str, object]] = None) -> None:
        self.state = {} if state is None else dict(state)


def test_stage_build_features_handles_empty_input() -> None:
    context = _Context(state={"cutoff_snapshot_rows": []})

    summary = stage_build_features(context)

    assert summary["feature_count"] == 0
    assert "feature_frame" in context.state
    assert isinstance(context.state["feature_frame"], pd.DataFrame)
    assert context.state["feature_frame"].empty


def test_stage_build_features_builds_expected_feature_columns() -> None:
    assert DEFAULT_VOL_WINDOW == 5
    assert DEFAULT_LIQUIDITY_LOW == 10_000.0
    assert DEFAULT_LIQUIDITY_HIGH == 100_000.0

    context = _Context(state={"cutoff_snapshots": _default_snapshot_rows()})

    summary = stage_build_features(context)
    feature_frame = context.state["feature_frame"]

    assert summary["feature_count"] == 3
    assert isinstance(feature_frame, pd.DataFrame)
    assert len(feature_frame) == 3
    for required_column in (
        "returns",
        "vol",
        "volume_velocity",
        "oi_change",
        "tte_seconds",
        "liquidity_bucket",
    ):
        assert required_column in feature_frame.columns

    assert feature_frame["liquidity_bucket"].tolist() == ["LOW", "MID", "HIGH"]


def test_stage_build_features_applies_custom_thresholds_from_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "features.yaml"
    config_path.write_text(
        "\n".join(
            [
                "features:",
                "  liquidity_thresholds:",
                "    low: 20000",
                "    high: 120000",
            ]
        ),
        encoding="utf-8",
    )

    context = _Context(
        state={
            "cutoff_snapshots": _default_snapshot_rows(),
            "feature_config_path": str(config_path),
        }
    )

    stage_build_features(context)

    feature_frame = context.state["feature_frame"]
    assert feature_frame["liquidity_bucket"].tolist() == ["LOW", "LOW", "HIGH"]


def test_stage_build_features_boundary_values_follow_low_inclusive_high_inclusive() -> None:
    context = _Context(
        state={
            "cutoff_snapshots": [
                {
                    "market_id": "mkt-a",
                    "ts": "2026-02-20T00:00:00Z",
                    "p_yes": 0.50,
                    "volume_24h": 49.0,
                    "open_interest": 49.0,
                    "end_ts": "2026-02-21T00:00:00Z",
                },
                {
                    "market_id": "mkt-a",
                    "ts": "2026-02-20T00:10:00Z",
                    "p_yes": 0.55,
                    "volume_24h": 50.0,
                    "open_interest": 50.0,
                    "end_ts": "2026-02-21T00:00:00Z",
                },
                {
                    "market_id": "mkt-a",
                    "ts": "2026-02-20T00:20:00Z",
                    "p_yes": 0.56,
                    "volume_24h": 99.0,
                    "open_interest": 99.0,
                    "end_ts": "2026-02-21T00:00:00Z",
                },
                {
                    "market_id": "mkt-a",
                    "ts": "2026-02-20T00:30:00Z",
                    "p_yes": 0.57,
                    "volume_24h": 100.0,
                    "open_interest": 100.0,
                    "end_ts": "2026-02-21T00:00:00Z",
                },
            ],
            "liquidity_low": 50.0,
            "liquidity_high": 100.0,
        }
    )

    stage_build_features(context)

    feature_frame = context.state["feature_frame"]
    assert feature_frame["liquidity_bucket"].tolist() == ["LOW", "MID", "MID", "HIGH"]


def _default_snapshot_rows() -> list[dict[str, object]]:
    return [
        {
            "market_id": "mkt-a",
            "ts": "2026-02-20T00:00:00Z",
            "p_yes": 0.50,
            "volume_24h": 9_000.0,
            "open_interest": 8_000.0,
            "end_ts": "2026-02-21T00:00:00Z",
        },
        {
            "market_id": "mkt-a",
            "ts": "2026-02-20T00:10:00Z",
            "p_yes": 0.55,
            "volume_24h": 12_000.0,
            "open_interest": 15_000.0,
            "end_ts": "2026-02-21T00:00:00Z",
        },
        {
            "market_id": "mkt-b",
            "ts": "2026-02-20T00:00:00Z",
            "p_yes": 0.40,
            "volume_24h": 130_000.0,
            "open_interest": 110_000.0,
            "end_ts": "2026-02-21T00:00:00Z",
        },
    ]
