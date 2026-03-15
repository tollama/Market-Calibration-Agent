#!/usr/bin/env python3
"""Evaluate forecasting promotion decisions from a backtest decision summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def evaluate_promotion_gate(decision_summary_path: Path) -> dict[str, object]:
    frame = pd.read_csv(decision_summary_path)
    if frame.empty:
        return {
            "decision_summary_path": str(decision_summary_path),
            "gate_passed": False,
            "recommended_variants": [],
            "conditional_variants": [],
            "blocked_variants": [],
            "reference_variants": [],
            "overall_decision": "no_go",
            "reason": "empty_decision_summary",
        }

    decision_col = frame["decision"].fillna("no_go").astype(str)
    reference_variants = sorted(frame.loc[decision_col == "reference", "model_variant"].astype(str).tolist())
    go_variants = sorted(frame.loc[decision_col == "go", "model_variant"].astype(str).tolist())
    conditional_variants = sorted(frame.loc[decision_col == "conditional_go", "model_variant"].astype(str).tolist())
    blocked_variants = sorted(frame.loc[decision_col == "no_go", "model_variant"].astype(str).tolist())

    if go_variants:
        overall_decision = "go"
    elif conditional_variants:
        overall_decision = "conditional_go"
    else:
        overall_decision = "no_go"

    return {
        "decision_summary_path": str(decision_summary_path),
        "gate_passed": bool(go_variants),
        "recommended_variants": go_variants,
        "conditional_variants": conditional_variants,
        "blocked_variants": blocked_variants,
        "reference_variants": reference_variants,
        "overall_decision": overall_decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate forecasting promotion decision summary")
    parser.add_argument("--input", required=True, help="path to decision_summary.csv")
    parser.add_argument("--output-json", help="optional output json path")
    args = parser.parse_args()

    result = evaluate_promotion_gate(Path(args.input))
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, sort_keys=True))
    return 0 if result["gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
