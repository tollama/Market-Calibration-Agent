"""Lightweight offline trainer for resolved-market datasets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from calibration.metrics import brier_score, summarize_metrics_extended
from features.external_enrichment import ExternalEnrichmentConfig, enrich_with_external_features
from pipelines.build_resolved_training_dataset import (
    ResolvedDatasetConfig,
    build_resolved_training_dataset,
)
from pipelines.generate_backtest_report import WalkForwardConfig, generate_backtest_report

_NUMERIC_CANDIDATES = (
    "market_prob",
    "p_yes",
    "returns",
    "vol",
    "volume_velocity",
    "oi_change",
    "tte_seconds",
    "liquidity_bucket_id",
    "horizon_hours",
    "template_confidence",
    "template_entity_count",
    "news_articles_24h",
    "news_articles_72h",
    "news_recentness_hours",
    "poll_yes_support",
    "poll_margin",
    "poll_count_30d",
    "poll_days_since_last",
    "poll_match_quality",
)
_CATEGORICAL_CANDIDATES = (
    "category",
    "liquidity_bucket",
    "template_group",
    "market_template",
    "poll_mode",
)


@dataclass(frozen=True)
class ResolvedModelConfig:
    alpha: float = 1.0
    validation_fraction: float = 0.2
    min_validation_rows: int = 10
    blend_grid_size: int = 21


@dataclass
class ResolvedModelMetrics:
    train_rows: int
    validation_rows: int
    brier_model: float
    brier_blended: float
    blend_weight_model: float
    feature_count: int


class ResolvedLinearModel:
    def __init__(self, config: ResolvedModelConfig | None = None) -> None:
        self.config = config or ResolvedModelConfig()
        self.numeric_features: list[str] = []
        self.categorical_features: list[str] = []
        self.category_levels: dict[str, list[str]] = {}
        self.numeric_fill: dict[str, float] = {}
        self.numeric_mean: dict[str, float] = {}
        self.numeric_scale: dict[str, float] = {}
        self.feature_names: list[str] = []
        self.coefficients: list[float] = []
        self.intercept: float = 0.0
        self.blend_weight_model: float = 1.0
        self.metrics: ResolvedModelMetrics | None = None

    def fit(self, frame: pd.DataFrame, *, label_col: str = "label") -> ResolvedModelMetrics:
        work = frame.copy()
        if label_col not in work.columns:
            raise ValueError(f"frame must include '{label_col}'")
        if work.empty:
            raise ValueError("frame must be non-empty")

        work = work.loc[pd.to_numeric(work[label_col], errors="coerce").isin([0, 1])].copy()
        if work.empty:
            raise ValueError("frame contains no binary labeled rows")

        self._select_features(work)
        ordered = self._order_for_validation(work)
        validation_rows = max(int(len(ordered) * float(self.config.validation_fraction)), 0)
        if len(ordered) >= self.config.min_validation_rows * 2:
            validation_rows = max(validation_rows, self.config.min_validation_rows)
        else:
            validation_rows = 0

        if validation_rows > 0:
            train = ordered.iloc[:-validation_rows].copy()
            validation = ordered.iloc[-validation_rows:].copy()
        else:
            train = ordered
            validation = ordered.iloc[0:0].copy()

        X_train = self._fit_transform(train)
        y_train = train[label_col].astype(float).to_numpy()
        self._fit_linear_weights(X_train, y_train)

        train_pred = self.predict_proba(train)
        model_brier = brier_score(train_pred.tolist(), y_train.tolist())
        blended_brier = model_brier
        self.blend_weight_model = 1.0

        if not validation.empty:
            validation_y = validation[label_col].astype(int).tolist()
            validation_model = self.predict_proba(validation).tolist()
            market_prob = _market_prob_series(validation).tolist()
            self.blend_weight_model = _select_blend_weight(
                validation_model,
                market_prob,
                validation_y,
                grid_size=self.config.blend_grid_size,
            )
            blended = _blend_predictions(validation_model, market_prob, self.blend_weight_model)
            model_brier = brier_score(validation_model, validation_y)
            blended_brier = brier_score(blended, validation_y)

        self.metrics = ResolvedModelMetrics(
            train_rows=int(len(train)),
            validation_rows=int(len(validation)),
            brier_model=float(model_brier),
            brier_blended=float(blended_brier),
            blend_weight_model=float(self.blend_weight_model),
            feature_count=int(len(self.feature_names)),
        )
        return self.metrics

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if not self.feature_names:
            raise ValueError("model has not been fit")
        X = self._transform(frame)
        raw = X @ np.asarray(self.coefficients, dtype=float) + float(self.intercept)
        return np.clip(raw, 0.0, 1.0)

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        market_prob = _market_prob_series(frame)
        pred = self.predict_proba(frame)
        recalibrated = _blend_predictions(pred.tolist(), market_prob.tolist(), self.blend_weight_model)
        return pd.DataFrame(
            {
                "pred": pred,
                "baseline_pred": market_prob,
                "recalibrated_pred": recalibrated,
            },
            index=frame.index,
        )

    def save(self, path: str | Path) -> None:
        payload = {
            "config": asdict(self.config),
            "numeric_features": self.numeric_features,
            "categorical_features": self.categorical_features,
            "category_levels": self.category_levels,
            "numeric_fill": self.numeric_fill,
            "numeric_mean": self.numeric_mean,
            "numeric_scale": self.numeric_scale,
            "feature_names": self.feature_names,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "blend_weight_model": self.blend_weight_model,
            "metrics": asdict(self.metrics) if self.metrics is not None else None,
        }
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ResolvedLinearModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        model = cls(ResolvedModelConfig(**payload["config"]))
        model.numeric_features = list(payload.get("numeric_features", []))
        model.categorical_features = list(payload.get("categorical_features", []))
        model.category_levels = {
            str(key): [str(value) for value in values]
            for key, values in payload.get("category_levels", {}).items()
        }
        model.numeric_fill = {str(k): float(v) for k, v in payload.get("numeric_fill", {}).items()}
        model.numeric_mean = {str(k): float(v) for k, v in payload.get("numeric_mean", {}).items()}
        model.numeric_scale = {str(k): float(v) for k, v in payload.get("numeric_scale", {}).items()}
        model.feature_names = [str(value) for value in payload.get("feature_names", [])]
        model.coefficients = [float(value) for value in payload.get("coefficients", [])]
        model.intercept = float(payload.get("intercept", 0.0))
        model.blend_weight_model = float(payload.get("blend_weight_model", 1.0))
        if payload.get("metrics") is not None:
            model.metrics = ResolvedModelMetrics(**payload["metrics"])
        return model

    def _select_features(self, frame: pd.DataFrame) -> None:
        self.numeric_features = [column for column in _NUMERIC_CANDIDATES if column in frame.columns]
        if "market_prob" not in self.numeric_features and "p_yes" in frame.columns:
            self.numeric_features.insert(0, "p_yes")
        self.categorical_features = [column for column in _CATEGORICAL_CANDIDATES if column in frame.columns]

    def _order_for_validation(self, frame: pd.DataFrame) -> pd.DataFrame:
        for column in ("snapshot_ts", "ts", "resolution_ts"):
            if column in frame.columns:
                ordered = frame.copy()
                ordered["_sort"] = pd.to_datetime(frame[column], utc=True, errors="coerce")
                ordered = ordered.sort_values(["_sort"], kind="mergesort")
                return ordered.drop(columns=["_sort"])
        return frame.reset_index(drop=True)

    def _fit_transform(self, frame: pd.DataFrame) -> np.ndarray:
        numeric_parts: list[np.ndarray] = []
        self.numeric_fill = {}
        self.numeric_mean = {}
        self.numeric_scale = {}
        for column in self.numeric_features:
            series = _coerce_numeric_series(frame, column)
            fill = float(series.median()) if series.notna().any() else 0.0
            filled = series.fillna(fill)
            mean = float(filled.mean())
            scale = float(filled.std(ddof=0))
            if scale == 0.0:
                scale = 1.0
            self.numeric_fill[column] = fill
            self.numeric_mean[column] = mean
            self.numeric_scale[column] = scale
            numeric_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        categorical_parts: list[np.ndarray] = []
        self.category_levels = {}
        for column in self.categorical_features:
            series = frame.get(column).astype("string").fillna("__missing__")
            levels = sorted(series.unique().tolist())
            self.category_levels[column] = levels
            dummies = pd.get_dummies(series, prefix=column)
            dummies = dummies.reindex(columns=[f"{column}_{level}" for level in levels], fill_value=0)
            categorical_parts.append(dummies.to_numpy(dtype=float))

        matrices = [part for part in numeric_parts + categorical_parts if part.size > 0]
        X = np.concatenate(matrices, axis=1) if matrices else np.zeros((len(frame), 0), dtype=float)
        self.feature_names = [*self.numeric_features]
        for column in self.categorical_features:
            self.feature_names.extend([f"{column}_{level}" for level in self.category_levels[column]])
        return X

    def _transform(self, frame: pd.DataFrame) -> np.ndarray:
        numeric_parts: list[np.ndarray] = []
        for column in self.numeric_features:
            series = _coerce_numeric_series(frame, column)
            fill = self.numeric_fill.get(column, 0.0)
            mean = self.numeric_mean.get(column, 0.0)
            scale = self.numeric_scale.get(column, 1.0)
            filled = series.fillna(fill)
            numeric_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        categorical_parts: list[np.ndarray] = []
        for column in self.categorical_features:
            levels = self.category_levels.get(column, [])
            series = frame.get(column).astype("string").fillna("__missing__")
            dummies = pd.get_dummies(series, prefix=column)
            dummies = dummies.reindex(columns=[f"{column}_{level}" for level in levels], fill_value=0)
            categorical_parts.append(dummies.to_numpy(dtype=float))
        matrices = [part for part in numeric_parts + categorical_parts if part.size > 0]
        return np.concatenate(matrices, axis=1) if matrices else np.zeros((len(frame), 0), dtype=float)

    def _fit_linear_weights(self, X: np.ndarray, y: np.ndarray) -> None:
        if X.ndim != 2:
            raise ValueError("X must be 2-dimensional")
        X_design = np.concatenate([np.ones((len(X), 1), dtype=float), X], axis=1)
        ridge = np.eye(X_design.shape[1], dtype=float) * float(self.config.alpha)
        ridge[0, 0] = 0.0
        lhs = X_design.T @ X_design + ridge
        rhs = X_design.T @ y
        coeff = np.linalg.pinv(lhs) @ rhs
        self.intercept = float(coeff[0])
        self.coefficients = [float(value) for value in coeff[1:]]


def train_resolved_model(
    rows: pd.DataFrame,
    *,
    model_config: ResolvedModelConfig | None = None,
) -> tuple[ResolvedLinearModel, pd.DataFrame, dict[str, Any]]:
    model = ResolvedLinearModel(model_config)
    metrics = model.fit(rows)
    predictions = pd.concat([rows.reset_index(drop=True), model.predict_frame(rows).reset_index(drop=True)], axis=1)
    summary = {
        **asdict(metrics),
        "metric_bundle": summarize_metrics_extended(
            predictions["recalibrated_pred"].tolist(),
            predictions["label"].astype(int).tolist(),
        ),
    }
    return model, predictions, summary


def run_training_workflow(
    *,
    input_path: Path,
    output_dir: Path,
    model_path: Path,
    report_dir: Path | None = None,
    dataset_path: Path | None = None,
    horizons: Sequence[int] = (1, 6, 24, 72),
    include_template_features: bool = True,
    news_csv_path: str | None = None,
    polls_csv_path: str | None = None,
    alpha: float = 1.0,
) -> dict[str, Any]:
    rows = _load_table(input_path)
    dataset = build_resolved_training_dataset(
        rows,
        config=ResolvedDatasetConfig(
            horizons_hours=tuple(int(value) for value in horizons),
            include_template_features=include_template_features,
        ),
    )
    if news_csv_path or polls_csv_path:
        dataset = enrich_with_external_features(
            dataset,
            ExternalEnrichmentConfig(
                news_csv_path=news_csv_path,
                polls_csv_path=polls_csv_path,
            ),
        )
    model, predictions, summary = train_resolved_model(
        dataset,
        model_config=ResolvedModelConfig(alpha=float(alpha)),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    predictions_path = output_dir / "resolved_model_predictions.csv"
    predictions.to_csv(predictions_path, index=False)
    if dataset_path is not None:
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_csv(dataset_path, index=False)
    report_summary: dict[str, Any] | None = None
    if report_dir is not None:
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
        )

    payload = {
        "input_path": str(input_path),
        "row_count": int(len(dataset)),
        "model_path": str(model_path),
        "predictions_path": str(predictions_path),
        "summary": summary,
        "report": report_summary,
    }
    summary_path = output_dir / "resolved_model_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    return payload


def _market_prob_series(frame: pd.DataFrame) -> pd.Series:
    if "market_prob" in frame.columns:
        return pd.to_numeric(frame["market_prob"], errors="coerce").fillna(0.5).clip(0.0, 1.0)
    return pd.to_numeric(frame.get("p_yes"), errors="coerce").fillna(0.5).clip(0.0, 1.0)


def _coerce_numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        source = frame[column]
    else:
        source = pd.Series([float("nan")] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(source, errors="coerce")


def _blend_predictions(
    model_pred: Sequence[float],
    market_pred: Sequence[float],
    weight_model: float,
) -> list[float]:
    weight_market = 1.0 - float(weight_model)
    return [
        min(max(float(weight_model) * float(model) + weight_market * float(market), 0.0), 1.0)
        for model, market in zip(model_pred, market_pred)
    ]


def _select_blend_weight(
    model_pred: Sequence[float],
    market_pred: Sequence[float],
    labels: Sequence[int],
    *,
    grid_size: int,
) -> float:
    best_weight = 1.0
    best_brier = float("inf")
    for step in range(max(2, int(grid_size))):
        weight = step / (max(2, int(grid_size)) - 1)
        blended = _blend_predictions(model_pred, market_pred, weight)
        score = brier_score(blended, labels)
        if score < best_brier:
            best_brier = score
            best_weight = weight
    return float(best_weight)


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a lightweight resolved-market baseline model")
    parser.add_argument("--input", required=True, help="snapshot input path (csv/parquet/jsonl)")
    parser.add_argument("--output-dir", default="artifacts/resolved_model")
    parser.add_argument("--model-path", default="artifacts/resolved_model/model.json")
    parser.add_argument("--dataset-path", default="", help="optional dataset csv output path")
    parser.add_argument("--report-dir", default="", help="optional backtest report output dir")
    parser.add_argument("--horizon", action="append", dest="horizons", type=int, default=[1, 6, 24, 72])
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--no-template-features", action="store_true")
    parser.add_argument("--news-csv", default="")
    parser.add_argument("--polls-csv", default="")
    args = parser.parse_args()

    payload = run_training_workflow(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        model_path=Path(args.model_path),
        report_dir=Path(args.report_dir) if args.report_dir else None,
        dataset_path=Path(args.dataset_path) if args.dataset_path else None,
        horizons=list(dict.fromkeys(int(value) for value in args.horizons)),
        include_template_features=not bool(args.no_template_features),
        news_csv_path=str(args.news_csv or "") or None,
        polls_csv_path=str(args.polls_csv or "") or None,
        alpha=float(args.alpha),
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
