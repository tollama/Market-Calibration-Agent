#!/usr/bin/env python3
"""Generate a deterministic forecasting baseline artifact pack from repo-local fixture data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.evaluate_tsfm_offline import run as run_offline_eval
from pipelines.generate_backtest_report import EventHoldoutConfig, WalkForwardConfig, generate_backtest_report
from scripts.evaluate_forecasting_promotion_gate import evaluate_promotion_gate


def _build_fixture_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    categories = ("politics", "macro", "sports")
    liquidity_values = ("high", "mid", "low")
    tte_values = ("0_24h", "24_72h", "72h_plus")
    for idx in range(18):
        category = categories[idx % len(categories)]
        liquidity = liquidity_values[idx % len(liquidity_values)]
        tte_bucket = tte_values[idx % len(tte_values)]
        actual = float(((idx * 7) % 10) / 10.0)
        market_prob = min(max(actual + (-0.08 if idx % 4 == 0 else 0.06 if idx % 5 == 0 else 0.02), 0.05), 0.95)
        baseline_q50 = min(max((market_prob * 0.85) + (actual * 0.15), 0.01), 0.99)
        tsfm_raw_q50 = min(max((market_prob * 0.55) + (actual * 0.45), 0.01), 0.99)
        tsfm_conformal_q50 = min(max((market_prob * 0.35) + (actual * 0.65), 0.01), 0.99)
        row = {
            "market_id": f"m-{idx + 1}",
            "event_id": f"e-{(idx // 2) + 1}",
            "category": category,
            "platform": "kalshi" if idx % 2 == 0 else "manifold",
            "liquidity_bucket": liquidity,
            "tte_bucket": tte_bucket,
            "horizon_hours": 24 if idx % 2 == 0 else 72,
            "ts": f"2026-01-{idx + 1:02d}T00:00:00Z",
            "actual": actual,
            "market_prob": market_prob,
            "baseline_q10": max(0.0, baseline_q50 - 0.10),
            "baseline_q50": baseline_q50,
            "baseline_q90": min(1.0, baseline_q50 + 0.10),
            "tsfm_raw_q10": max(0.0, tsfm_raw_q50 - 0.08),
            "tsfm_raw_q50": tsfm_raw_q50,
            "tsfm_raw_q90": min(1.0, tsfm_raw_q50 + 0.08),
            "tsfm_conformal_q10": max(0.0, tsfm_conformal_q50 - 0.06),
            "tsfm_conformal_q50": tsfm_conformal_q50,
            "tsfm_conformal_q90": min(1.0, tsfm_conformal_q50 + 0.06),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _build_backtest_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for idx, row in frame.reset_index(drop=True).iterrows():
        rows.append(
            {
                "market_id": row["market_id"],
                "event_id": row["event_id"],
                "ts": row["ts"],
                "resolution_ts": f"2026-02-{(idx % 18) + 1:02d}T00:00:00Z",
                "label": int(float(row["actual"]) >= 0.5),
                "p_yes": row["market_prob"],
                "pred": row["tsfm_conformal_q50"],
                "baseline_pred": row["baseline_q50"],
                "category": row["category"],
                "liquidity_bucket": str(row["liquidity_bucket"]).upper(),
                "tte_bucket": row["tte_bucket"],
                "template_group": "elections" if row["category"] == "politics" else "economy",
                "market_template": f"{row['category']}-yes-no",
                "horizon_hours": row["horizon_hours"],
            }
        )
    return pd.DataFrame(rows)


def _write_dataset_summary(frame: pd.DataFrame, path: Path) -> None:
    summary = {
        "rows": int(len(frame)),
        "markets": int(frame["market_id"].nunique()),
        "events": int(frame["event_id"].nunique()),
        "categories": sorted(frame["category"].astype(str).unique().tolist()),
        "liquidity_buckets": sorted(frame["liquidity_bucket"].astype(str).unique().tolist()),
        "tte_buckets": sorted(frame["tte_bucket"].astype(str).unique().tolist()),
        "platforms": sorted(frame["platform"].astype(str).unique().tolist()),
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def _write_benchmark_summary(offline_dir: Path, backtest_dir: Path, path: Path) -> None:
    offline_metrics = pd.read_csv(offline_dir / "offline_eval_metrics.csv")
    decision_summary = pd.read_csv(backtest_dir / "decision_summary.csv")
    score_column = "mse_q50" if "mse_q50" in offline_metrics.columns else "mae_q50"
    benchmark = {
        "offline_models": sorted(offline_metrics["model"].astype(str).unique().tolist()),
        "offline_splits": sorted(offline_metrics["split"].astype(str).unique().tolist()),
        "best_score_by_split": (
            offline_metrics.sort_values(["split", score_column, "model"])
            .groupby("split", sort=True)
            .first()
            .reset_index()[["split", "model", score_column]]
            .to_dict("records")
        ),
        "promotion_decisions": decision_summary.to_dict("records"),
        "offline_primary_score_column": score_column,
    }
    path.write_text(json.dumps(benchmark, indent=2, sort_keys=True), encoding="utf-8")


def generate_pack(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir = output_dir / "inputs"
    offline_dir = output_dir / "offline_eval"
    backtest_dir = output_dir / "backtest_report"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    offline_frame = _build_fixture_rows()
    backtest_frame = _build_backtest_rows(offline_frame)

    offline_input = inputs_dir / "offline_eval_input.csv"
    backtest_input = inputs_dir / "backtest_rows.csv"
    offline_frame.to_csv(offline_input, index=False)
    backtest_frame.to_csv(backtest_input, index=False)

    _write_dataset_summary(offline_frame, output_dir / "dataset_summary.json")

    run_offline_eval(
        input_path=offline_input,
        output_dir=offline_dir,
        model_prefixes=["baseline", "tsfm_raw", "tsfm_conformal"],
        validation_ratio=0.25,
        holdout_ratio=0.25,
        seed=42,
        move_threshold=0.03,
        followthrough_hours=6.0,
        edge_threshold=0.03,
    )

    generate_backtest_report(
        backtest_frame,
        report_dir=backtest_dir,
        walk_forward=WalkForwardConfig(
            n_splits=3,
            initial_train_fraction=0.4,
            min_train_rows=4,
            min_test_rows=2,
        ),
        event_holdout=EventHoldoutConfig(
            holdout_fraction=0.25,
            min_test_rows=2,
            seed=42,
        ),
    )

    _write_benchmark_summary(offline_dir, backtest_dir, output_dir / "benchmark_summary.json")
    promotion = evaluate_promotion_gate(backtest_dir / "decision_summary.csv")
    (output_dir / "promotion_decision.json").write_text(
        json.dumps(promotion, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    readme_lines = [
        "# Forecasting Baseline Artifact Pack",
        "",
        "This pack is a deterministic repo-local reference artifact set generated from fixture data.",
        "It is intended to keep the forecasting benchmark contract, reporting schema, and promotion-gate flow reproducible in-repo.",
        "",
        "Contents:",
        "- `dataset_summary.json`",
        "- `benchmark_summary.json`",
        "- `promotion_decision.json`",
        "- `inputs/offline_eval_input.csv`",
        "- `inputs/backtest_rows.csv`",
        "- `offline_eval/`",
        "- `backtest_report/`",
        "",
        "Generation command:",
        "```bash",
        f"python3 scripts/generate_forecasting_baseline_pack.py --output-dir {output_dir}",
        "```",
    ]
    (output_dir / "README.md").write_text("\n".join(readme_lines).rstrip() + "\n", encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "offline_eval_dir": str(offline_dir),
        "backtest_report_dir": str(backtest_dir),
        "promotion_decision": promotion["overall_decision"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic forecasting baseline artifact pack")
    parser.add_argument(
        "--output-dir",
        default="artifacts/forecasting_baseline_pack/reference_fixture_v1",
        help="artifact output directory",
    )
    args = parser.parse_args()
    summary = generate_pack(Path(args.output_dir))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
