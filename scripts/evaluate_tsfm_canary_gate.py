#!/usr/bin/env python3
"""Evaluate TSFM canary promotion gates + rollback triggers from JSON metrics windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

REQUIRED_METRICS = [
    "p95_latency_ms",
    "error_rate",
    "fallback_rate",
    "breaker_open_rate",
    "invalid_output_rate",
]

FALLBACK_GATE_LIMIT = {
    "canary_5": 0.08,
    "canary_25": 0.10,
    "full_100": 0.10,
}


def longest_run_over(values: List[float], threshold: float) -> int:
    best = cur = 0
    for v in values:
        if v > threshold:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def evaluate(data: Dict, stage: str) -> Dict:
    if stage not in FALLBACK_GATE_LIMIT:
        raise ValueError(f"unsupported stage: {stage}")

    metrics = data.get("metrics", {})
    missing = [k for k in REQUIRED_METRICS if k not in metrics]
    if missing:
        raise ValueError(f"missing metrics keys: {missing}")

    lengths = {k: len(metrics[k]) for k in REQUIRED_METRICS}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"metrics length mismatch: {lengths}")

    n = next(iter(lengths.values()))
    if n == 0:
        raise ValueError("empty metric windows")

    window_minutes = int(data.get("window_minutes", 5))
    if window_minutes <= 0:
        raise ValueError("window_minutes must be > 0")

    p95 = metrics["p95_latency_ms"]
    err = metrics["error_rate"]
    fb = metrics["fallback_rate"]
    br = metrics["breaker_open_rate"]
    inv = metrics["invalid_output_rate"]

    rollback_reasons: List[str] = []

    if longest_run_over(p95, 400.0) >= 2:
        rollback_reasons.append("p95>400ms_for_2x5m")

    if any(v > 0.02 for v in err):
        rollback_reasons.append("error_rate>2pct_any_5m")

    if any(v > 0 for v in inv):
        rollback_reasons.append("invalid_output_rate>0")

    fb_run = longest_run_over(fb, 0.20)
    if fb_run * window_minutes >= 15:
        rollback_reasons.append("fallback_rate>20pct_for_15m")

    br_run = longest_run_over(br, 0.30)
    if br_run * window_minutes >= 15:
        rollback_reasons.append("breaker_open_rate>30pct_for_15m")

    gate_fail_reasons: List[str] = []

    if max(p95) > 300.0:
        gate_fail_reasons.append("gate:p95>300ms")

    if max(err) > 0.01:
        gate_fail_reasons.append("gate:error_rate>1pct")

    if max(inv) > 0:
        gate_fail_reasons.append("gate:invalid_output_rate_nonzero")

    if max(fb) > FALLBACK_GATE_LIMIT[stage]:
        gate_fail_reasons.append(f"gate:fallback_rate>{FALLBACK_GATE_LIMIT[stage]*100:.0f}pct_for_{stage}")

    rollback_triggered = len(rollback_reasons) > 0
    gate_passed = (not rollback_triggered) and (len(gate_fail_reasons) == 0)

    return {
        "stage": stage,
        "windows": n,
        "window_minutes": window_minutes,
        "gate_passed": gate_passed,
        "rollback_triggered": rollback_triggered,
        "rollback_reasons": rollback_reasons,
        "gate_fail_reasons": gate_fail_reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="TSFM canary gate evaluator")
    parser.add_argument("--input", required=True, help="Path to metrics JSON")
    parser.add_argument("--stage", required=True, choices=list(FALLBACK_GATE_LIMIT.keys()))
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text())
    result = evaluate(payload, args.stage)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["gate_passed"] else 2)


if __name__ == "__main__":
    main()
