#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


KEY_VALUE_RE = re.compile(r"^([a-zA-Z0-9_]+)=(.+)$")


def parse_bench_log(path: Path) -> dict[str, object]:
    data: dict[str, object] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        match = KEY_VALUE_RE.match(line)
        if not match:
            continue
        key, value = match.groups()
        if value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
            continue
        try:
            if "." in value:
                data[key] = float(value)
            else:
                data[key] = int(value)
            continue
        except ValueError:
            data[key] = value

    required = {"requests", "elapsed_s", "latency_p95_ms"}
    missing = sorted(required - set(data.keys()))
    if missing:
        raise ValueError(f"Missing required keys in bench output: {', '.join(missing)}")
    return data


def validate_metrics(metrics: dict[str, object], p95_ms: float, cycle_s: float) -> tuple[bool, list[str]]:
    failures: list[str] = []
    actual_p95 = float(metrics["latency_p95_ms"])
    actual_cycle = float(metrics["elapsed_s"])

    if actual_p95 > p95_ms:
        failures.append(f"latency_p95_ms {actual_p95:.2f} > threshold {p95_ms:.2f}")
    if actual_cycle > cycle_s:
        failures.append(f"elapsed_s {actual_cycle:.2f} > threshold {cycle_s:.2f}")

    return (len(failures) == 0, failures)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and validate PRD2 benchmark output")
    parser.add_argument("--input", required=True, help="Path to raw bench stdout log or JSON file")
    parser.add_argument("--output", required=True, help="Path to write normalized JSON metrics")
    parser.add_argument("--p95-threshold-ms", type=float, default=300.0)
    parser.add_argument("--cycle-threshold-s", type=float, default=60.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if input_path.suffix.lower() == ".json":
        metrics = json.loads(input_path.read_text())
    else:
        metrics = parse_bench_log(input_path)

    ok, failures = validate_metrics(metrics, args.p95_threshold_ms, args.cycle_threshold_s)

    result = {
        "thresholds": {
            "p95_ms": args.p95_threshold_ms,
            "cycle_s": args.cycle_threshold_s,
        },
        "metrics": metrics,
        "ok": ok,
        "failures": failures,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    if ok:
        print("PERF_GATE_PASS")
        return 0

    print("PERF_GATE_FAIL")
    for failure in failures:
        print(f" - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
