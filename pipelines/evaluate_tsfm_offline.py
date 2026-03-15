from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from calibration.interval_metrics import compute_interval_metrics


REQUIRED_BASE_COLUMNS = ("market_id", "event_id", "category", "ts", "actual")
OPTIONAL_GROUP_COLUMNS = ("category", "liquidity_bucket", "tte_bucket", "horizon_hours", "platform")
MARKET_BASELINE_CANDIDATES = ("market_prob", "p_yes", "baseline_q50")


@dataclass(frozen=True)
class PointForecastMetrics:
    samples: int
    mse_q50: float
    rmse_q50: float
    mae_q50: float
    mean_actual: float
    mean_forecast: float
    mean_error: float
    mean_abs_error: float


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

    ordered_events = pd.Series(df["event_id"].unique()).sample(frac=1.0, random_state=seed).tolist()
    holdout_count = max(1, int(len(ordered_events) * holdout_ratio))
    holdout_events = set(ordered_events[:holdout_count])
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

    diffs = enriched.groupby("market_id")["ts"].diff().dt.total_seconds().dropna()
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

    groups = []
    for _, group in enriched.groupby("market_id", sort=False):
        groups.append(_market_followthrough(group))
    return pd.concat(groups, ignore_index=True) if groups else enriched.iloc[0:0].copy()


def _resolve_market_baseline_column(df: pd.DataFrame) -> str | None:
    for column in MARKET_BASELINE_CANDIDATES:
        if column in df.columns:
            return column
    return None


def _market_frame(df: pd.DataFrame, column: str) -> pd.DataFrame:
    return pd.DataFrame({"actual": df["actual"], "q50": df[column]})


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


def _compute_point_forecast_metrics(actual: pd.Series, forecast: pd.Series) -> PointForecastMetrics:
    actual_values = pd.to_numeric(actual, errors="coerce").astype(float)
    forecast_values = pd.to_numeric(forecast, errors="coerce").astype(float)
    clean = pd.DataFrame({"actual": actual_values, "forecast": forecast_values}).dropna()
    if clean.empty:
        return PointForecastMetrics(
            samples=0,
            mse_q50=float("nan"),
            rmse_q50=float("nan"),
            mae_q50=float("nan"),
            mean_actual=float("nan"),
            mean_forecast=float("nan"),
            mean_error=float("nan"),
            mean_abs_error=float("nan"),
        )

    error = clean["forecast"] - clean["actual"]
    abs_error = error.abs()
    mse = float((error**2).mean())
    return PointForecastMetrics(
        samples=int(len(clean)),
        mse_q50=mse,
        rmse_q50=math.sqrt(mse),
        mae_q50=float(abs_error.mean()),
        mean_actual=float(clean["actual"].mean()),
        mean_forecast=float(clean["forecast"].mean()),
        mean_error=float(error.mean()),
        mean_abs_error=float(abs_error.mean()),
    )


def _compute_edge_metrics(
    df: pd.DataFrame,
    *,
    forecast: pd.Series,
    market_column: str | None,
    edge_threshold: float,
) -> dict[str, float]:
    if market_column is None:
        return {
            "selected": 0.0,
            "selection_rate": 0.0,
            "avg_abs_edge": float("nan"),
            "avg_signed_edge": float("nan"),
            "avg_pnl": float("nan"),
            "hit_rate": float("nan"),
            "meaningful_move_rate": float("nan"),
        }

    work = pd.DataFrame(
        {
            "forecast": pd.to_numeric(forecast, errors="coerce"),
            "market": pd.to_numeric(df[market_column], errors="coerce"),
            "actual": pd.to_numeric(df["actual"], errors="coerce"),
            "meaningful_move": df.get("meaningful_move"),
        }
    ).dropna(subset=["forecast", "market", "actual"])
    if work.empty:
        return {
            "selected": 0.0,
            "selection_rate": 0.0,
            "avg_abs_edge": float("nan"),
            "avg_signed_edge": float("nan"),
            "avg_pnl": float("nan"),
            "hit_rate": float("nan"),
            "meaningful_move_rate": float("nan"),
        }

    edge = work["forecast"] - work["market"]
    selected = work.loc[edge.abs() >= float(edge_threshold)].copy()
    if selected.empty:
        return {
            "selected": 0.0,
            "selection_rate": 0.0,
            "avg_abs_edge": 0.0,
            "avg_signed_edge": 0.0,
            "avg_pnl": 0.0,
            "hit_rate": 0.0,
            "meaningful_move_rate": 0.0,
        }

    signed_side = edge.loc[selected.index].apply(lambda value: 1.0 if value >= 0 else -1.0)
    pnl = signed_side * (selected["actual"] - selected["market"])
    meaningful_move_rate = (
        float(selected["meaningful_move"].mean()) if "meaningful_move" in selected.columns else float("nan")
    )
    return {
        "selected": float(len(selected)),
        "selection_rate": float(len(selected) / len(work)),
        "avg_abs_edge": float(edge.loc[selected.index].abs().mean()),
        "avg_signed_edge": float(edge.loc[selected.index].mean()),
        "avg_pnl": float(pnl.mean()),
        "hit_rate": float((pnl > 0).mean()),
        "meaningful_move_rate": meaningful_move_rate,
    }


def _build_metrics_row(
    df: pd.DataFrame,
    *,
    model_name: str,
    frame: pd.DataFrame,
    market_column: str | None,
    edge_threshold: float,
) -> dict[str, Any]:
    point_metrics = asdict(_compute_point_forecast_metrics(df["actual"], frame["q50"]))
    row: dict[str, Any] = {
        "model": model_name,
        **point_metrics,
        **_compute_edge_metrics(
            df,
            forecast=frame["q50"],
            market_column=market_column,
            edge_threshold=edge_threshold,
        ),
    }

    if {"q10", "q50", "q90"}.issubset(frame.columns):
        metric_obj = compute_interval_metrics(frame.to_dict("records"))
        q10 = frame["q10"].astype(float)
        q90 = frame["q90"].astype(float)
        actual = df["actual"].astype(float)
        breached = (actual < q10) | (actual > q90)
        row.update(
            {
                **asdict(metric_obj),
                "breach_rate": float(breached.mean()),
                "breach_followthrough_rate": (
                    float(df.loc[breached, "meaningful_move"].mean())
                    if breached.any() and "meaningful_move" in df.columns
                    else 0.0
                ),
            }
        )
    else:
        row.update(
            {
                "coverage_80": float("nan"),
                "coverage_90": float("nan"),
                "mean_width_80": float("nan"),
                "mean_width_90": float("nan"),
                "pinball_q10": float("nan"),
                "pinball_q50": float("nan"),
                "pinball_q90": float("nan"),
                "pinball_mean": float("nan"),
                "breach_rate": float("nan"),
                "breach_followthrough_rate": float("nan"),
                "samples": point_metrics["samples"],
            }
        )
    return row


def _evaluate_split(
    df: pd.DataFrame,
    model_prefixes: list[str],
    *,
    market_column: str | None,
    edge_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if market_column is not None:
        rows.append(
            _build_metrics_row(
                df,
                model_name="market",
                frame=_market_frame(df, market_column),
                market_column=market_column,
                edge_threshold=edge_threshold,
            )
        )
    for prefix in model_prefixes:
        rows.append(
            _build_metrics_row(
                df,
                model_name=prefix,
                frame=_model_frame(df, prefix),
                market_column=market_column,
                edge_threshold=edge_threshold,
            )
        )
    return rows


def _evaluate_segments(
    df: pd.DataFrame,
    model_prefixes: list[str],
    *,
    market_column: str | None,
    edge_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_by in OPTIONAL_GROUP_COLUMNS:
        if group_by not in df.columns:
            continue
        grouped = df.groupby(group_by, dropna=False, sort=True)
        for group_value, sub in grouped:
            if len(sub) == 0:
                continue
            for row in _evaluate_split(
                sub,
                model_prefixes,
                market_column=market_column,
                edge_threshold=edge_threshold,
            ):
                row["group_by"] = group_by
                row["group_value"] = group_value
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
    edge_threshold: float = 0.03,
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
    market_column = _resolve_market_baseline_column(df)

    _, time_val = _split_time(df, validation_ratio=validation_ratio)
    _, event_holdout = _split_event_holdout(df, holdout_ratio=holdout_ratio, seed=seed)

    result_rows: list[dict[str, Any]] = []
    segment_rows: list[dict[str, Any]] = []
    for split_name, split_df in (("time_validation", time_val), ("event_holdout", event_holdout)):
        for row in _evaluate_split(
            split_df,
            model_prefixes,
            market_column=market_column,
            edge_threshold=edge_threshold,
        ):
            row["split"] = split_name
            result_rows.append(row)
        for row in _evaluate_segments(
            split_df,
            model_prefixes,
            market_column=market_column,
            edge_threshold=edge_threshold,
        ):
            row["split"] = split_name
            segment_rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)

    detail_df = pd.DataFrame(result_rows).sort_values(["split", "model"]).reset_index(drop=True)
    detail_path = output_dir / "offline_eval_metrics.csv"
    detail_df.to_csv(detail_path, index=False)

    segment_df = pd.DataFrame(segment_rows)
    segment_path = output_dir / "offline_eval_segments.csv"
    if segment_df.empty:
        pd.DataFrame(
            columns=["split", "group_by", "group_value", "model"]
        ).to_csv(segment_path, index=False)
    else:
        segment_df.sort_values(["split", "group_by", "group_value", "model"]).reset_index(drop=True).to_csv(
            segment_path,
            index=False,
        )

    summary = {
        "schema_version": "2.0",
        "input_path": str(input_path),
        "output_metrics_csv": str(detail_path),
        "output_segments_csv": str(segment_path),
        "rows": len(df),
        "time_validation_rows": len(time_val),
        "event_holdout_rows": len(event_holdout),
        "model_prefixes": model_prefixes,
        "market_baseline_column": market_column,
        "splits": sorted(detail_df["split"].unique().tolist()),
        "group_fields": [field for field in OPTIONAL_GROUP_COLUMNS if field in df.columns],
        "edge_threshold": float(edge_threshold),
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
    parser.add_argument("--edge-threshold", type=float, default=0.03)
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
        edge_threshold=float(args.edge_threshold),
    )

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
