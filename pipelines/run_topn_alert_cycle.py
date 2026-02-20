from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipelines.alert_policy_loader import load_alert_min_trust_score, load_alert_thresholds
from pipelines.alert_topn_orchestration import orchestrate_top_n_alert_decisions
from runners.tsfm_service import TSFMRunnerService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one top-N alert decision cycle")
    parser.add_argument("--input", required=True, help="Path to JSON array market candidates")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--alert-config", default="configs/alerts.yaml")
    args = parser.parse_args()

    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("input must be a JSON array")

    thresholds = load_alert_thresholds(args.alert_config)
    min_trust = load_alert_min_trust_score(args.alert_config)
    service = TSFMRunnerService.from_runtime_config()

    decisions = orchestrate_top_n_alert_decisions(
        rows,
        tsfm_service=service,
        top_n=args.top_n,
        thresholds=thresholds,
        min_trust_score=min_trust,
    )
    print(json.dumps({"decision_count": len(decisions), "decisions": decisions}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
