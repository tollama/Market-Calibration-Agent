from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from calibration.conformal import (
    apply_conformal_adjustment_many,
    coverage_report,
    fit_conformal_adjustment,
)
from calibration.conformal_state import save_conformal_adjustment


def _iter_rows(path: Path) -> Iterable[Mapping[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield row
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, Mapping):
            yield payload


def _as_float(raw: Any) -> float:
    return float(raw)


def _normalize_sample(row: Mapping[str, Any]) -> tuple[dict[str, float], float] | None:
    candidate_band = row.get("band") or row.get("forecast_band") or row
    if not isinstance(candidate_band, Mapping):
        return None

    actual = row.get("actual")
    if actual is None:
        actual = row.get("resolved_prob")
    if actual is None:
        return None

    keys = {
        "q10": candidate_band.get("q10"),
        "q50": candidate_band.get("q50"),
        "q90": candidate_band.get("q90"),
    }
    if any(value is None for value in keys.values()):
        return None

    return {k: _as_float(v) for k, v in keys.items()}, _as_float(actual)


def run(
    *,
    input_path: Path,
    state_path: Path,
    target_coverage: float,
    window_size: int,
    min_samples: int,
    dry_run: bool,
) -> int:
    samples: list[tuple[dict[str, float], float]] = []
    for row in _iter_rows(input_path):
        parsed = _normalize_sample(row)
        if parsed is not None:
            samples.append(parsed)

    if window_size > 0:
        samples = samples[-window_size:]

    if len(samples) < min_samples:
        print(f"SKIP: insufficient samples ({len(samples)} < {min_samples})")
        return 2

    bands = [band for band, _ in samples]
    actuals = [actual for _, actual in samples]
    adjustment = fit_conformal_adjustment(
        bands,
        actuals,
        target_coverage=target_coverage,
    )

    pre_report = coverage_report(bands, actuals)
    post_report = coverage_report(apply_conformal_adjustment_many(bands, adjustment), actuals)

    metadata = {
        "source": str(input_path),
        "window_size": len(samples),
        "pre_coverage": pre_report["empirical_coverage"],
        "post_coverage": post_report["empirical_coverage"],
        "target_coverage": target_coverage,
    }

    if dry_run:
        print("DRY_RUN")
    else:
        save_conformal_adjustment(adjustment, path=state_path, metadata=metadata)

    print(f"samples={len(samples)}")
    print(f"target_coverage={target_coverage:.3f}")
    print(f"center_shift={adjustment.center_shift:.6f}")
    print(f"width_scale={adjustment.width_scale:.6f}")
    print(f"pre_coverage={pre_report['empirical_coverage']:.4f}")
    print(f"post_coverage={post_report['empirical_coverage']:.4f}")
    if not dry_run:
        print(f"state_path={state_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rolling conformal calibration state updater")
    parser.add_argument(
        "--input",
        dest="input_path",
        default="data/derived/calibration/conformal_history.jsonl",
        help="JSONL/CSV history containing q10/q50/q90 + actual",
    )
    parser.add_argument(
        "--state-path",
        default="data/derived/calibration/conformal_state.json",
        help="destination conformal calibration state",
    )
    parser.add_argument("--target-coverage", type=float, default=0.8)
    parser.add_argument("--window-size", type=int, default=2000)
    parser.add_argument("--min-samples", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    return run(
        input_path=Path(args.input_path),
        state_path=Path(args.state_path),
        target_coverage=float(args.target_coverage),
        window_size=int(args.window_size),
        min_samples=int(args.min_samples),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
