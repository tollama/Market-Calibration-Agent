from pathlib import Path

import pandas as pd

from pipelines.train_resolved_model import (
    ResolvedLinearModel,
    ResolvedModelConfig,
    run_feature_ablation,
    train_resolved_model,
)


def _training_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_id": f"m{idx}",
                "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
                "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
                "label": 1 if idx % 2 == 0 else 0,
                "market_prob": 0.55 if idx % 2 == 0 else 0.45,
                "returns": 0.05 if idx % 2 == 0 else -0.05,
                "vol": 0.02 + idx * 0.001,
                "volume_velocity": 0.1 + idx * 0.01,
                "oi_change": 0.03 if idx % 2 == 0 else -0.02,
                "tte_seconds": 3600 + idx * 60,
                "liquidity_bucket_id": idx % 3,
                "category": "politics" if idx % 2 == 0 else "sports",
                "liquidity_bucket": "HIGH" if idx % 2 == 0 else "LOW",
                "template_group": "politics" if idx % 2 == 0 else "sports",
                "market_template": "politics_candidate" if idx % 2 == 0 else "sports_match",
                "template_confidence": 0.85 if idx % 2 == 0 else 0.7,
                "template_entity_count": 2,
            }
            for idx in range(12)
        ]
    )


def test_train_resolved_model_produces_prediction_columns() -> None:
    model, predictions, summary = train_resolved_model(_training_rows())

    assert isinstance(model, ResolvedLinearModel)
    assert set(predictions.columns) >= {"pred", "baseline_pred", "recalibrated_pred"}
    assert summary["feature_count"] > 0
    assert "selected_alpha" in summary
    assert "selected_drop_feature_groups" in summary
    assert predictions["recalibrated_pred"].between(0, 1).all()


def test_resolved_linear_model_round_trip(tmp_path: Path) -> None:
    model, _, _ = train_resolved_model(_training_rows())
    path = tmp_path / "model.json"
    model.save(path)

    loaded = ResolvedLinearModel.load(path)
    assert loaded.selected_alpha > 0
    preds = loaded.predict_frame(_training_rows())
    assert preds["pred"].between(0, 1).all()


def test_train_resolved_model_supports_residual_target_mode() -> None:
    model, predictions, summary = train_resolved_model(
        _training_rows(),
        model_config=ResolvedModelConfig(target_mode="residual", use_horizon_interactions=True),
    )

    assert isinstance(model, ResolvedLinearModel)
    assert summary["target_mode"] == "residual"
    assert summary["brier_baseline"] >= 0
    assert set(predictions.columns) >= {"model_output", "pred", "baseline_pred", "recalibrated_pred", "target_mode"}
    assert predictions["target_mode"].nunique() == 1
    assert predictions["target_mode"].iloc[0] == "residual"
    assert predictions["pred"].between(0, 1).all()


def test_run_feature_ablation_returns_group_comparison_rows() -> None:
    ablation = run_feature_ablation(
        _training_rows(),
        model_config=ResolvedModelConfig(target_mode="residual", use_horizon_interactions=True),
    )

    assert not ablation.empty
    assert "all_features" in set(ablation["feature_group"])
    assert any(str(value).startswith("drop:") for value in ablation["feature_group"])
    assert set(ablation.columns) >= {
        "feature_group",
        "feature_count",
        "brier_model",
        "brier_blended",
        "brier_baseline",
        "target_mode",
    }


def test_train_resolved_model_supports_platform_category_weighting() -> None:
    rows = _training_rows().copy()
    rows["platform"] = ["kalshi"] * 8 + ["polymarket"] * 4
    rows["canonical_category"] = ["crypto"] * 8 + ["politics"] * 4
    rows["platform_category"] = [
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "kalshi:crypto",
        "polymarket:politics",
        "polymarket:politics",
        "polymarket:politics",
        "polymarket:politics",
    ]

    model, predictions, summary = train_resolved_model(
        rows,
        model_config=ResolvedModelConfig(
            target_mode="residual",
            use_horizon_interactions=True,
            sample_weight_scheme="segment_balanced",
            sample_weight_key="platform_category",
        ),
    )

    assert isinstance(model, ResolvedLinearModel)
    assert summary["sample_weight_scheme"] == "segment_balanced"
    assert summary["sample_weight_key"] == "platform_category"
    assert predictions["recalibrated_pred"].between(0, 1).all()
