#!/usr/bin/env python3
"""Summarize recent N-run KPI contract status (Go/No-Go)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    "brier_max": 0.20,
    "ece_max": 0.08,
    "realized_slippage_bps_max": 15.0,
    "execution_fail_rate_max": 0.02,
}


@dataclass
class RunRow:
    run_id: str
    ts: str
    stage: str
    brier: float
    ece: float
    realized_slippage_bps: float
    execution_fail_rate: float


def _parse_ts(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _to_float(payload: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        if key in payload and payload[key] is not None:
            return float(payload[key])
    raise ValueError(f"missing required field (any of {keys})")


def _load_rows(path: Path) -> list[RunRow]:
    if not path.exists():
        raise FileNotFoundError(path)

    rows: list[dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    elif path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("runs"), list):
            rows = payload["runs"]
        else:
            raise ValueError("JSON input must be a list or {'runs': [...]} shape")
    else:
        raise ValueError("unsupported input format (use .json/.jsonl)")

    out: list[RunRow] = []
    for row in rows:
        run_id = str(row.get("run_id") or row.get("id") or "unknown")
        ts = str(
            row.get("ts")
            or row.get("timestamp")
            or row.get("ended_at")
            or row.get("endedAt")
            or row.get("as_of")
            or ""
        )
        if not ts:
            raise ValueError(f"run {run_id}: missing ts/timestamp/ended_at")
        stage = str(row.get("stage") or row.get("rollout_stage") or "unknown")
        out.append(
            RunRow(
                run_id=run_id,
                ts=ts,
                stage=stage,
                brier=_to_float(row, ["brier"]),
                ece=_to_float(row, ["ece"]),
                realized_slippage_bps=_to_float(
                    row,
                    ["realized_slippage_bps", "realized_slippage", "slippage_bps"],
                ),
                execution_fail_rate=_to_float(
                    row,
                    ["execution_fail_rate", "exec_fail_rate", "failure_rate"],
                ),
            )
        )
    return out


def _load_thresholds(path: Path | None, stage: str) -> dict[str, float]:
    if path is None:
        return DEFAULT_THRESHOLDS.copy()
    payload = json.loads(path.read_text(encoding="utf-8"))
    stages = payload.get("stages") if isinstance(payload, dict) else None
    if not isinstance(stages, dict):
        return DEFAULT_THRESHOLDS.copy()

    def _resolve(stage_name: str) -> dict[str, Any]:
        current = stages.get(stage_name)
        if not isinstance(current, dict):
            return {}
        inherit = current.get("inherit")
        base = _resolve(str(inherit)) if isinstance(inherit, str) else {}
        merged = {**base}
        for k, v in current.items():
            if k == "inherit":
                continue
            merged[k] = v
        return merged

    resolved = _resolve(stage)
    merged = {**DEFAULT_THRESHOLDS}
    merged.update({k: float(v) for k, v in resolved.items() if k in DEFAULT_THRESHOLDS})
    return merged


def _evaluate(row: RunRow, t: dict[str, float]) -> tuple[str, list[str]]:
    fails: list[str] = []
    if row.brier > t["brier_max"]:
        fails.append(f"brier>{t['brier_max']:.4f}")
    if row.ece > t["ece_max"]:
        fails.append(f"ece>{t['ece_max']:.4f}")
    if row.realized_slippage_bps > t["realized_slippage_bps_max"]:
        fails.append(f"realized_slippage_bps>{t['realized_slippage_bps_max']:.2f}")
    if row.execution_fail_rate > t["execution_fail_rate_max"]:
        fails.append(f"execution_fail_rate>{t['execution_fail_rate_max']:.4f}")
    return ("WARN" if fails else "OK", fails)


def main() -> int:
    parser = argparse.ArgumentParser(description="N-run KPI contract report")
    parser.add_argument("--input", required=True, help="run-level KPI data (.json/.jsonl)")
    parser.add_argument("--n", type=int, default=10, help="recent N runs to summarize")
    parser.add_argument("--stage", default="canary", help="threshold stage (canary/prod/common)")
    parser.add_argument("--thresholds", default="configs/kpi_contract_thresholds.json")
    parser.add_argument("--output-json", help="optional output summary path")
    args = parser.parse_args()

    input_path = Path(args.input)
    thresholds_path = Path(args.thresholds) if args.thresholds else None

    rows = _load_rows(input_path)
    rows = sorted(rows, key=lambda r: _parse_ts(r.ts), reverse=True)[: max(1, int(args.n))]
    thresholds = _load_thresholds(thresholds_path, stage=str(args.stage))

    report_rows: list[dict[str, Any]] = []
    warn_count = 0

    for row in rows:
        status, fails = _evaluate(row, thresholds)
        if status == "WARN":
            warn_count += 1
        report_rows.append(
            {
                "run_id": row.run_id,
                "ts": row.ts,
                "stage": row.stage,
                "brier": row.brier,
                "ece": row.ece,
                "realized_slippage_bps": row.realized_slippage_bps,
                "execution_fail_rate": row.execution_fail_rate,
                "status": status,
                "alerts": fails,
            }
        )

    print(f"[KPI Contract] stage={args.stage} recent_n={len(report_rows)}")
    print(
        "thresholds: "
        f"brier<={thresholds['brier_max']:.4f}, "
        f"ece<={thresholds['ece_max']:.4f}, "
        f"realized_slippage_bps<={thresholds['realized_slippage_bps_max']:.2f}, "
        f"execution_fail_rate<={thresholds['execution_fail_rate_max']:.4f}"
    )
    print("-" * 120)
    print("ts | run_id | stage | brier | ece | slippage_bps | exec_fail_rate | status | alerts")
    print("-" * 120)
    for row in report_rows:
        print(
            f"{row['ts']} | {row['run_id']} | {row['stage']} | "
            f"{row['brier']:.4f} | {row['ece']:.4f} | {row['realized_slippage_bps']:.2f} | "
            f"{row['execution_fail_rate']:.4f} | {row['status']} | "
            f"{','.join(row['alerts']) if row['alerts'] else '-'}"
        )

    overall = "GO" if warn_count == 0 else "NO_GO"
    print("-" * 120)
    print(f"overall={overall} warn_runs={warn_count}/{len(report_rows)}")

    payload = {
        "stage": args.stage,
        "recent_n": len(report_rows),
        "thresholds": thresholds,
        "overall": overall,
        "warn_runs": warn_count,
        "runs": report_rows,
    }

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return 0 if warn_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
