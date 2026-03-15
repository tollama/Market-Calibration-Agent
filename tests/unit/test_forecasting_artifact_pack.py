from __future__ import annotations

import pandas as pd

from scripts.evaluate_forecasting_promotion_gate import evaluate_promotion_gate
from scripts.generate_forecasting_baseline_pack import generate_pack


def test_evaluate_promotion_gate_prefers_go_variants(tmp_path) -> None:
    decision_path = tmp_path / "decision_summary.csv"
    pd.DataFrame(
        [
            {"model_variant": "market", "decision": "reference"},
            {"model_variant": "baseline", "decision": "no_go"},
            {"model_variant": "tsfm_conformal", "decision": "go"},
        ]
    ).to_csv(decision_path, index=False)

    result = evaluate_promotion_gate(decision_path)

    assert result["gate_passed"] is True
    assert result["overall_decision"] == "go"
    assert result["recommended_variants"] == ["tsfm_conformal"]


def test_generate_pack_writes_expected_artifacts(tmp_path) -> None:
    summary = generate_pack(tmp_path / "baseline_pack")

    pack_dir = tmp_path / "baseline_pack"
    assert summary["promotion_decision"] in {"go", "conditional_go", "no_go"}
    assert (pack_dir / "dataset_summary.json").exists()
    assert (pack_dir / "benchmark_summary.json").exists()
    assert (pack_dir / "promotion_decision.json").exists()
    assert (pack_dir / "offline_eval" / "offline_eval_metrics.csv").exists()
    assert (pack_dir / "backtest_report" / "decision_summary.csv").exists()
