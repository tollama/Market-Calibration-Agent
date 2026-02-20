from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipelines.evaluate_tsfm_offline import run


def _build_fixture(path: Path) -> None:
    rows = []
    ts = pd.date_range("2026-02-01", periods=40, freq="5min", tz="UTC")
    events = ["evt-a", "evt-b", "evt-c", "evt-d"]
    categories = {"evt-a": "politics", "evt-b": "sports", "evt-c": "crypto", "evt-d": "macro"}
    for idx, t in enumerate(ts):
        event_id = events[idx % len(events)]
        base = 0.35 + 0.002 * idx
        actual = min(0.95, max(0.05, base))
        rows.append(
            {
                "market_id": f"m-{idx % 3}",
                "event_id": event_id,
                "category": categories[event_id],
                "ts": t.isoformat(),
                "actual": actual,
                "baseline_q05": max(0.0, actual - 0.18),
                "baseline_q10": max(0.0, actual - 0.12),
                "baseline_q50": actual,
                "baseline_q90": min(1.0, actual + 0.12),
                "baseline_q95": min(1.0, actual + 0.18),
                "tsfm_raw_q05": max(0.0, actual - 0.15),
                "tsfm_raw_q10": max(0.0, actual - 0.10),
                "tsfm_raw_q50": actual,
                "tsfm_raw_q90": min(1.0, actual + 0.10),
                "tsfm_raw_q95": min(1.0, actual + 0.15),
                "tsfm_conformal_q05": max(0.0, actual - 0.17),
                "tsfm_conformal_q10": max(0.0, actual - 0.11),
                "tsfm_conformal_q50": actual,
                "tsfm_conformal_q90": min(1.0, actual + 0.11),
                "tsfm_conformal_q95": min(1.0, actual + 0.17),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_event_holdout_pipeline_generates_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "offline_eval_input.csv"
    output_dir = tmp_path / "artifacts"
    _build_fixture(input_path)

    summary = run(
        input_path=input_path,
        output_dir=output_dir,
        model_prefixes=["baseline", "tsfm_raw", "tsfm_conformal"],
        validation_ratio=0.2,
        holdout_ratio=0.25,
        seed=7,
        move_threshold=0.03,
        followthrough_hours=6.0,
    )

    assert summary["event_holdout_rows"] > 0
    assert set(summary["splits"]) == {"event_holdout", "time_validation"}

    metrics_df = pd.read_csv(output_dir / "offline_eval_metrics.csv")
    assert set(metrics_df["split"]) == {"event_holdout", "time_validation"}
    assert set(metrics_df["model"]) == {"baseline", "tsfm_raw", "tsfm_conformal"}
    assert all(col in metrics_df.columns for col in ["coverage_80", "coverage_90", "pinball_mean"])

    summary_json = json.loads((output_dir / "offline_eval_summary.json").read_text(encoding="utf-8"))
    assert summary_json["rows"] == 40
    assert summary_json["model_prefixes"] == ["baseline", "tsfm_raw", "tsfm_conformal"]


def test_event_holdout_pipeline_outputs_are_reproducible(tmp_path: Path) -> None:
    input_path = tmp_path / "offline_eval_input.csv"
    _build_fixture(input_path)

    output_a = tmp_path / "artifacts_a"
    output_b = tmp_path / "artifacts_b"

    kwargs = {
        "input_path": input_path,
        "model_prefixes": ["baseline", "tsfm_raw", "tsfm_conformal"],
        "validation_ratio": 0.2,
        "holdout_ratio": 0.25,
        "seed": 7,
        "move_threshold": 0.03,
        "followthrough_hours": 6.0,
    }

    run(output_dir=output_a, **kwargs)
    run(output_dir=output_b, **kwargs)

    metrics_a = (output_a / "offline_eval_metrics.csv").read_text(encoding="utf-8")
    metrics_b = (output_b / "offline_eval_metrics.csv").read_text(encoding="utf-8")
    summary_a = json.loads((output_a / "offline_eval_summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((output_b / "offline_eval_summary.json").read_text(encoding="utf-8"))

    assert metrics_a == metrics_b
    for key in (
        "rows",
        "time_validation_rows",
        "event_holdout_rows",
        "model_prefixes",
        "splits",
    ):
        assert summary_a[key] == summary_b[key]
