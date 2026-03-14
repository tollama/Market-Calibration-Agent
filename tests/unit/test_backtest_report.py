from pathlib import Path

import pandas as pd

from pipelines.generate_backtest_report import (
    WalkForwardConfig,
    build_walk_forward_splits,
    generate_backtest_report,
)


def _sample_backtest_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_id": "m1",
                "event_id": "e1",
                "ts": "2026-01-01T00:00:00Z",
                "resolution_ts": "2026-01-01T06:00:00Z",
                "label": 1,
                "p_yes": 0.55,
                "pred": 0.62,
                "baseline_pred": 0.58,
                "category": "politics",
                "liquidity_bucket": "MID",
            },
            {
                "market_id": "m2",
                "event_id": "e2",
                "ts": "2026-01-01T02:00:00Z",
                "resolution_ts": "2026-01-01T08:00:00Z",
                "label": 0,
                "p_yes": 0.47,
                "pred": 0.41,
                "baseline_pred": 0.45,
                "category": "sports",
                "liquidity_bucket": "LOW",
            },
            {
                "market_id": "m3",
                "event_id": "e3",
                "ts": "2026-01-01T04:00:00Z",
                "resolution_ts": "2026-01-01T10:00:00Z",
                "label": 1,
                "p_yes": 0.51,
                "pred": 0.68,
                "baseline_pred": 0.56,
                "category": "politics",
                "liquidity_bucket": "HIGH",
            },
            {
                "market_id": "m4",
                "event_id": "e4",
                "ts": "2026-01-01T06:00:00Z",
                "resolution_ts": "2026-01-01T12:00:00Z",
                "label": 0,
                "p_yes": 0.52,
                "pred": 0.36,
                "baseline_pred": 0.48,
                "category": "sports",
                "liquidity_bucket": "MID",
            },
            {
                "market_id": "m5",
                "event_id": "e5",
                "ts": "2026-01-01T08:00:00Z",
                "resolution_ts": "2026-01-01T14:00:00Z",
                "label": 1,
                "p_yes": 0.57,
                "pred": 0.73,
                "baseline_pred": 0.60,
                "category": "finance",
                "liquidity_bucket": "HIGH",
            },
            {
                "market_id": "m6",
                "event_id": "e6",
                "ts": "2026-01-01T10:00:00Z",
                "resolution_ts": "2026-01-01T16:00:00Z",
                "label": 0,
                "p_yes": 0.43,
                "pred": 0.34,
                "baseline_pred": 0.40,
                "category": "finance",
                "liquidity_bucket": "LOW",
            },
        ]
    )


def test_build_walk_forward_splits_respects_label_availability_cutoff() -> None:
    frame = _sample_backtest_rows()
    splits = build_walk_forward_splits(
        frame,
        WalkForwardConfig(
            n_splits=2,
            initial_train_fraction=0.34,
            min_train_rows=2,
            min_test_rows=1,
        ),
    )

    assert len(splits) == 2
    for split in splits:
        test_start = pd.Timestamp(split.test_start_at)
        train_cutoff = pd.Timestamp(split.train_cutoff_at)
        assert train_cutoff <= test_start


def test_generate_backtest_report_writes_expected_artifacts(tmp_path: Path) -> None:
    summary = generate_backtest_report(
        _sample_backtest_rows(),
        report_dir=tmp_path,
        walk_forward=WalkForwardConfig(
            n_splits=2,
            initial_train_fraction=0.34,
            min_train_rows=2,
            min_test_rows=1,
        ),
    )

    assert summary["row_count"] == 6
    assert summary["walk_forward_enabled"] is True
    assert (tmp_path / "overall_summary.csv").exists()
    assert (tmp_path / "group_metrics.csv").exists()
    assert (tmp_path / "predictions.csv").exists()
    assert (tmp_path / "walk_forward_overall_summary.csv").exists()
    assert (tmp_path / "walk_forward_fold_summary.csv").exists()
    assert (tmp_path / "walk_forward_predictions.csv").exists()
    assert (tmp_path / "summary.md").exists()

    overall = pd.read_csv(tmp_path / "overall_summary.csv")
    assert set(overall["model_variant"]) == {"baseline", "market", "primary"}
    assert set(overall.columns) >= {"brier", "log_loss", "ece", "accuracy", "avg_pnl"}

