from pathlib import Path

import pandas as pd

from pipelines.train_resolved_model import (
    ResolvedLinearModel,
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
    assert predictions["recalibrated_pred"].between(0, 1).all()


def test_resolved_linear_model_round_trip(tmp_path: Path) -> None:
    model, _, _ = train_resolved_model(_training_rows())
    path = tmp_path / "model.json"
    model.save(path)

    loaded = ResolvedLinearModel.load(path)
    preds = loaded.predict_frame(_training_rows())
    assert preds["pred"].between(0, 1).all()

