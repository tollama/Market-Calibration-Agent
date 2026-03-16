"""Backtest report generation with walk-forward and event-holdout evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from calibration.metrics import summarize_metrics_extended

_DEFAULT_GROUP_FIELDS = (
    "category",
    "liquidity_bucket",
    "tte_bucket",
    "template_group",
    "market_template",
    "horizon_hours",
)
_DEFAULT_EDGE_BUCKETS = (0.0, 0.03, 0.05, 0.10, 1.01)


@dataclass(frozen=True)
class WalkForwardConfig:
    n_splits: int = 4
    initial_train_fraction: float = 0.5
    min_train_rows: int = 20
    min_test_rows: int = 10
    time_col: str = "ts"
    label_available_col: str = "resolution_ts"
    embargo_hours: float = 0.0


@dataclass(frozen=True)
class EventHoldoutConfig:
    holdout_fraction: float = 0.2
    min_test_rows: int = 10
    seed: int = 42
    event_id_col: str = "event_id"


@dataclass(frozen=True)
class BacktestGateConfig:
    benchmark_variant: str = "market"
    max_ece_regression: float = 0.01
    min_avg_pnl: float = 0.0


@dataclass(frozen=True)
class WalkForwardSplit:
    fold: int
    train_index: tuple[int, ...]
    test_index: tuple[int, ...]
    test_start_at: str
    test_end_at: str
    train_cutoff_at: str


def compute_prediction_metrics(
    rows: pd.DataFrame,
    *,
    prob_col: str,
    label_col: str = "label",
) -> dict[str, Any]:
    if rows.empty or prob_col not in rows.columns or label_col not in rows.columns:
        return _empty_prediction_metrics()

    clean = rows[[prob_col, label_col]].copy().dropna()
    if clean.empty:
        return _empty_prediction_metrics()

    probs = clean[prob_col].astype(float).clip(0.0, 1.0).tolist()
    labels = clean[label_col].astype(int).tolist()
    metrics = summarize_metrics_extended(probs, labels)
    base_rate = sum(labels) / len(labels)
    mean_prob = sum(probs) / len(probs)
    accuracy = sum(int((prob >= 0.5) == bool(label)) for prob, label in zip(probs, labels)) / len(labels)
    return {
        "rows": len(clean),
        "mean_prob": mean_prob,
        "base_rate": base_rate,
        "calibration_gap": abs(mean_prob - base_rate),
        "brier": metrics["brier"],
        "log_loss": metrics["log_loss"],
        "ece": metrics["ece"],
        "slope": metrics["slope"],
        "intercept": metrics["intercept"],
        "accuracy": accuracy,
    }


def hold_to_resolution_simulation(
    rows: pd.DataFrame,
    *,
    prob_col: str,
    market_col: str = "p_yes",
    label_col: str = "label",
    edge_threshold: float = 0.03,
) -> dict[str, Any]:
    required = {prob_col, market_col, label_col}
    if rows.empty or not required.issubset(rows.columns):
        return _empty_simulation_metrics()

    prob_series = pd.to_numeric(rows[prob_col], errors="coerce")
    market_series = pd.to_numeric(rows[market_col], errors="coerce")
    label_series = pd.to_numeric(rows[label_col], errors="coerce")
    clean = pd.DataFrame(
        {
            "prob": prob_series,
            "market": market_series,
            "label": label_series,
        }
    ).dropna()
    if clean.empty:
        return _empty_simulation_metrics()

    edge = clean["prob"].astype(float) - clean["market"].astype(float)
    selected = clean.loc[edge.abs() >= float(edge_threshold)].copy()
    if selected.empty:
        return {
            "selected": 0,
            "selection_rate": 0.0,
            "avg_pnl": float("nan"),
            "hit_rate": float("nan"),
            "avg_abs_edge": float("nan"),
        }
    signed_side = edge.loc[selected.index].apply(lambda value: 1.0 if value >= 0 else -1.0)
    realized_yes_pnl = selected["label"].astype(float) - selected["market"].astype(float)
    pnl = signed_side * realized_yes_pnl
    return {
        "selected": int(len(selected)),
        "selection_rate": float(len(selected) / len(clean)),
        "avg_pnl": float(pnl.mean()),
        "hit_rate": float((pnl > 0).mean()),
        "avg_abs_edge": float(edge.loc[selected.index].abs().mean()),
    }


def build_walk_forward_splits(
    rows: pd.DataFrame,
    config: WalkForwardConfig | None = None,
) -> list[WalkForwardSplit]:
    if rows.empty:
        return []

    cfg = config or WalkForwardConfig()
    work = rows.copy()
    work["_time_key"] = pd.to_datetime(work[cfg.time_col], utc=True, errors="coerce")
    work["_label_time_key"] = pd.to_datetime(work[cfg.label_available_col], utc=True, errors="coerce")
    work = work.loc[work["_time_key"].notna() & work["_label_time_key"].notna()].copy()
    if work.empty:
        return []

    counts = work.groupby("_time_key", sort=True).size()
    unique_times = list(counts.index)
    if len(unique_times) < 2:
        return []

    cumulative_rows = counts.cumsum().tolist()
    initial_target = max(int(len(work) * float(cfg.initial_train_fraction)), int(cfg.min_train_rows))
    start_time_pos = 0
    while start_time_pos < len(cumulative_rows) and cumulative_rows[start_time_pos] < initial_target:
        start_time_pos += 1
    embargo = pd.to_timedelta(float(cfg.embargo_hours), unit="h")
    while start_time_pos < len(unique_times):
        test_start = unique_times[start_time_pos]
        train_cutoff = test_start - embargo
        eligible_train = work.loc[work["_label_time_key"] <= train_cutoff]
        if len(eligible_train) >= int(cfg.min_train_rows):
            break
        start_time_pos += 1
    if start_time_pos >= len(unique_times):
        return []

    remaining_positions = list(range(start_time_pos, len(unique_times)))
    fold_count = min(int(cfg.n_splits), len(remaining_positions))
    if fold_count <= 0:
        return []

    chunks = _chunk_positions(remaining_positions, fold_count)
    splits: list[WalkForwardSplit] = []
    for fold, chunk in enumerate(chunks, start=1):
        test_times = {unique_times[pos] for pos in chunk}
        test_start = min(test_times)
        test_end = max(test_times)
        train_cutoff = test_start - embargo

        test_mask = work["_time_key"].isin(test_times)
        train_mask = work["_label_time_key"] <= train_cutoff
        train_mask &= ~test_mask

        train_index = tuple(int(idx) for idx in work.index[train_mask].tolist())
        test_index = tuple(int(idx) for idx in work.index[test_mask].tolist())
        if len(train_index) < int(cfg.min_train_rows) or len(test_index) < int(cfg.min_test_rows):
            continue

        splits.append(
            WalkForwardSplit(
                fold=fold,
                train_index=train_index,
                test_index=test_index,
                test_start_at=test_start.isoformat(),
                test_end_at=test_end.isoformat(),
                train_cutoff_at=train_cutoff.isoformat(),
            )
        )
    return splits


def build_event_holdout_split(
    rows: pd.DataFrame,
    config: EventHoldoutConfig | None = None,
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    cfg = config or EventHoldoutConfig()
    if cfg.event_id_col not in rows.columns:
        return pd.DataFrame()
    if not 0 < float(cfg.holdout_fraction) < 1:
        raise ValueError("event holdout fraction must be in (0, 1)")

    events = pd.Series(rows[cfg.event_id_col].dropna().unique())
    if events.empty:
        return pd.DataFrame()
    shuffled = events.sample(frac=1.0, random_state=int(cfg.seed)).tolist()
    holdout_count = max(1, int(len(shuffled) * float(cfg.holdout_fraction)))
    holdout_events = set(shuffled[:holdout_count])
    holdout = rows.loc[rows[cfg.event_id_col].isin(holdout_events)].copy()
    if len(holdout) < int(cfg.min_test_rows):
        return pd.DataFrame()
    return holdout.reset_index(drop=True)


def generate_backtest_report(
    rows: Sequence[Mapping[str, object]] | pd.DataFrame,
    *,
    report_dir: str | Path,
    prediction_columns: Mapping[str, str] | None = None,
    edge_threshold: float = 0.03,
    edge_buckets: Sequence[float] = _DEFAULT_EDGE_BUCKETS,
    group_fields: Sequence[str] = _DEFAULT_GROUP_FIELDS,
    walk_forward: WalkForwardConfig | None = None,
    event_holdout: EventHoldoutConfig | None = None,
    gates: BacktestGateConfig | None = None,
) -> dict[str, Any]:
    frame = _coerce_frame(rows)
    if frame.empty:
        raise ValueError("rows must be non-empty")
    if "label" not in frame.columns:
        raise ValueError("rows must include 'label'")

    variants = _resolve_prediction_columns(frame, prediction_columns)
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)

    overall = _build_overall_summary(frame, variants, edge_threshold=edge_threshold)
    group_metrics = _build_group_metrics(frame, variants, edge_threshold=edge_threshold, group_fields=group_fields)
    edge_bucket_metrics = _build_edge_bucket_metrics(
        frame,
        variants,
        edge_threshold=edge_threshold,
        edge_buckets=edge_buckets,
    )
    prediction_export = _build_prediction_export(frame, variants)

    overall.to_csv(report_path / "overall_summary.csv", index=False)
    group_metrics.to_csv(report_path / "group_metrics.csv", index=False)
    edge_bucket_metrics.to_csv(report_path / "edge_bucket_metrics.csv", index=False)
    prediction_export.to_csv(report_path / "predictions.csv", index=False)

    wf_overall = pd.DataFrame()
    wf_group_metrics = pd.DataFrame()
    wf_fold_summary = pd.DataFrame()
    wf_worst_fold_summary = pd.DataFrame()
    wf_edge_bucket_metrics = pd.DataFrame()
    wf_predictions = pd.DataFrame()
    splits = build_walk_forward_splits(frame, walk_forward)
    if splits:
        wf_predictions = _build_walk_forward_predictions(frame, splits, variants)
        wf_overall = _build_overall_summary(wf_predictions, variants, edge_threshold=edge_threshold)
        wf_group_metrics = _build_group_metrics(
            wf_predictions,
            variants,
            edge_threshold=edge_threshold,
            group_fields=group_fields,
        )
        wf_fold_summary = _build_fold_summary(wf_predictions, variants, edge_threshold=edge_threshold)
        wf_worst_fold_summary = _build_worst_fold_summary(wf_fold_summary)
        wf_edge_bucket_metrics = _build_edge_bucket_metrics(
            wf_predictions,
            variants,
            edge_threshold=edge_threshold,
            edge_buckets=edge_buckets,
        )
        wf_predictions.to_csv(report_path / "walk_forward_predictions.csv", index=False)
        wf_overall.to_csv(report_path / "walk_forward_overall_summary.csv", index=False)
        wf_group_metrics.to_csv(report_path / "walk_forward_group_metrics.csv", index=False)
        wf_fold_summary.to_csv(report_path / "walk_forward_fold_summary.csv", index=False)
        wf_worst_fold_summary.to_csv(report_path / "walk_forward_worst_fold_summary.csv", index=False)
        wf_edge_bucket_metrics.to_csv(report_path / "walk_forward_edge_bucket_metrics.csv", index=False)

    event_holdout_predictions = pd.DataFrame()
    event_holdout_overall = pd.DataFrame()
    event_holdout_group_metrics = pd.DataFrame()
    event_holdout_edge_bucket_metrics = pd.DataFrame()
    holdout_frame = build_event_holdout_split(frame, event_holdout)
    if not holdout_frame.empty:
        event_holdout_predictions = _build_prediction_export(holdout_frame, variants)
        event_holdout_overall = _build_overall_summary(holdout_frame, variants, edge_threshold=edge_threshold)
        event_holdout_group_metrics = _build_group_metrics(
            holdout_frame,
            variants,
            edge_threshold=edge_threshold,
            group_fields=group_fields,
        )
        event_holdout_edge_bucket_metrics = _build_edge_bucket_metrics(
            holdout_frame,
            variants,
            edge_threshold=edge_threshold,
            edge_buckets=edge_buckets,
        )
        event_holdout_predictions.to_csv(report_path / "event_holdout_predictions.csv", index=False)
        event_holdout_overall.to_csv(report_path / "event_holdout_overall_summary.csv", index=False)
        event_holdout_group_metrics.to_csv(report_path / "event_holdout_group_metrics.csv", index=False)
        event_holdout_edge_bucket_metrics.to_csv(report_path / "event_holdout_edge_bucket_metrics.csv", index=False)
    else:
        event_holdout_predictions.to_csv(report_path / "event_holdout_predictions.csv", index=False)
        event_holdout_overall.to_csv(report_path / "event_holdout_overall_summary.csv", index=False)
        event_holdout_group_metrics.to_csv(report_path / "event_holdout_group_metrics.csv", index=False)
        event_holdout_edge_bucket_metrics.to_csv(report_path / "event_holdout_edge_bucket_metrics.csv", index=False)

    decision_summary = _build_decision_summary(
        overall=overall,
        walk_forward_overall=wf_overall,
        walk_forward_worst_fold=wf_worst_fold_summary,
        event_holdout_overall=event_holdout_overall,
        gates=gates or BacktestGateConfig(),
    )
    decision_summary.to_csv(report_path / "decision_summary.csv", index=False)

    summary = {
        "row_count": int(len(frame)),
        "prediction_variants": list(variants.keys()),
        "group_fields": [field for field in group_fields if field in frame.columns],
        "walk_forward_enabled": bool(splits),
        "walk_forward_fold_count": len(splits),
        "event_holdout_enabled": not holdout_frame.empty,
        "event_holdout_rows": int(len(holdout_frame)),
        "edge_buckets": [float(value) for value in edge_buckets],
        "output_dir": str(report_path),
    }
    summary_markdown = _render_summary_markdown(
        summary,
        overall,
        wf_overall,
        wf_worst_fold_summary,
        event_holdout_overall,
        decision_summary,
    )
    (report_path / "summary.md").write_text(summary_markdown, encoding="utf-8")
    return summary


def _coerce_frame(rows: Sequence[Mapping[str, object]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame.from_records([dict(row) for row in rows])


def _empty_prediction_metrics() -> dict[str, Any]:
    return {
        "rows": 0,
        "mean_prob": float("nan"),
        "base_rate": float("nan"),
        "calibration_gap": float("nan"),
        "brier": float("nan"),
        "log_loss": float("nan"),
        "ece": float("nan"),
        "slope": float("nan"),
        "intercept": float("nan"),
        "accuracy": float("nan"),
    }


def _empty_simulation_metrics() -> dict[str, Any]:
    return {
        "selected": 0,
        "selection_rate": 0.0,
        "avg_pnl": float("nan"),
        "hit_rate": float("nan"),
        "avg_abs_edge": float("nan"),
    }


def _resolve_prediction_columns(
    frame: pd.DataFrame,
    columns: Mapping[str, str] | None,
) -> dict[str, str]:
    if columns is not None:
        resolved = {str(name): str(column) for name, column in columns.items() if column in frame.columns}
    else:
        resolved = {}
        defaults = (
            ("market", "p_yes"),
            ("primary", "pred"),
            ("baseline", "baseline_pred"),
            ("recalibrated", "recalibrated_pred"),
        )
        for variant, column in defaults:
            if column in frame.columns:
                resolved[variant] = column

    if "primary" not in resolved and "pred" in frame.columns:
        resolved["primary"] = "pred"
    if not resolved:
        raise ValueError("No usable prediction columns were found")
    return resolved


def _build_overall_summary(
    frame: pd.DataFrame,
    variants: Mapping[str, str],
    *,
    edge_threshold: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, column in variants.items():
        prob_col = _variant_probability_column(frame, variant, column)
        metrics = compute_prediction_metrics(frame, prob_col=prob_col)
        sim = hold_to_resolution_simulation(frame, prob_col=prob_col, edge_threshold=edge_threshold)
        rows.append({"model_variant": variant, **metrics, **sim})
    return pd.DataFrame(rows).sort_values("model_variant").reset_index(drop=True)


def _build_group_metrics(
    frame: pd.DataFrame,
    variants: Mapping[str, str],
    *,
    edge_threshold: float,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_field in group_fields:
        if group_field not in frame.columns:
            continue
        grouped = frame.groupby(group_field, dropna=False, sort=True)
        for group_value, sub in grouped:
            for variant, column in variants.items():
                prob_col = _variant_probability_column(sub, variant, column)
                metrics = compute_prediction_metrics(sub, prob_col=prob_col)
                sim = hold_to_resolution_simulation(sub, prob_col=prob_col, edge_threshold=edge_threshold)
                rows.append(
                    {
                        "group_by": group_field,
                        "group_value": group_value,
                        "model_variant": variant,
                        **metrics,
                        **sim,
                    }
                )
    return pd.DataFrame(rows)


def _build_edge_bucket_metrics(
    frame: pd.DataFrame,
    variants: Mapping[str, str],
    *,
    edge_threshold: float,
    edge_buckets: Sequence[float],
    market_col: str = "p_yes",
) -> pd.DataFrame:
    if market_col not in frame.columns:
        return pd.DataFrame()
    thresholds = sorted({float(value) for value in edge_buckets if float(value) >= 0.0})
    if len(thresholds) < 2:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    market_series = pd.to_numeric(frame[market_col], errors="coerce")
    for variant, column in variants.items():
        source_col = column if column in frame.columns else f"p_{variant}"
        if source_col not in frame.columns:
            continue
        probs = pd.to_numeric(frame[source_col], errors="coerce")
        edges = (probs - market_series).abs()
        for lower, upper in zip(thresholds[:-1], thresholds[1:]):
            mask = edges.ge(lower)
            if upper < thresholds[-1]:
                mask &= edges.lt(upper)
                bucket_label = f"[{lower:.2f},{upper:.2f})"
            else:
                mask &= edges.le(upper)
                bucket_label = f"[{lower:.2f},{upper:.2f}]"
            subset = frame.loc[mask].copy()
            if subset.empty:
                continue
            metrics = compute_prediction_metrics(subset, prob_col=source_col)
            sim = hold_to_resolution_simulation(
                subset,
                prob_col=source_col,
                market_col=market_col,
                edge_threshold=edge_threshold,
            )
            rows.append(
                {
                    "model_variant": variant,
                    "edge_bucket": bucket_label,
                    "bucket_min_abs_edge": lower,
                    "bucket_max_abs_edge": upper,
                    **metrics,
                    **sim,
                }
            )
    return pd.DataFrame(rows).sort_values(["model_variant", "bucket_min_abs_edge"]).reset_index(drop=True)


def _build_prediction_export(frame: pd.DataFrame, variants: Mapping[str, str]) -> pd.DataFrame:
    columns = [
        column
        for column in (
            "market_id",
            "event_id",
            "ts",
            "resolution_ts",
            "label",
            "category",
            "liquidity_bucket",
            "tte_bucket",
            "template_group",
            "market_template",
            "horizon_hours",
            "p_yes",
        )
        if column in frame.columns
    ]
    exported = frame[columns].copy() if columns else pd.DataFrame(index=frame.index)
    for variant, source_col in variants.items():
        exported[f"p_{variant}"] = frame[source_col]
    return exported.reset_index(drop=True)


def _variant_probability_column(frame: pd.DataFrame, variant: str, preferred_column: str) -> str:
    if preferred_column in frame.columns:
        return preferred_column
    exported_column = f"p_{variant}"
    if exported_column in frame.columns:
        return exported_column
    return preferred_column


def _build_walk_forward_predictions(
    frame: pd.DataFrame,
    splits: Sequence[WalkForwardSplit],
    variants: Mapping[str, str],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for split in splits:
        sub = frame.loc[list(split.test_index)].copy()
        sub["fold"] = split.fold
        sub["test_start_at"] = split.test_start_at
        sub["test_end_at"] = split.test_end_at
        sub["train_cutoff_at"] = split.train_cutoff_at
        sub["train_rows"] = len(split.train_index)
        sub["test_rows"] = len(split.test_index)
        rows.append(sub)

    merged = pd.concat(rows, ignore_index=True)
    return _build_prediction_export(merged, variants).join(
        merged[
            [
                column
                for column in (
                    "fold",
                    "test_start_at",
                    "test_end_at",
                    "train_cutoff_at",
                    "train_rows",
                    "test_rows",
                )
                if column in merged.columns
            ]
        ]
    )


def _build_fold_summary(
    frame: pd.DataFrame,
    variants: Mapping[str, str],
    *,
    edge_threshold: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if "fold" not in frame.columns:
        return pd.DataFrame()

    for fold, sub in frame.groupby("fold", sort=True):
        for variant in variants:
            prob_col = f"p_{variant}"
            metrics = compute_prediction_metrics(sub, prob_col=prob_col)
            sim = hold_to_resolution_simulation(sub, prob_col=prob_col, edge_threshold=edge_threshold)
            payload = {
                "fold": int(fold),
                "model_variant": variant,
                "train_rows": int(sub["train_rows"].iloc[0]) if "train_rows" in sub.columns else 0,
                "test_rows": int(sub["test_rows"].iloc[0]) if "test_rows" in sub.columns else len(sub),
                "test_start_at": sub["test_start_at"].iloc[0] if "test_start_at" in sub.columns else None,
                "test_end_at": sub["test_end_at"].iloc[0] if "test_end_at" in sub.columns else None,
            }
            payload.update(metrics)
            payload.update(sim)
            rows.append(payload)
    return pd.DataFrame(rows).sort_values(["fold", "model_variant"]).reset_index(drop=True)


def _build_worst_fold_summary(fold_summary: pd.DataFrame) -> pd.DataFrame:
    if fold_summary.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for variant, sub in fold_summary.groupby("model_variant", sort=True):
        worst_brier = sub.sort_values(["brier", "fold"], ascending=[False, True]).iloc[0]
        rows.append(
            {
                "model_variant": variant,
                "worst_fold": int(worst_brier["fold"]),
                "worst_fold_brier": float(worst_brier["brier"]),
                "worst_fold_log_loss": float(worst_brier["log_loss"]),
                "worst_fold_ece": float(worst_brier["ece"]),
                "worst_fold_avg_pnl": float(worst_brier["avg_pnl"]),
            }
        )
    return pd.DataFrame(rows).sort_values("model_variant").reset_index(drop=True)


def _build_decision_summary(
    *,
    overall: pd.DataFrame,
    walk_forward_overall: pd.DataFrame,
    walk_forward_worst_fold: pd.DataFrame,
    event_holdout_overall: pd.DataFrame,
    gates: BacktestGateConfig,
) -> pd.DataFrame:
    if overall.empty:
        return pd.DataFrame()

    benchmark_variant = str(gates.benchmark_variant)
    if benchmark_variant not in set(overall["model_variant"]):
        benchmark_variant = str(overall["model_variant"].iloc[0])

    overall_lookup = overall.set_index("model_variant")
    walk_lookup = (
        walk_forward_overall.set_index("model_variant") if not walk_forward_overall.empty else pd.DataFrame()
    )
    worst_lookup = (
        walk_forward_worst_fold.set_index("model_variant") if not walk_forward_worst_fold.empty else pd.DataFrame()
    )
    holdout_lookup = (
        event_holdout_overall.set_index("model_variant") if not event_holdout_overall.empty else pd.DataFrame()
    )

    benchmark_overall = overall_lookup.loc[benchmark_variant]
    benchmark_walk = walk_lookup.loc[benchmark_variant] if not walk_lookup.empty and benchmark_variant in walk_lookup.index else None
    benchmark_worst = worst_lookup.loc[benchmark_variant] if not worst_lookup.empty and benchmark_variant in worst_lookup.index else None
    benchmark_holdout = holdout_lookup.loc[benchmark_variant] if not holdout_lookup.empty and benchmark_variant in holdout_lookup.index else None

    rows: list[dict[str, Any]] = []
    for variant in overall["model_variant"].tolist():
        current = overall_lookup.loc[variant]
        if variant == benchmark_variant:
            rows.append(
                {
                    "model_variant": variant,
                    "benchmark_variant": benchmark_variant,
                    "overall_pass": True,
                    "walk_forward_pass": True,
                    "event_holdout_pass": True,
                    "decision": "reference",
                }
            )
            continue

        overall_pass = bool(
            current["brier"] <= benchmark_overall["brier"]
            and current["log_loss"] <= benchmark_overall["log_loss"]
            and current["ece"] <= benchmark_overall["ece"] + float(gates.max_ece_regression)
            and (pd.isna(current["avg_pnl"]) or current["avg_pnl"] >= float(gates.min_avg_pnl))
        )

        walk_pass = True
        if not walk_lookup.empty and variant in walk_lookup.index and benchmark_walk is not None:
            current_walk = walk_lookup.loc[variant]
            walk_pass = bool(
                current_walk["brier"] <= benchmark_walk["brier"]
                and current_walk["log_loss"] <= benchmark_walk["log_loss"]
                and current_walk["ece"] <= benchmark_walk["ece"] + float(gates.max_ece_regression)
            )
            if not worst_lookup.empty and variant in worst_lookup.index and benchmark_worst is not None:
                current_worst = worst_lookup.loc[variant]
                walk_pass = walk_pass and bool(
                    current_worst["worst_fold_brier"] <= benchmark_worst["worst_fold_brier"]
                )

        holdout_pass = True
        if not holdout_lookup.empty and variant in holdout_lookup.index and benchmark_holdout is not None:
            current_holdout = holdout_lookup.loc[variant]
            holdout_pass = bool(
                current_holdout["brier"] <= benchmark_holdout["brier"]
                and current_holdout["log_loss"] <= benchmark_holdout["log_loss"]
                and current_holdout["ece"] <= benchmark_holdout["ece"] + float(gates.max_ece_regression)
            )

        if overall_pass and walk_pass and holdout_pass:
            decision = "go"
        elif overall_pass and (walk_pass or holdout_pass):
            decision = "conditional_go"
        else:
            decision = "no_go"

        rows.append(
            {
                "model_variant": variant,
                "benchmark_variant": benchmark_variant,
                "overall_pass": overall_pass,
                "walk_forward_pass": walk_pass,
                "event_holdout_pass": holdout_pass,
                "decision": decision,
            }
        )
    return pd.DataFrame(rows).sort_values("model_variant").reset_index(drop=True)


def _render_summary_markdown(
    summary: Mapping[str, Any],
    overall: pd.DataFrame,
    wf_overall: pd.DataFrame,
    wf_worst_fold: pd.DataFrame,
    event_holdout_overall: pd.DataFrame,
    decision_summary: pd.DataFrame,
) -> str:
    lines = [
        "# Backtest Report",
        "",
        f"- Rows: {summary['row_count']}",
        f"- Prediction variants: {', '.join(summary['prediction_variants'])}",
        f"- Group fields: {', '.join(summary['group_fields']) or 'none'}",
        f"- Walk-forward folds: {summary['walk_forward_fold_count']}",
        f"- Event-holdout rows: {summary['event_holdout_rows']}",
        "",
        "## Overall Summary",
        "",
    ]
    lines.extend(_markdown_or_empty(overall, "- No overall rows."))
    lines.extend(["", "## Walk-Forward Overall Summary", ""])
    lines.extend(_markdown_or_empty(wf_overall, "- Walk-forward report not generated."))
    lines.extend(["", "## Walk-Forward Worst Fold Summary", ""])
    lines.extend(_markdown_or_empty(wf_worst_fold, "- Worst-fold report not generated."))
    lines.extend(["", "## Event-Holdout Overall Summary", ""])
    lines.extend(_markdown_or_empty(event_holdout_overall, "- Event-holdout report not generated."))
    lines.extend(["", "## Promotion Decision Summary", ""])
    lines.extend(_markdown_or_empty(decision_summary, "- Decision summary not generated."))
    return "\n".join(lines).rstrip() + "\n"


def _markdown_or_empty(frame: pd.DataFrame, empty_message: str) -> list[str]:
    if frame.empty:
        return [empty_message]
    return _markdown_table(frame)


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for header in headers:
            value = row[header]
            if isinstance(value, float):
                values.append(f"{value:.6f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _chunk_positions(positions: Sequence[int], chunk_count: int) -> list[list[int]]:
    if chunk_count <= 0:
        return []
    base, remainder = divmod(len(positions), chunk_count)
    chunks: list[list[int]] = []
    start = 0
    for idx in range(chunk_count):
        extra = 1 if idx < remainder else 0
        end = start + base + extra
        chunk = list(positions[start:end])
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


__all__ = [
    "BacktestGateConfig",
    "EventHoldoutConfig",
    "WalkForwardConfig",
    "WalkForwardSplit",
    "build_event_holdout_split",
    "build_walk_forward_splits",
    "compute_prediction_metrics",
    "generate_backtest_report",
    "hold_to_resolution_simulation",
]
