#!/usr/bin/env python3
"""Generate a forecasting artifact pack from locally available resolved-market data."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.prediction_market_normalization import augment_prediction_market_context
from pipelines.generate_backtest_report import EventHoldoutConfig, WalkForwardConfig, generate_backtest_report
from pipelines.train_resolved_model import (
    ResolvedModelConfig,
    ResolvedLinearModel,
    run_feature_ablation,
    train_resolved_model,
)
from scripts.evaluate_forecasting_promotion_gate import evaluate_promotion_gate

_RAW_REQUIRED = ("market_id",)
_RAW_TIME_COLUMNS = ("ts",)
_RAW_RESOLUTION_COLUMNS = ("resolution_ts", "end_ts", "event_end_ts")
_RAW_LABEL_COLUMNS = ("label", "label_status")

_DATASET_REQUIRED = ("market_id", "snapshot_ts", "resolution_ts", "label")

_CANDIDATE_PATTERNS = (
    "data/**/*.parquet",
    "data/**/*.csv",
    "data/**/*.jsonl",
    "artifacts/**/*.parquet",
    "artifacts/**/*.csv",
    "artifacts/**/*.jsonl",
)

_PATH_HINTS = (
    "resolved",
    "snapshot",
    "feature",
    "training",
    "offline_eval_input",
)


@dataclass(frozen=True)
class CandidateInfo:
    path: str
    row_count: int
    columns: list[str]
    kind: str


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {path}")


def _classify_frame(frame: pd.DataFrame) -> str | None:
    columns = set(frame.columns.astype(str).tolist())
    if all(column in columns for column in _DATASET_REQUIRED):
        return "dataset"
    if all(column in columns for column in _RAW_REQUIRED) and any(column in columns for column in _RAW_TIME_COLUMNS):
        if any(column in columns for column in _RAW_RESOLUTION_COLUMNS) and any(column in columns for column in _RAW_LABEL_COLUMNS):
            return "raw_snapshot_rows"
    return None


def _candidate_from_frame(path: Path, frame: pd.DataFrame) -> CandidateInfo | None:
    kind = _classify_frame(frame)
    if kind is None:
        return None
    return CandidateInfo(
        path=str(path),
        row_count=int(len(frame)),
        columns=[str(column) for column in frame.columns.tolist()],
        kind=kind,
    )


def _discover_candidates(root: Path) -> list[CandidateInfo]:
    candidates: list[CandidateInfo] = []
    seen: set[Path] = set()
    for pattern in _CANDIDATE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            lowered = str(path).lower()
            if not any(token in lowered for token in _PATH_HINTS):
                continue
            try:
                frame = _load_table(path)
            except Exception:
                continue
            candidate = _candidate_from_frame(path, frame)
            if candidate is None:
                continue
            candidates.append(candidate)
    candidates.sort(key=lambda item: (0 if item.kind == "raw_snapshot_rows" else 1, -item.row_count, item.path))
    return candidates


def _explicit_candidate(path: Path) -> tuple[CandidateInfo | None, pd.DataFrame | None, str | None]:
    if not path.exists():
        return None, None, f"Input path does not exist: {path}"
    try:
        frame = _load_table(path)
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Failed to load input path {path}: {exc}"
    candidate = _candidate_from_frame(path, frame)
    if candidate is None:
        return None, frame, (
            "Input path loaded successfully but does not match an accepted schema. "
            "Expected raw snapshot rows with `market_id`, `ts`, resolution timestamp, and `label`/`label_status`, "
            "or resolved dataset rows with `market_id`, `snapshot_ts`, `resolution_ts`, and `label`."
        )
    return candidate, frame, None


def _train_from_dataset(dataset: pd.DataFrame) -> tuple[ResolvedLinearModel, pd.DataFrame, dict[str, Any], pd.DataFrame]:
    model, predictions, summary = train_resolved_model(
        dataset,
        model_config=ResolvedModelConfig(
            target_mode="residual",
            use_horizon_interactions=True,
            feature_group_grid=(),
        ),
    )
    ablation = run_feature_ablation(
        dataset,
        model_config=ResolvedModelConfig(
            target_mode="residual",
            use_horizon_interactions=True,
            feature_group_grid=(),
        ),
    )
    return model, predictions, summary, ablation


def _dataset_summary(dataset: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rows": int(len(dataset)),
        "markets": int(dataset["market_id"].nunique()) if "market_id" in dataset.columns else 0,
        "platforms": sorted(dataset["platform"].dropna().astype(str).unique().tolist()) if "platform" in dataset.columns else [],
        "categories": sorted(dataset["category"].dropna().astype(str).unique().tolist()) if "category" in dataset.columns else [],
        "canonical_categories": sorted(dataset["canonical_category"].dropna().astype(str).unique().tolist()) if "canonical_category" in dataset.columns else [],
        "market_structures": sorted(dataset["market_structure"].dropna().astype(str).unique().tolist()) if "market_structure" in dataset.columns else [],
        "liquidity_buckets": sorted(dataset["liquidity_bucket"].dropna().astype(str).unique().tolist()) if "liquidity_bucket" in dataset.columns else [],
        "tte_buckets": sorted(dataset["tte_bucket"].dropna().astype(str).unique().tolist()) if "tte_bucket" in dataset.columns else [],
        "horizons_hours": sorted(pd.to_numeric(dataset["horizon_hours"], errors="coerce").dropna().astype(int).unique().tolist()) if "horizon_hours" in dataset.columns else [],
    }
    return summary


def _clean_resolved_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if dataset.empty:
        return dataset, {"excluded_rows": 0, "reasons": {}}

    dataset = augment_prediction_market_context(dataset)
    excluded = pd.Series(False, index=dataset.index)
    reasons: dict[str, int] = {}

    if "category" in dataset.columns:
        category_mask = dataset["category"].astype("string").str.lower().eq("test")
        if category_mask.any():
            excluded |= category_mask
            reasons["category:test"] = int(category_mask.sum())

    if "title" in dataset.columns:
        title_series = dataset["title"].astype("string").fillna("").str.lower().str.strip()
        title_mask = title_series.str.startswith("test, do not trade") | title_series.str.startswith("daily market")
        if title_mask.any():
            excluded |= title_mask
            reasons["title:test_or_daily_market"] = int(title_mask.sum())

    if "market_structure" in dataset.columns:
        structure_mask = ~dataset["market_structure"].astype("string").isin(["standard_binary", "player_prop"])
        if structure_mask.any():
            excluded |= structure_mask
            reasons["market_structure:non_standard"] = int(structure_mask.sum())

    cleaned = dataset.loc[~excluded].reset_index(drop=True)
    summary = {
        "excluded_rows": int(excluded.sum()),
        "reasons": reasons,
    }
    return cleaned, summary


def _render_success_readme(
    *,
    selected: CandidateInfo,
    dataset_summary: dict[str, Any],
    cleaning_summary: dict[str, Any],
    training_summary: dict[str, Any],
    promotion: dict[str, Any],
    report_summary: dict[str, Any],
) -> str:
    categories = ", ".join(dataset_summary.get("categories", [])) or "none"
    canonical_categories = ", ".join(dataset_summary.get("canonical_categories", [])) or "none"
    platforms = ", ".join(dataset_summary.get("platforms", [])) or "none"
    market_structures = ", ".join(dataset_summary.get("market_structures", [])) or "none"
    liquidity_buckets = ", ".join(dataset_summary.get("liquidity_buckets", [])) or "none"
    tte_buckets = ", ".join(dataset_summary.get("tte_buckets", [])) or "none"
    recommended = ", ".join(promotion.get("recommended_variants", [])) or "none"
    blocked = ", ".join(promotion.get("blocked_variants", [])) or "none"
    conditional = ", ".join(promotion.get("conditional_variants", [])) or "none"
    return (
        "\n".join(
            [
                "# Real-Data Forecasting Pack",
                "",
                f"Selected input: `{selected.path}`",
                f"Input kind: `{selected.kind}`",
                "",
                "Dataset summary:",
                f"- rows: `{dataset_summary.get('rows', 0)}`",
                f"- markets: `{dataset_summary.get('markets', 0)}`",
                f"- platforms: `{platforms}`",
                f"- categories: `{categories}`",
                f"- canonical categories: `{canonical_categories}`",
                f"- market structures: `{market_structures}`",
                f"- liquidity buckets: `{liquidity_buckets}`",
                f"- tte buckets: `{tte_buckets}`",
                f"- excluded rows during cleaning: `{cleaning_summary.get('excluded_rows', 0)}`",
                "",
                "Training summary:",
                f"- feature count: `{training_summary.get('feature_count', 0)}`",
                f"- target mode: `{training_summary.get('target_mode', 'unknown')}`",
                f"- baseline brier: `{training_summary.get('brier_baseline', 'n/a')}`",
                f"- blended brier: `{training_summary.get('brier_blended', 'n/a')}`",
                "",
                "Promotion summary:",
                f"- overall decision: `{promotion.get('overall_decision', 'unknown')}`",
                f"- gate passed: `{promotion.get('gate_passed', False)}`",
                f"- recommended variants: `{recommended}`",
                f"- conditional variants: `{conditional}`",
                f"- blocked variants: `{blocked}`",
                "",
                "Backtest summary:",
                f"- event holdout rows: `{report_summary.get('event_holdout_rows', 0)}`",
                f"- walk-forward folds: `{report_summary.get('walk_forward_fold_count', 0)}`",
                f"- prediction variants: `{', '.join(report_summary.get('prediction_variants', [])) or 'none'}`",
                "",
                "Outputs:",
                "- `status.json`",
                "- `discovery_manifest.json`",
                "- `dataset_summary.json`",
                "- `promotion_decision.json`",
                "- `dataset/dataset.csv`",
                "- `resolved_model/`",
                "- `backtest_report/`",
            ]
        )
        + "\n"
    )


def _write_blocked_pack(
    output_dir: Path,
    *,
    candidates: list[CandidateInfo],
    reason: str | None = None,
    selected_input: CandidateInfo | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "blocked_no_local_resolved_data",
        "reason": reason or "No local resolved snapshot rows or resolved dataset tables were found in data/ or artifacts/.",
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    if selected_input is not None:
        payload["selected_input"] = asdict(selected_input)
    (output_dir / "status.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "discovery_manifest.json").write_text(
        json.dumps({"candidates": [asdict(candidate) for candidate in candidates]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# Real-Data Forecasting Pack",
                "",
                "Status: blocked.",
                "",
                "No local resolved-market training input was found in this workspace.",
                "See `status.json` and `discovery_manifest.json` for the discovery result.",
                "",
                "Accepted input shapes:",
                "- raw snapshot rows with `market_id`, `ts`, resolution timestamp, and `label` or `label_status`",
                "- resolved dataset rows with `market_id`, `snapshot_ts`, `resolution_ts`, and `label`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def generate_real_data_pack(
    output_dir: Path,
    *,
    search_root: Path = ROOT,
    input_path: Path | None = None,
) -> dict[str, Any]:
    if input_path is not None:
        selected, frame, error = _explicit_candidate(input_path)
        candidates = [selected] if selected is not None else []
        if error is not None or selected is None or frame is None:
            return _write_blocked_pack(
                output_dir,
                candidates=candidates,
                reason=error,
                selected_input=selected,
            )
    else:
        candidates = _discover_candidates(search_root)
        if not candidates:
            return _write_blocked_pack(output_dir, candidates=[])
        selected = candidates[0]
        frame = _load_table(Path(selected.path))

    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = output_dir / "resolved_model"
    report_dir = output_dir / "backtest_report"
    dataset_dir = output_dir / "dataset"

    if selected.kind == "dataset":
        dataset = frame.copy()
    else:
        from pipelines.build_resolved_training_dataset import ResolvedDatasetConfig, build_resolved_training_dataset

        dataset = build_resolved_training_dataset(
            frame,
            config=ResolvedDatasetConfig(
                horizons_hours=(1, 6, 24, 72),
                include_template_features=True,
            ),
        )

    dataset, cleaning_summary = _clean_resolved_dataset(dataset)
    if dataset.empty:
        return _write_blocked_pack(
            output_dir,
            candidates=candidates,
            reason="Selected input produced an empty resolved dataset after filtering and horizon construction.",
            selected_input=selected,
        )

    model, predictions, summary, ablation = _train_from_dataset(dataset)
    model_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.json"
    predictions_path = model_dir / "resolved_model_predictions.csv"
    ablation_path = model_dir / "feature_ablation_summary.csv"
    dataset_path = dataset_dir / "dataset.csv"

    model.save(model_path)
    predictions.to_csv(predictions_path, index=False)
    ablation.to_csv(ablation_path, index=False)
    dataset.to_csv(dataset_path, index=False)

    report_summary = generate_backtest_report(
        predictions,
        report_dir=report_dir,
        prediction_columns={
            "market": "baseline_pred",
            "primary": "pred",
            "recalibrated": "recalibrated_pred",
        },
        walk_forward=WalkForwardConfig(
            n_splits=4,
            initial_train_fraction=0.5,
            min_train_rows=10,
            min_test_rows=5,
            time_col="snapshot_ts",
            label_available_col="resolution_ts",
        ),
        event_holdout=EventHoldoutConfig(
            holdout_fraction=0.2,
            min_test_rows=5,
            seed=42,
        ),
    )
    promotion = evaluate_promotion_gate(report_dir / "decision_summary.csv")

    dataset_summary = _dataset_summary(dataset)
    manifest = {
        "status": "ok",
        "selected_input": asdict(selected),
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
        "dataset_summary": dataset_summary,
        "cleaning_summary": cleaning_summary,
        "training_summary": summary,
        "report_summary": report_summary,
        "promotion": promotion,
    }
    (output_dir / "status.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "discovery_manifest.json").write_text(
        json.dumps({"candidates": [asdict(candidate) for candidate in candidates]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "promotion_decision.json").write_text(json.dumps(promotion, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "dataset_summary.json").write_text(
        json.dumps(dataset_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        _render_success_readme(
            selected=selected,
            dataset_summary=dataset_summary,
            cleaning_summary=cleaning_summary,
            training_summary=summary,
            promotion=promotion,
            report_summary=report_summary,
        ),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate forecasting artifact pack from local resolved-market data")
    parser.add_argument("--input", default="", help="explicit resolved input path (csv/parquet/jsonl)")
    parser.add_argument("--search-root", default="", help="optional root directory for input discovery")
    parser.add_argument(
        "--output-dir",
        default="artifacts/forecasting_baseline_pack/real_data_v1",
        help="artifact output directory",
    )
    args = parser.parse_args()
    result = generate_real_data_pack(
        Path(args.output_dir),
        search_root=Path(args.search_root) if args.search_root else ROOT,
        input_path=Path(args.input) if args.input else None,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
