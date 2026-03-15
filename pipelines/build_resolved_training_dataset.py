"""Build supervised resolved-market datasets from snapshot rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from calibration.labeling import RESOLVED_FALSE, RESOLVED_TRUE
from features.external_enrichment import ExternalEnrichmentConfig, enrich_with_external_features
from features.market_templates import build_market_template_features

_RESOLUTION_CANDIDATES = ("resolution_ts", "end_ts", "event_end_ts")


@dataclass(frozen=True)
class ResolvedDatasetConfig:
    horizons_hours: tuple[int, ...] = (1, 6, 24, 72)
    time_col: str = "ts"
    include_template_features: bool = False
    external_enrichment: ExternalEnrichmentConfig | None = None
    sample_mode: str = "all_eligible"
    min_snapshot_spacing_minutes: int = 0
    max_samples_per_horizon: int | None = None


def build_resolved_training_dataset(
    rows: Sequence[Mapping[str, object]] | pd.DataFrame,
    config: ResolvedDatasetConfig | None = None,
) -> pd.DataFrame:
    frame = _coerce_frame(rows)
    if frame.empty:
        return pd.DataFrame()
    if "market_id" not in frame.columns:
        raise ValueError("rows must include 'market_id'")

    cfg = config or ResolvedDatasetConfig()
    work = frame.copy()
    work["_row_order"] = range(len(work))
    work["_snapshot_ts"] = pd.to_datetime(work[cfg.time_col], utc=True, errors="coerce")
    if work["_snapshot_ts"].isna().all():
        raise ValueError(f"rows must include a valid '{cfg.time_col}' column")
    work["_resolution_ts"] = _resolve_resolution_timestamps(work)
    work = work.loc[work["_snapshot_ts"].notna() & work["_resolution_ts"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for _, group in work.sort_values(["market_id", "_snapshot_ts", "_row_order"]).groupby("market_id", sort=True):
        label = _resolve_binary_label(group)
        if label is None:
            continue
        resolution_ts = group["_resolution_ts"].max()
        open_ts = group["_snapshot_ts"].min()
        prepared = group.copy()
        prepared["_snapshot_gap_minutes"] = (
            prepared["_snapshot_ts"].diff().dt.total_seconds().div(60.0).fillna(0.0)
        )
        for horizon in sorted({int(value) for value in cfg.horizons_hours if int(value) > 0}):
            cutoff = resolution_ts - pd.to_timedelta(horizon, unit="h")
            eligible = prepared.loc[prepared["_snapshot_ts"] <= cutoff]
            if eligible.empty:
                continue
            for sample_index, selected in enumerate(
                _select_samples_for_horizon(
                    eligible,
                    sample_mode=cfg.sample_mode,
                    min_snapshot_spacing_minutes=cfg.min_snapshot_spacing_minutes,
                    max_samples_per_horizon=cfg.max_samples_per_horizon,
                ),
                start=1,
            ):
                example = {
                    key: value
                    for key, value in selected.items()
                    if not str(key).startswith("_")
                }
                tte_minutes = max((resolution_ts - selected["_snapshot_ts"]).total_seconds() / 60.0, 0.0)
                example["snapshot_ts"] = selected["_snapshot_ts"].isoformat()
                example["resolution_ts"] = resolution_ts.isoformat()
                example["horizon_hours"] = horizon
                example["label"] = label
                example["sample_index"] = sample_index
                example["snapshot_gap_minutes"] = float(selected["_snapshot_gap_minutes"])
                example["age_since_open_minutes"] = float(
                    max((selected["_snapshot_ts"] - open_ts).total_seconds() / 60.0, 0.0)
                )
                example["tte_minutes"] = float(tte_minutes)
                example["tte_bucket"] = _tte_bucket(tte_minutes / 60.0)
                example["platform"] = str(example.get("platform") or "unknown")
                if "market_prob" not in example and "p_yes" in example:
                    example["market_prob"] = example["p_yes"]
                if cfg.include_template_features:
                    example.update(build_market_template_features(example))
                records.append(example)

    dataset = pd.DataFrame.from_records(records)
    if dataset.empty:
        return dataset
    dataset = dataset.sort_values(["market_id", "horizon_hours", "snapshot_ts"]).reset_index(drop=True)
    if cfg.external_enrichment is not None:
        dataset = enrich_with_external_features(dataset, cfg.external_enrichment)
    return dataset


def stage_build_resolved_training_dataset(context: Any) -> dict[str, int]:
    source = context.state.get("feature_frame")
    if source is None:
        source = context.state.get("features")
    if source is None:
        source = context.state.get("feature_rows")
    if source is None:
        source = context.state.get("cutoff_snapshots")
    config = ResolvedDatasetConfig(
        horizons_hours=tuple(int(value) for value in context.state.get("resolved_dataset_horizons", (1, 6, 24, 72))),
        include_template_features=bool(context.state.get("include_template_features", False)),
        sample_mode=str(context.state.get("resolved_dataset_sample_mode", "all_eligible")),
        min_snapshot_spacing_minutes=int(context.state.get("resolved_dataset_min_spacing_minutes", 0)),
        max_samples_per_horizon=(
            int(context.state["resolved_dataset_max_samples_per_horizon"])
            if context.state.get("resolved_dataset_max_samples_per_horizon") is not None
            else None
        ),
        external_enrichment=ExternalEnrichmentConfig(
            news_csv_path=str(context.state.get("news_csv_path") or "") or None,
            polls_csv_path=str(context.state.get("polls_csv_path") or "") or None,
        ) if context.state.get("news_csv_path") or context.state.get("polls_csv_path") else None,
    )
    dataset = build_resolved_training_dataset(source if source is not None else [], config=config)
    context.state["resolved_training_dataset"] = dataset
    return {"row_count": int(len(dataset))}


def _coerce_frame(rows: Sequence[Mapping[str, object]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame.from_records([dict(row) for row in rows])


def _resolve_resolution_timestamps(frame: pd.DataFrame) -> pd.Series:
    resolved = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    for column in _RESOLUTION_CANDIDATES:
        if column not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column], utc=True, errors="coerce")
        resolved = resolved.where(resolved.notna(), parsed)
    return resolved


def _resolve_binary_label(group: pd.DataFrame) -> int | None:
    if "label" in group.columns:
        labels = pd.to_numeric(group["label"], errors="coerce").dropna()
        for value in labels.tolist():
            if value in (0, 1):
                return int(value)

    if "label_status" not in group.columns:
        return None
    statuses = group["label_status"].astype("string").str.upper()
    if (statuses == RESOLVED_TRUE).any():
        return 1
    if (statuses == RESOLVED_FALSE).any():
        return 0
    return None


def _select_samples_for_horizon(
    eligible: pd.DataFrame,
    *,
    sample_mode: str,
    min_snapshot_spacing_minutes: int,
    max_samples_per_horizon: int | None,
) -> list[pd.Series]:
    ordered = eligible.sort_values("_snapshot_ts", kind="mergesort")
    mode = str(sample_mode).strip().lower()
    if mode not in {"all_eligible", "latest_only"}:
        raise ValueError(f"Unsupported sample_mode: {sample_mode}")

    if mode == "latest_only":
        return [ordered.iloc[-1]]

    selected: list[pd.Series] = []
    spacing = max(int(min_snapshot_spacing_minutes), 0)
    last_kept_ts = None
    for _, row in ordered.iloc[::-1].iterrows():
        snapshot_ts = row["_snapshot_ts"]
        if last_kept_ts is not None and spacing > 0:
            delta_minutes = (last_kept_ts - snapshot_ts).total_seconds() / 60.0
            if delta_minutes < spacing:
                continue
        selected.append(row)
        last_kept_ts = snapshot_ts
        if max_samples_per_horizon is not None and len(selected) >= int(max_samples_per_horizon):
            break
    return list(reversed(selected))


def _tte_bucket(tte_hours: float) -> str:
    if tte_hours <= 6:
        return "0-6h"
    if tte_hours <= 24:
        return "6-24h"
    if tte_hours <= 72:
        return "24-72h"
    return "72h+"


__all__ = [
    "ResolvedDatasetConfig",
    "build_resolved_training_dataset",
    "stage_build_resolved_training_dataset",
]
