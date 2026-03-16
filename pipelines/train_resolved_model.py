"""Lightweight offline trainer for resolved-market datasets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from calibration.metrics import brier_score, log_loss, summarize_metrics_extended
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
    "returns_3",
    "returns_6",
    "vol",
    "vol_3",
    "vol_12",
    "price_acceleration",
    "reversal_signal",
    "volume_velocity",
    "volume_acceleration",
    "oi_change",
    "oi_acceleration",
    "gap_minutes",
    "stale_gap_flag",
    "tte_seconds",
    "tte_hours",
    "price_distance_mid",
    "liquidity_bucket_id",
    "horizon_hours",
    "template_confidence",
    "template_entity_count",
    "news_articles_24h",
    "news_articles_72h",
    "news_recentness_hours",
    "news_match_quality",
    "news_weighted_count_72h",
    "poll_yes_support",
    "poll_margin",
    "poll_margin_abs",
    "poll_count_30d",
    "poll_days_since_last",
    "poll_match_quality",
    "poll_recency_weight",
    "event_market_count",
    "event_consensus_p_yes",
    "event_disagreement_abs",
    "event_price_dispersion",
    "cross_platform_count",
    "cross_platform_disagreement_abs",
    "event_relative_rank",
)
_CATEGORICAL_CANDIDATES = (
    "category",
    "canonical_category",
    "liquidity_bucket",
    "tte_bucket",
    "template_group",
    "market_template",
    "poll_mode",
    "platform",
    "platform_category",
    "market_structure",
)
_FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "market": ("market_prob", "p_yes"),
    "price_action": ("returns", "returns_3", "returns_6", "vol", "vol_3", "vol_12", "price_acceleration", "reversal_signal", "price_distance_mid"),
    "liquidity_flow": ("volume_velocity", "volume_acceleration", "oi_change", "oi_acceleration", "liquidity_bucket_id", "liquidity_bucket"),
    "time_to_event": ("tte_seconds", "tte_hours", "tte_bucket", "gap_minutes", "stale_gap_flag", "horizon_hours"),
    "template": ("template_confidence", "template_entity_count", "template_group", "market_template"),
    "external_news": ("news_articles_24h", "news_articles_72h", "news_recentness_hours", "news_match_quality", "news_weighted_count_72h"),
    "external_polls": ("poll_yes_support", "poll_margin", "poll_margin_abs", "poll_count_30d", "poll_days_since_last", "poll_match_quality", "poll_recency_weight", "poll_mode"),
    "event_structure": ("event_market_count", "event_consensus_p_yes", "event_disagreement_abs", "event_price_dispersion", "cross_platform_count", "cross_platform_disagreement_abs", "event_relative_rank", "platform"),
    "categorical_context": ("category", "canonical_category", "platform_category", "market_structure"),
}


@dataclass(frozen=True)
class ResolvedModelConfig:
    alpha: float = 1.0
    alpha_grid: tuple[float, ...] = (0.25, 1.0, 4.0, 16.0, 64.0)
    validation_fraction: float = 0.2
    min_validation_rows: int = 10
    validation_windows: int = 3
    blend_grid_size: int = 21
    min_categorical_level_count: int = 2
    selection_metric: str = "joint"
    drop_feature_groups: tuple[str, ...] = ()
    feature_group_grid: tuple[str, ...] = (
        "all_features",
        "drop:time_to_event",
    )
    target_mode: str = "direct"
    use_horizon_interactions: bool = False
    sample_weight_scheme: str = "none"
    sample_weight_key: str = "platform_category"
    sample_weight_power: float = 0.5
    sample_weight_min: float = 0.5
    sample_weight_cap: float = 3.0


@dataclass
class ResolvedModelMetrics:
    train_rows: int
    validation_rows: int
    validation_windows: int
    target_mode: str
    brier_model: float
    brier_blended: float
    brier_baseline: float
    blend_weight_model: float
    selected_alpha: float
    validation_objective: float
    selected_drop_feature_groups: list[str]
    feature_count: int
    sample_weight_scheme: str
    sample_weight_key: str


@dataclass(frozen=True)
class SegmentRoutingConfig:
    strategy: str = "none"
    route_key: str = "canonical_category"
    min_segment_rows: int = 150
    gate_min_windows: int = 2
    gate_min_improvement: float = 0.0
    gate_worst_case_tolerance: float = 0.01


class ResolvedLinearModel:
    def __init__(self, config: ResolvedModelConfig | None = None) -> None:
        self.config = config or ResolvedModelConfig()
        self.numeric_features: list[str] = []
        self.categorical_features: list[str] = []
        self.category_levels: dict[str, list[str]] = {}
        self.numeric_fill: dict[str, float] = {}
        self.numeric_mean: dict[str, float] = {}
        self.numeric_scale: dict[str, float] = {}
        self.interaction_sources: list[tuple[str, str]] = []
        self.interaction_fill: dict[str, float] = {}
        self.interaction_mean: dict[str, float] = {}
        self.interaction_scale: dict[str, float] = {}
        self.feature_names: list[str] = []
        self.coefficients: list[float] = []
        self.intercept: float = 0.0
        self.blend_weight_model: float = 1.0
        self.selected_alpha: float = float(self.config.alpha)
        self.selected_drop_feature_groups: tuple[str, ...] = tuple(str(value) for value in self.config.drop_feature_groups)
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

        validation_windows = self._build_validation_windows(ordered, validation_rows)
        self.blend_weight_model = 1.0
        validation_objective = float("nan")

        if validation_windows:
            best_alpha, best_blend, best_drop_groups, validation_metrics = self._select_alpha_and_blend(
                ordered,
                validation_windows=validation_windows,
                label_col=label_col,
            )
            self.selected_alpha = float(best_alpha)
            self.blend_weight_model = float(best_blend)
            self.selected_drop_feature_groups = tuple(best_drop_groups)
            validation_objective = float(validation_metrics["objective"])
            model_brier = float(validation_metrics["brier_model"])
            blended_brier = float(validation_metrics["brier_blended"])
            baseline_brier = float(validation_metrics["brier_baseline"])
        else:
            self.selected_alpha = float(self.config.alpha)
            self.selected_drop_feature_groups = tuple(str(value) for value in self.config.drop_feature_groups)
            model_brier = float("nan")
            blended_brier = float("nan")
            baseline_brier = float("nan")

        self._select_features(train)
        X_train = self._fit_transform(train)
        y_train_labels = train[label_col].astype(float).to_numpy()
        y_train_target = self._training_target(train, label_col=label_col)
        train_sample_weight = _sample_weight_series(train, self.config)
        self._fit_linear_weights(
            X_train,
            y_train_target,
            alpha=self.selected_alpha,
            sample_weight=train_sample_weight.to_numpy(dtype=float),
        )

        if not validation_windows:
            train_pred = self.predict_proba(train)
            train_market = _market_prob_series(train)
            model_brier = brier_score(train_pred.tolist(), y_train_labels.tolist())
            blended_brier = brier_score(
                _blend_predictions(train_pred.tolist(), train_market.tolist(), self.blend_weight_model),
                y_train_labels.tolist(),
            )
            baseline_brier = brier_score(train_market.tolist(), y_train_labels.tolist())

        self.metrics = ResolvedModelMetrics(
            train_rows=int(len(train)),
            validation_rows=int(len(validation)),
            validation_windows=int(len(validation_windows)),
            target_mode=str(self.config.target_mode),
            brier_model=float(model_brier),
            brier_blended=float(blended_brier),
            brier_baseline=float(baseline_brier),
            blend_weight_model=float(self.blend_weight_model),
            selected_alpha=float(self.selected_alpha),
            validation_objective=float(validation_objective),
            selected_drop_feature_groups=list(self.selected_drop_feature_groups),
            feature_count=int(len(self.feature_names)),
            sample_weight_scheme=str(self.config.sample_weight_scheme),
            sample_weight_key=str(self.config.sample_weight_key),
        )
        return self.metrics

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if not self.feature_names:
            raise ValueError("model has not been fit")
        raw = self._predict_linear_output(frame)
        if self._target_mode() == "residual":
            raw = raw + _market_prob_series(frame).to_numpy(dtype=float)
        return np.clip(raw, 0.0, 1.0)

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        market_prob = _market_prob_series(frame)
        linear_output = self._predict_linear_output(frame)
        pred = self.predict_proba(frame)
        recalibrated = _blend_predictions(pred.tolist(), market_prob.tolist(), self.blend_weight_model)
        return pd.DataFrame(
            {
                "target_mode": self._target_mode(),
                "model_output": linear_output,
                "pred": pred,
                "baseline_pred": market_prob,
                "recalibrated_pred": recalibrated,
            },
            index=frame.index,
        )

    def save(self, path: str | Path) -> None:
        payload = self.to_payload()
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def to_payload(self) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "numeric_features": self.numeric_features,
            "categorical_features": self.categorical_features,
            "category_levels": self.category_levels,
            "numeric_fill": self.numeric_fill,
            "numeric_mean": self.numeric_mean,
            "numeric_scale": self.numeric_scale,
            "interaction_sources": self.interaction_sources,
            "interaction_fill": self.interaction_fill,
            "interaction_mean": self.interaction_mean,
            "interaction_scale": self.interaction_scale,
            "feature_names": self.feature_names,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "blend_weight_model": self.blend_weight_model,
            "selected_alpha": self.selected_alpha,
            "selected_drop_feature_groups": list(self.selected_drop_feature_groups),
            "metrics": asdict(self.metrics) if self.metrics is not None else None,
        }

    @classmethod
    def load(cls, path: str | Path) -> "ResolvedLinearModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ResolvedLinearModel":
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
        model.interaction_sources = [tuple(value) for value in payload.get("interaction_sources", [])]
        model.interaction_fill = {str(k): float(v) for k, v in payload.get("interaction_fill", {}).items()}
        model.interaction_mean = {str(k): float(v) for k, v in payload.get("interaction_mean", {}).items()}
        model.interaction_scale = {str(k): float(v) for k, v in payload.get("interaction_scale", {}).items()}
        model.feature_names = [str(value) for value in payload.get("feature_names", [])]
        model.coefficients = [float(value) for value in payload.get("coefficients", [])]
        model.intercept = float(payload.get("intercept", 0.0))
        model.blend_weight_model = float(payload.get("blend_weight_model", 1.0))
        model.selected_alpha = float(payload.get("selected_alpha", model.config.alpha))
        model.selected_drop_feature_groups = tuple(str(value) for value in payload.get("selected_drop_feature_groups", model.config.drop_feature_groups))
        if payload.get("metrics") is not None:
            model.metrics = ResolvedModelMetrics(**payload["metrics"])
        return model

    def _target_mode(self) -> str:
        mode = str(self.config.target_mode).strip().lower()
        if mode not in {"direct", "residual"}:
            raise ValueError(f"Unsupported target_mode: {self.config.target_mode}")
        return mode

    def _training_target(self, frame: pd.DataFrame, *, label_col: str) -> np.ndarray:
        labels = pd.to_numeric(frame[label_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        if self._target_mode() == "residual":
            return labels - _market_prob_series(frame).to_numpy(dtype=float)
        return labels

    def _predict_linear_output(self, frame: pd.DataFrame) -> np.ndarray:
        X = self._transform(frame)
        return X @ np.asarray(self.coefficients, dtype=float) + float(self.intercept)

    def _select_features(self, frame: pd.DataFrame) -> None:
        blocked = self._blocked_feature_columns(frame.columns)
        self.numeric_features = [column for column in _NUMERIC_CANDIDATES if column in frame.columns and column not in blocked]
        if "market_prob" not in self.numeric_features and "p_yes" in frame.columns:
            self.numeric_features.insert(0, "p_yes")
        self.categorical_features = [column for column in _CATEGORICAL_CANDIDATES if column in frame.columns and column not in blocked]

    def _blocked_feature_columns(self, columns: Sequence[object]) -> set[str]:
        available = {str(column) for column in columns}
        blocked: set[str] = set()
        for group_name in self.selected_drop_feature_groups:
            blocked.update(
                member
                for member in _FEATURE_GROUPS.get(str(group_name), ())
                if member in available
            )
        return blocked

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
        numeric_filled: dict[str, pd.Series] = {}
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
            numeric_filled[column] = filled
            numeric_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        categorical_parts: list[np.ndarray] = []
        self.category_levels = {}
        for column in self.categorical_features:
            series = frame.get(column).astype("string").fillna("__missing__")
            levels = self._fit_category_levels(series)
            if "__other__" in levels:
                series = series.where(series.isin(levels), "__other__")
            else:
                series = series.where(series.isin(levels), "__missing__")
            self.category_levels[column] = levels
            dummies = pd.get_dummies(series, prefix=column)
            dummies = dummies.reindex(columns=[f"{column}_{level}" for level in levels], fill_value=0)
            categorical_parts.append(dummies.to_numpy(dtype=float))

        interaction_parts: list[np.ndarray] = []
        self.interaction_sources = []
        self.interaction_fill = {}
        self.interaction_mean = {}
        self.interaction_scale = {}
        if self.config.use_horizon_interactions and "horizon_hours" in numeric_filled:
            horizon = numeric_filled["horizon_hours"]
            for column in self.numeric_features:
                if column == "horizon_hours":
                    continue
                key = f"{column}__x_horizon_hours"
                interaction = numeric_filled[column] * horizon
                fill = float(interaction.median()) if interaction.notna().any() else 0.0
                filled = interaction.fillna(fill)
                mean = float(filled.mean())
                scale = float(filled.std(ddof=0))
                if scale == 0.0:
                    scale = 1.0
                self.interaction_sources.append((column, "horizon_hours"))
                self.interaction_fill[key] = fill
                self.interaction_mean[key] = mean
                self.interaction_scale[key] = scale
                interaction_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        matrices = [part for part in numeric_parts + interaction_parts + categorical_parts if part.size > 0]
        X = np.concatenate(matrices, axis=1) if matrices else np.zeros((len(frame), 0), dtype=float)
        self.feature_names = [*self.numeric_features]
        for left, right in self.interaction_sources:
            self.feature_names.append(f"{left}__x_{right}")
        for column in self.categorical_features:
            self.feature_names.extend([f"{column}_{level}" for level in self.category_levels[column]])
        return X

    def _transform(self, frame: pd.DataFrame) -> np.ndarray:
        numeric_parts: list[np.ndarray] = []
        numeric_filled: dict[str, pd.Series] = {}
        for column in self.numeric_features:
            series = _coerce_numeric_series(frame, column)
            fill = self.numeric_fill.get(column, 0.0)
            mean = self.numeric_mean.get(column, 0.0)
            scale = self.numeric_scale.get(column, 1.0)
            filled = series.fillna(fill)
            numeric_filled[column] = filled
            numeric_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        interaction_parts: list[np.ndarray] = []
        for left, right in self.interaction_sources:
            key = f"{left}__x_{right}"
            left_series = numeric_filled.get(left)
            right_series = numeric_filled.get(right)
            if left_series is None or right_series is None:
                interaction = pd.Series([self.interaction_fill.get(key, 0.0)] * len(frame), index=frame.index)
            else:
                interaction = left_series * right_series
            fill = self.interaction_fill.get(key, 0.0)
            mean = self.interaction_mean.get(key, 0.0)
            scale = self.interaction_scale.get(key, 1.0)
            filled = interaction.fillna(fill)
            interaction_parts.append(((filled - mean) / scale).to_numpy(dtype=float).reshape(-1, 1))

        categorical_parts: list[np.ndarray] = []
        for column in self.categorical_features:
            levels = self.category_levels.get(column, [])
            series = frame.get(column).astype("string").fillna("__missing__")
            if "__other__" in levels:
                series = series.where(series.isin(levels), "__other__")
            elif "__missing__" in levels:
                series = series.where(series.isin(levels), "__missing__")
            dummies = pd.get_dummies(series, prefix=column)
            dummies = dummies.reindex(columns=[f"{column}_{level}" for level in levels], fill_value=0)
            categorical_parts.append(dummies.to_numpy(dtype=float))
        matrices = [part for part in numeric_parts + interaction_parts + categorical_parts if part.size > 0]
        return np.concatenate(matrices, axis=1) if matrices else np.zeros((len(frame), 0), dtype=float)

    def _fit_linear_weights(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        alpha: float | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> None:
        if X.ndim != 2:
            raise ValueError("X must be 2-dimensional")
        coeff = _solve_ridge_weights(
            X,
            y,
            alpha=float(self.config.alpha if alpha is None else alpha),
            sample_weight=sample_weight,
        )
        self.intercept = float(coeff[0])
        self.coefficients = [float(value) for value in coeff[1:]]

    def _fit_category_levels(self, series: pd.Series) -> list[str]:
        min_count = max(int(self.config.min_categorical_level_count), 1)
        counts = series.value_counts(dropna=False)
        levels = sorted(str(index) for index, count in counts.items() if int(count) >= min_count)
        if len(levels) < len(counts):
            levels.append("__other__")
        if not levels:
            levels = ["__missing__"]
        return sorted(dict.fromkeys(levels))

    def _build_validation_windows(
        self,
        ordered: pd.DataFrame,
        validation_rows: int,
    ) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
        if validation_rows <= 0 or len(ordered) <= validation_rows:
            return []
        if len(ordered) < self.config.min_validation_rows * 2:
            return []
        max_windows = max(1, int(self.config.validation_windows))
        window_count = min(max_windows, max(1, (len(ordered) // validation_rows) - 1))
        start = len(ordered) - (window_count * validation_rows)
        windows: list[tuple[pd.DataFrame, pd.DataFrame]] = []
        for idx in range(window_count):
            val_start = start + (idx * validation_rows)
            val_end = min(len(ordered), val_start + validation_rows)
            train = ordered.iloc[:val_start].copy()
            validation = ordered.iloc[val_start:val_end].copy()
            if len(train) < self.config.min_validation_rows or validation.empty:
                continue
            windows.append((train, validation))
        return windows

    def _select_alpha_and_blend(
        self,
        ordered: pd.DataFrame,
        *,
        validation_windows: list[tuple[pd.DataFrame, pd.DataFrame]],
        label_col: str,
    ) -> tuple[float, float, tuple[str, ...], dict[str, float]]:
        best_alpha = float(self.config.alpha)
        best_blend = 1.0
        best_drop_groups: tuple[str, ...] = tuple(str(value) for value in self.config.drop_feature_groups)
        best_metrics: dict[str, float] | None = None
        best_objective = float("inf")
        for drop_groups in _candidate_drop_feature_groups(self.config, ordered.columns):
            for alpha in _candidate_alphas(self.config):
                validation_model: list[float] = []
                validation_market: list[float] = []
                validation_labels: list[int] = []
                validation_weights: list[float] = []
                for train, validation in validation_windows:
                    temp_model = ResolvedLinearModel(
                        ResolvedModelConfig(
                            alpha=float(alpha),
                            alpha_grid=(),
                            validation_fraction=0.0,
                            min_validation_rows=self.config.min_validation_rows,
                            validation_windows=1,
                            blend_grid_size=self.config.blend_grid_size,
                            min_categorical_level_count=self.config.min_categorical_level_count,
                            selection_metric=self.config.selection_metric,
                            drop_feature_groups=tuple(drop_groups),
                            feature_group_grid=(),
                            target_mode=self.config.target_mode,
                            use_horizon_interactions=self.config.use_horizon_interactions,
                            sample_weight_scheme=self.config.sample_weight_scheme,
                            sample_weight_key=self.config.sample_weight_key,
                            sample_weight_power=self.config.sample_weight_power,
                            sample_weight_min=self.config.sample_weight_min,
                            sample_weight_cap=self.config.sample_weight_cap,
                        )
                    )
                    temp_model.fit(train, label_col=label_col)
                    validation_frame = temp_model.predict_frame(validation)
                    validation_model.extend(validation_frame["pred"].tolist())
                    validation_market.extend(validation_frame["baseline_pred"].tolist())
                    validation_labels.extend(validation[label_col].astype(int).tolist())
                    validation_weights.extend(_sample_weight_series(validation, self.config).tolist())

                if not validation_labels:
                    continue
                blend_weight = _select_blend_weight(
                    validation_model,
                    validation_market,
                    validation_labels,
                    sample_weight=validation_weights,
                    grid_size=self.config.blend_grid_size,
                    selection_metric=self.config.selection_metric,
                )
                blended = _blend_predictions(validation_model, validation_market, blend_weight)
                objective = _selection_objective(
                    blended,
                    validation_labels,
                    selection_metric=self.config.selection_metric,
                    sample_weight=validation_weights,
                )
                if objective < best_objective - 1e-12 or (
                    abs(objective - best_objective) <= 1e-12 and blend_weight < best_blend
                ):
                    best_objective = float(objective)
                    best_alpha = float(alpha)
                    best_blend = float(blend_weight)
                    best_drop_groups = tuple(drop_groups)
                    best_metrics = {
                        "objective": float(objective),
                        "brier_model": float(_weighted_brier_score(validation_model, validation_labels, sample_weight=validation_weights)),
                        "brier_blended": float(_weighted_brier_score(blended, validation_labels, sample_weight=validation_weights)),
                        "brier_baseline": float(_weighted_brier_score(validation_market, validation_labels, sample_weight=validation_weights)),
                    }
        if best_metrics is None:
            return float(self.config.alpha), 1.0, tuple(str(value) for value in self.config.drop_feature_groups), {
                "objective": float("nan"),
                "brier_model": float("nan"),
                "brier_blended": float("nan"),
                "brier_baseline": float("nan"),
            }
        return best_alpha, best_blend, best_drop_groups, best_metrics


class SegmentedResolvedModel:
    def __init__(
        self,
        *,
        model_config: ResolvedModelConfig | None = None,
        routing_config: SegmentRoutingConfig | None = None,
    ) -> None:
        self.model_config = model_config or ResolvedModelConfig()
        self.routing_config = routing_config or SegmentRoutingConfig()
        self.global_model = ResolvedLinearModel(self.model_config)
        self.segment_models: dict[str, ResolvedLinearModel] = {}
        self.segment_row_counts: dict[str, int] = {}
        self.segment_gate_metrics: dict[str, dict[str, float | int | bool]] = {}

    def fit(self, frame: pd.DataFrame, *, label_col: str = "label") -> dict[str, Any]:
        self.global_model.fit(frame, label_col=label_col)
        route_series = _segment_route_series(frame, self.routing_config)
        self.segment_models = {}
        self.segment_gate_metrics = {}
        self.segment_row_counts = {
            str(key): int(value)
            for key, value in route_series.value_counts(dropna=False).to_dict().items()
        }
        for segment, row_count in self.segment_row_counts.items():
            if segment in {"", "__global__"}:
                continue
            if row_count < max(int(self.routing_config.min_segment_rows), 1):
                continue
            mask = route_series.eq(segment)
            subset = frame.loc[mask].copy()
            if subset.empty:
                continue
            labels = pd.to_numeric(subset[label_col], errors="coerce").dropna().astype(int)
            if labels.nunique() < 2:
                continue
            gate_metrics = _evaluate_segment_route_gate(
                frame,
                segment=str(segment),
                label_col=label_col,
                model_config=self.model_config,
                routing_config=self.routing_config,
            )
            self.segment_gate_metrics[str(segment)] = gate_metrics
            if not bool(gate_metrics.get("activate", False)):
                continue
            model = ResolvedLinearModel(self.model_config)
            model.fit(subset, label_col=label_col)
            self.segment_models[str(segment)] = model
        return {
            "routing_strategy": str(self.routing_config.strategy),
            "route_key": str(self.routing_config.route_key),
            "trained_segments": sorted(self.segment_models.keys()),
            "segment_row_counts": dict(sorted(self.segment_row_counts.items())),
            "segment_gate_metrics": self.segment_gate_metrics,
        }

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        base = self.global_model.predict_frame(frame).copy()
        route_series = _segment_route_series(frame, self.routing_config)
        base["route_segment"] = route_series.astype("string")
        base["route_model"] = "global"
        for segment, model in self.segment_models.items():
            mask = route_series.eq(segment)
            if not bool(mask.any()):
                continue
            segment_pred = model.predict_frame(frame.loc[mask]).copy()
            for column in ("target_mode", "model_output", "pred", "baseline_pred", "recalibrated_pred"):
                base.loc[mask, column] = segment_pred[column].to_numpy()
            base.loc[mask, "route_model"] = f"segment:{segment}"
        return base

    def save(self, path: str | Path) -> None:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "segmented_resolved_model",
            "model_config": asdict(self.model_config),
            "routing_config": asdict(self.routing_config),
            "global_model": self.global_model.to_payload(),
            "segment_models": {key: model.to_payload() for key, model in self.segment_models.items()},
            "segment_row_counts": self.segment_row_counts,
            "segment_gate_metrics": self.segment_gate_metrics,
        }
        resolved.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SegmentedResolvedModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        model = cls(
            model_config=ResolvedModelConfig(**payload["model_config"]),
            routing_config=SegmentRoutingConfig(**payload["routing_config"]),
        )
        model.global_model = ResolvedLinearModel.from_payload(payload["global_model"])
        model.segment_models = {
            str(key): ResolvedLinearModel.from_payload(value)
            for key, value in payload.get("segment_models", {}).items()
        }
        model.segment_row_counts = {
            str(key): int(value)
            for key, value in payload.get("segment_row_counts", {}).items()
        }
        model.segment_gate_metrics = {
            str(key): dict(value)
            for key, value in payload.get("segment_gate_metrics", {}).items()
        }
        return model


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


def train_segmented_resolved_model(
    rows: pd.DataFrame,
    *,
    model_config: ResolvedModelConfig | None = None,
    routing_config: SegmentRoutingConfig | None = None,
) -> tuple[SegmentedResolvedModel, pd.DataFrame, dict[str, Any]]:
    model = SegmentedResolvedModel(
        model_config=model_config,
        routing_config=routing_config,
    )
    routing_summary = model.fit(rows)
    predictions = pd.concat([rows.reset_index(drop=True), model.predict_frame(rows).reset_index(drop=True)], axis=1)
    summary = {
        **(asdict(model.global_model.metrics) if model.global_model.metrics is not None else {}),
        "metric_bundle": summarize_metrics_extended(
            predictions["recalibrated_pred"].tolist(),
            predictions["label"].astype(int).tolist(),
        ),
        **routing_summary,
    }
    return model, predictions, summary


def run_feature_ablation(
    rows: pd.DataFrame,
    *,
    model_config: ResolvedModelConfig | None = None,
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()

    _, _, base_summary = train_resolved_model(rows, model_config=model_config)
    results: list[dict[str, Any]] = [
        {
            "feature_group": "all_features",
            "row_count": int(len(rows)),
            "feature_count": int(base_summary["feature_count"]),
            "brier_model": float(base_summary["brier_model"]),
            "brier_blended": float(base_summary["brier_blended"]),
            "brier_baseline": float(base_summary["brier_baseline"]),
            "target_mode": str(base_summary["target_mode"]),
            "blend_weight_model": float(base_summary["blend_weight_model"]),
        }
    ]

    for group_name in _active_feature_groups(rows.columns):
        excluded_columns = [column for column in _FEATURE_GROUPS[group_name] if column in rows.columns]
        if not excluded_columns:
            continue
        ablated_rows = rows.drop(columns=excluded_columns, errors="ignore")
        _, _, summary = train_resolved_model(ablated_rows, model_config=model_config)
        results.append(
            {
                "feature_group": f"drop:{group_name}",
                "row_count": int(len(ablated_rows)),
                "feature_count": int(summary["feature_count"]),
                "brier_model": float(summary["brier_model"]),
                "brier_blended": float(summary["brier_blended"]),
                "brier_baseline": float(summary["brier_baseline"]),
                "target_mode": str(summary["target_mode"]),
                "blend_weight_model": float(summary["blend_weight_model"]),
            }
        )
    return pd.DataFrame(results).sort_values("feature_group").reset_index(drop=True)


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
    target_mode: str = "residual",
    use_horizon_interactions: bool = True,
    sample_weight_scheme: str = "none",
    sample_weight_key: str = "platform_category",
    run_ablation: bool = False,
    ablation_report_path: Path | None = None,
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
        model_config=ResolvedModelConfig(
            alpha=float(alpha),
            target_mode=str(target_mode),
            use_horizon_interactions=bool(use_horizon_interactions),
            sample_weight_scheme=str(sample_weight_scheme),
            sample_weight_key=str(sample_weight_key),
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    predictions_path = output_dir / "resolved_model_predictions.csv"
    predictions.to_csv(predictions_path, index=False)
    ablation_summary_path: str | None = None
    if run_ablation:
        ablation_frame = run_feature_ablation(
            dataset,
            model_config=ResolvedModelConfig(
                alpha=float(alpha),
                target_mode=str(target_mode),
                use_horizon_interactions=bool(use_horizon_interactions),
                sample_weight_scheme=str(sample_weight_scheme),
                sample_weight_key=str(sample_weight_key),
            ),
        )
        resolved_ablation_path = ablation_report_path or (output_dir / "feature_ablation_summary.csv")
        ablation_frame.to_csv(resolved_ablation_path, index=False)
        ablation_summary_path = str(resolved_ablation_path)
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
        "target_mode": target_mode,
        "use_horizon_interactions": bool(use_horizon_interactions),
        "sample_weight_scheme": str(sample_weight_scheme),
        "sample_weight_key": str(sample_weight_key),
        "ablation_summary_path": ablation_summary_path,
    }
    summary_path = output_dir / "resolved_model_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    return payload


def _market_prob_series(frame: pd.DataFrame) -> pd.Series:
    if "market_prob" in frame.columns:
        return pd.to_numeric(frame["market_prob"], errors="coerce").fillna(0.5).clip(0.0, 1.0)
    if "p_yes" in frame.columns:
        return pd.to_numeric(frame["p_yes"], errors="coerce").fillna(0.5).clip(0.0, 1.0)
    return pd.Series([0.5] * len(frame), index=frame.index, dtype=float)


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
    sample_weight: Sequence[float] | None = None,
    grid_size: int,
    selection_metric: str = "joint",
) -> float:
    best_weight = 1.0
    best_objective = float("inf")
    for step in range(max(2, int(grid_size))):
        weight = step / (max(2, int(grid_size)) - 1)
        blended = _blend_predictions(model_pred, market_pred, weight)
        score = _selection_objective(
            blended,
            labels,
            selection_metric=selection_metric,
            sample_weight=sample_weight,
        )
        if score < best_objective - 1e-12 or (
            abs(score - best_objective) <= 1e-12 and weight < best_weight
        ):
            best_objective = score
            best_weight = weight
    return float(best_weight)


def _selection_objective(
    preds: Sequence[float],
    labels: Sequence[int],
    *,
    selection_metric: str,
    sample_weight: Sequence[float] | None = None,
) -> float:
    metric = str(selection_metric).strip().lower()
    if metric == "brier":
        return float(_weighted_brier_score(preds, labels, sample_weight=sample_weight))
    if metric == "log_loss":
        return float(_weighted_log_loss(preds, labels, sample_weight=sample_weight))
    return float(
        _weighted_brier_score(preds, labels, sample_weight=sample_weight)
        + (0.25 * _weighted_log_loss(preds, labels, sample_weight=sample_weight))
    )


def _solve_ridge_weights(
    X: np.ndarray,
    y: np.ndarray,
    *,
    alpha: float,
    sample_weight: np.ndarray | None = None,
) -> np.ndarray:
    X_design = np.concatenate([np.ones((len(X), 1), dtype=float), X], axis=1)
    if sample_weight is not None:
        weight = np.asarray(sample_weight, dtype=float).reshape(-1)
        if len(weight) != len(X_design):
            raise ValueError("sample_weight must align to X rows")
        safe_weight = np.clip(weight, 1e-9, None)
        root_weight = np.sqrt(safe_weight).reshape(-1, 1)
        X_design = X_design * root_weight
        y = np.asarray(y, dtype=float).reshape(-1) * root_weight.reshape(-1)
    ridge = np.eye(X_design.shape[1], dtype=float) * float(alpha)
    ridge[0, 0] = 0.0
    lhs = X_design.T @ X_design + ridge
    rhs = X_design.T @ y
    try:
        return np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(lhs) @ rhs


def _sample_weight_series(frame: pd.DataFrame, config: ResolvedModelConfig) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)

    scheme = str(config.sample_weight_scheme).strip().lower()
    if scheme in {"", "none"}:
        return pd.Series(np.ones(len(frame), dtype=float), index=frame.index)

    key = str(config.sample_weight_key).strip()
    if key not in frame.columns:
        return pd.Series(np.ones(len(frame), dtype=float), index=frame.index)

    segment = frame[key].astype("string").fillna("__missing__")
    counts = segment.value_counts(dropna=False)
    if counts.empty:
        return pd.Series(np.ones(len(frame), dtype=float), index=frame.index)

    reference = float(np.median(counts.astype(float).to_numpy()))
    if reference <= 0.0:
        reference = 1.0

    power = float(config.sample_weight_power)
    min_weight = max(float(config.sample_weight_min), 1e-6)
    max_weight = max(float(config.sample_weight_cap), min_weight)

    raw = segment.map(lambda value: (reference / max(float(counts.get(value, 1.0)), 1.0)) ** power).astype(float)
    clipped = raw.clip(lower=min_weight, upper=max_weight)
    normalized = clipped / max(float(clipped.mean()), 1e-9)
    return normalized.astype(float)


def _segment_route_series(frame: pd.DataFrame, config: SegmentRoutingConfig) -> pd.Series:
    strategy = str(config.strategy).strip().lower()
    if strategy in {"", "none"}:
        return pd.Series(["__global__"] * len(frame), index=frame.index, dtype="string")

    if strategy == "crypto_vs_rest":
        source = frame.get(config.route_key, pd.Series([""] * len(frame), index=frame.index)).astype("string").fillna("")
        return source.str.lower().map(lambda value: "crypto" if value == "crypto" else "non_crypto").astype("string")

    if strategy == "kalshi_vs_rest":
        source = frame.get(config.route_key, pd.Series([""] * len(frame), index=frame.index)).astype("string").fillna("")
        return source.str.lower().map(lambda value: "kalshi" if value == "kalshi" else "non_kalshi").astype("string")

    source = frame.get(config.route_key, pd.Series([""] * len(frame), index=frame.index)).astype("string").fillna("__missing__")
    return source


def _evaluate_segment_route_gate(
    frame: pd.DataFrame,
    *,
    segment: str,
    label_col: str,
    model_config: ResolvedModelConfig,
    routing_config: SegmentRoutingConfig,
) -> dict[str, float | int | bool]:
    helper = ResolvedLinearModel(model_config)
    ordered = helper._order_for_validation(frame)
    validation_rows = max(int(len(ordered) * float(model_config.validation_fraction)), 0)
    if len(ordered) >= model_config.min_validation_rows * 2:
        validation_rows = max(validation_rows, model_config.min_validation_rows)
    else:
        validation_rows = 0
    windows = helper._build_validation_windows(ordered, validation_rows)
    improvements: list[float] = []
    for train, validation in windows:
        train_route = _segment_route_series(train, routing_config)
        validation_route = _segment_route_series(validation, routing_config)
        train_mask = train_route.eq(segment)
        validation_mask = validation_route.eq(segment)
        if int(train_mask.sum()) < max(int(routing_config.min_segment_rows), 1):
            continue
        if int(validation_mask.sum()) < max(int(model_config.min_validation_rows), 1):
            continue
        train_subset = train.loc[train_mask].copy()
        validation_subset = validation.loc[validation_mask].copy()
        labels = pd.to_numeric(train_subset[label_col], errors="coerce").dropna().astype(int)
        if labels.nunique() < 2:
            continue
        global_model = ResolvedLinearModel(model_config)
        global_model.fit(train, label_col=label_col)
        segment_model = ResolvedLinearModel(model_config)
        segment_model.fit(train_subset, label_col=label_col)
        global_pred = global_model.predict_frame(validation_subset)["pred"].tolist()
        segment_pred = segment_model.predict_frame(validation_subset)["pred"].tolist()
        val_labels = validation_subset[label_col].astype(int).tolist()
        weights = _sample_weight_series(validation_subset, model_config).tolist()
        global_brier = _weighted_brier_score(global_pred, val_labels, sample_weight=weights)
        segment_brier = _weighted_brier_score(segment_pred, val_labels, sample_weight=weights)
        improvements.append(float(global_brier - segment_brier))

    valid_windows = len(improvements)
    avg_improvement = float(np.mean(improvements)) if improvements else float("-inf")
    worst_improvement = float(min(improvements)) if improvements else float("-inf")
    activate = (
        valid_windows >= max(int(routing_config.gate_min_windows), 1)
        and avg_improvement >= float(routing_config.gate_min_improvement)
        and worst_improvement >= -float(routing_config.gate_worst_case_tolerance)
    )
    return {
        "activate": bool(activate),
        "valid_windows": int(valid_windows),
        "avg_improvement": float(avg_improvement),
        "worst_improvement": float(worst_improvement),
    }


def _weighted_brier_score(
    preds: Sequence[float],
    labels: Sequence[int],
    *,
    sample_weight: Sequence[float] | None = None,
) -> float:
    if sample_weight is None:
        return float(brier_score(preds, labels))
    pred_arr = np.asarray([float(value) for value in preds], dtype=float)
    label_arr = np.asarray([float(value) for value in labels], dtype=float)
    weight_arr = np.asarray([float(value) for value in sample_weight], dtype=float)
    return float(np.average((pred_arr - label_arr) ** 2, weights=weight_arr))


def _weighted_log_loss(
    preds: Sequence[float],
    labels: Sequence[int],
    *,
    sample_weight: Sequence[float] | None = None,
) -> float:
    if sample_weight is None:
        return float(log_loss(preds, labels))
    pred_arr = np.clip(np.asarray([float(value) for value in preds], dtype=float), 1e-8, 1.0 - 1e-8)
    label_arr = np.asarray([float(value) for value in labels], dtype=float)
    weight_arr = np.asarray([float(value) for value in sample_weight], dtype=float)
    losses = -(label_arr * np.log(pred_arr) + (1.0 - label_arr) * np.log(1.0 - pred_arr))
    return float(np.average(losses, weights=weight_arr))


def _candidate_alphas(config: ResolvedModelConfig) -> list[float]:
    values = [float(config.alpha)]
    values.extend(float(value) for value in config.alpha_grid)
    return sorted({value for value in values if value > 0.0})


def _candidate_drop_feature_groups(
    config: ResolvedModelConfig,
    columns: Sequence[object],
) -> list[tuple[str, ...]]:
    available = {str(column) for column in columns}
    candidates: list[tuple[str, ...]] = [tuple(str(value) for value in config.drop_feature_groups)]
    for item in config.feature_group_grid:
        token = str(item).strip()
        if not token or token == "all_features":
            candidates.append(())
            continue
        if token.startswith("drop:"):
            group_name = token.split(":", 1)[1]
            members = _FEATURE_GROUPS.get(group_name, ())
            if any(member in available for member in members):
                candidates.append((group_name,))
    deduped: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        normalized = tuple(sorted(dict.fromkeys(str(value) for value in candidate)))
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _active_feature_groups(columns: Sequence[object]) -> list[str]:
    available = {str(column) for column in columns}
    active: list[str] = []
    for group_name, members in _FEATURE_GROUPS.items():
        if any(member in available for member in members):
            active.append(group_name)
    return active


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
    parser.add_argument("--target-mode", default="residual", choices=["direct", "residual"])
    parser.add_argument("--disable-horizon-interactions", action="store_true")
    parser.add_argument("--sample-weight-scheme", default="none")
    parser.add_argument("--sample-weight-key", default="platform_category")
    parser.add_argument("--run-ablation", action="store_true")
    parser.add_argument("--ablation-report-path", default="")
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
        target_mode=str(args.target_mode),
        use_horizon_interactions=not bool(args.disable_horizon_interactions),
        sample_weight_scheme=str(args.sample_weight_scheme),
        sample_weight_key=str(args.sample_weight_key),
        run_ablation=bool(args.run_ablation),
        ablation_report_path=Path(args.ablation_report_path) if args.ablation_report_path else None,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
