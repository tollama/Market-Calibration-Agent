from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from calibration.interval_metrics import compute_interval_metrics


REQUIRED_BASE_COLUMNS = ("market_id", "event_id", "category", "ts", "actual")


def _load_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {path}")


def _split_time(df: pd.DataFrame, validation_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < validation_ratio < 1:
        raise ValueError("validation_ratio must be in (0,1)")
    ordered = df.sort_values("ts").reset_index(drop=True)
    split_idx = max(1, int(len(ordered) * (1 - validation_ratio)))
    return ordered.iloc[:split_idx], ordered.iloc[split_idx:]


def _split_event_holdout(
    df: pd.DataFrame,
    holdout_ratio: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < holdout_ratio < 1:
        raise ValueError("holdout_ratio must be in (0,1)")

    rng = pd.Series(df["event_id"].unique()).sample(frac=1.0, random_state=seed).tolist()
    holdout_count = max(1, int(len(rng) * holdout_ratio))
    holdout_events = set(rng[:holdout_count])
    is_holdout = df["event_id"].isin(holdout_events)
    return df.loc[~is_holdout].copy(), df.loc[is_holdout].copy()


def _calc_followthrough(
    df: pd.DataFrame,
    *,
    move_threshold: float,
    followthrough_hours: float,
) -> pd.DataFrame:
    enriched = df.sort_values(["market_id", "ts"]).copy()
    enriched["ts"] = pd.to_datetime(enriched["ts"], utc=True)

    # infer median step in minutes, default to 5m when unavailable
    diffs = (
        enriched.groupby("market_id")["ts"]
        .diff()
        .dt.total_seconds()
        .dropna()
    )
    step_seconds = float(diffs.median()) if not diffs.empty else 300.0
    horizon_steps = max(1, int((followthrough_hours * 3600.0) / max(step_seconds, 1.0)))

    def _market_followthrough(group: pd.DataFrame) -> pd.DataFrame:
        values = group["actual"].astype(float).tolist()
        out = []
        for idx, current in enumerate(values):
            end = min(len(values), idx + horizon_steps + 1)
            window = values[idx + 1 : end]
            if not window:
                out.append(0.0)
                continue
            out.append(max(abs(v - current) for v in window))
        g = group.copy()
        g["future_abs_move"] = out
        g["meaningful_move"] = g["future_abs_move"] >= float(move_threshold)
        return g

    return enriched.groupby("market_id", group_keys=False).apply(_market_followthrough)


def _model_frame(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    required = [f"{prefix}_q10", f"{prefix}_q50", f"{prefix}_q90"]
    optional_90 = [f"{prefix}_q05", f"{prefix}_q95"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for model {prefix}: {missing}")

    frame = pd.DataFrame(
        {
            "actual": df["actual"],
            "q10": df[f"{prefix}_q10"],
            "q50": df[f"{prefix}_q50"],
            "q90": df[f"{prefix}_q90"],
        }
    )
    if all(col in df.columns for col in optional_90):
        frame["q05"] = df[f"{prefix}_q05"]
        frame["q95"] = df[f"{prefix}_q95"]
    return frame


def _evaluate_split(df: pd.DataFrame, model_prefixes: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prefix in model_prefixes:
        metric_obj = compute_interval_metrics(_model_frame(df, prefix).to_dict("records"))

        q10 = df[f"{prefix}_q10"].astype(float)
        q90 = df[f"{prefix}_q90"].astype(float)
        actual = df["actual"].astype(float)
        breached = (actual < q10) | (actual > q90)
        breach_rate = float(breached.mean())

        if "meaningful_move" in df.columns:
            breach_followthrough_rate = (
                float(df.loc[breached, "meaningful_move"].mean()) if breached.any() else 0.0
            )
        else:
            breach_followthrough_rate = 0.0

        row = asdict(metric_obj)
        row.update(
            {
                "model": prefix,
                "breach_rate": breach_rate,
                "breach_followthrough_rate": breach_followthrough_rate,
            }
        )
        rows.append(row)
    return rows


def run(
    *,
    input_path: Path,
    output_dir: Path,
    model_prefixes: list[str],
    validation_ratio: float,
    holdout_ratio: float,
    seed: int,
    move_threshold: float,
    followthrough_hours: float,
) -> dict[str, Any]:
    df = _load_table(input_path)
    for col in REQUIRED_BASE_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Missing required base column: {col}")

    df = _calc_followthrough(
        df,
        move_threshold=move_threshold,
        followthrough_hours=followthrough_hours,
    )

    _, time_val = _split_time(df, validation_ratio=validation_ratio)
    _, event_holdout = _split_event_holdout(df, holdout_ratio=holdout_ratio, seed=seed)

    result_rows: list[dict[str, Any]] = []
    for split_name, split_df in (("time_validation", time_val), ("event_holdout", event_holdout)):
        for row in _evaluate_split(split_df, model_prefixes):
            row["split"] = split_name
            result_rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    detail_df = pd.DataFrame(result_rows)
    detail_path = output_dir / "offline_eval_metrics.csv"
    detail_df.to_csv(detail_path, index=False)

    summary = {
        "input_path": str(input_path),
        "output_metrics_csv": str(detail_path),
        "rows": len(df),
        "time_validation_rows": len(time_val),
        "event_holdout_rows": len(event_holdout),
        "model_prefixes": model_prefixes,
        "splits": sorted(detail_df["split"].unique().tolist()),
    }
    summary_path = output_dir / "offline_eval_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="PRD2 offline TSFM interval evaluation")
    parser.add_argument("--input", required=True, help="input parquet/csv/jsonl path")
    parser.add_argument("--output-dir", default="artifacts/prd2_offline_eval")
    parser.add_argument(
        "--model-prefix",
        action="append",
        dest="model_prefixes",
        default=["baseline", "tsfm_raw", "tsfm_conformal"],
        help="column prefix for quantiles, e.g. tsfm_raw => tsfm_raw_q10...",
    )
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--move-threshold", type=float, default=0.03)
    parser.add_argument("--followthrough-hours", type=float, default=6.0)
    args = parser.parse_args()

    summary = run(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        model_prefixes=list(dict.fromkeys(args.model_prefixes)),
        validation_ratio=float(args.validation_ratio),
        holdout_ratio=float(args.holdout_ratio),
        seed=int(args.seed),
        move_threshold=float(args.move_threshold),
        followthrough_hours=float(args.followthrough_hours),
    )

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
