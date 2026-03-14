import pandas as pd

from pipelines.build_resolved_training_dataset import (
    ResolvedDatasetConfig,
    build_resolved_training_dataset,
)


def _resolved_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_id": "m1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "slug": "candidate-a-election",
                "ts": "2026-01-01T00:00:00Z",
                "resolution_ts": "2026-01-01T06:00:00Z",
                "label_status": "RESOLVED_TRUE",
                "p_yes": 0.44,
            },
            {
                "market_id": "m1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "slug": "candidate-a-election",
                "ts": "2026-01-01T03:00:00Z",
                "resolution_ts": "2026-01-01T06:00:00Z",
                "label_status": "RESOLVED_TRUE",
                "p_yes": 0.58,
            },
            {
                "market_id": "m1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "slug": "candidate-a-election",
                "ts": "2026-01-01T05:30:00Z",
                "resolution_ts": "2026-01-01T06:00:00Z",
                "label_status": "RESOLVED_TRUE",
                "p_yes": 0.71,
            },
            {
                "market_id": "m2",
                "question": "Will Team X win tonight?",
                "category": "Sports",
                "slug": "team-x-win-tonight",
                "ts": "2026-01-01T00:00:00Z",
                "end_ts": "2026-01-01T08:00:00Z",
                "label_status": "RESOLVED_FALSE",
                "p_yes": 0.62,
            },
            {
                "market_id": "m2",
                "question": "Will Team X win tonight?",
                "category": "Sports",
                "slug": "team-x-win-tonight",
                "ts": "2026-01-01T07:00:00Z",
                "end_ts": "2026-01-01T08:00:00Z",
                "label_status": "RESOLVED_FALSE",
                "p_yes": 0.52,
            },
        ]
    )


def test_build_resolved_training_dataset_selects_latest_snapshot_before_horizon() -> None:
    dataset = build_resolved_training_dataset(
        _resolved_rows(),
        config=ResolvedDatasetConfig(horizons_hours=(1, 3)),
    )

    assert len(dataset) == 4
    m1_h3 = dataset.loc[(dataset["market_id"] == "m1") & (dataset["horizon_hours"] == 3)].iloc[0]
    m1_h1 = dataset.loc[(dataset["market_id"] == "m1") & (dataset["horizon_hours"] == 1)].iloc[0]
    m2_h1 = dataset.loc[(dataset["market_id"] == "m2") & (dataset["horizon_hours"] == 1)].iloc[0]
    m2_h3 = dataset.loc[(dataset["market_id"] == "m2") & (dataset["horizon_hours"] == 3)].iloc[0]

    assert m1_h3["snapshot_ts"] == "2026-01-01T03:00:00+00:00"
    assert m1_h1["snapshot_ts"] == "2026-01-01T03:00:00+00:00"
    assert m2_h1["snapshot_ts"] == "2026-01-01T07:00:00+00:00"
    assert m2_h3["snapshot_ts"] == "2026-01-01T00:00:00+00:00"
    assert m1_h1["label"] == 1
    assert m2_h1["label"] == 0
    assert m1_h1["market_prob"] == m1_h1["p_yes"]


def test_build_resolved_training_dataset_enriches_template_features_when_enabled() -> None:
    dataset = build_resolved_training_dataset(
        _resolved_rows(),
        config=ResolvedDatasetConfig(horizons_hours=(1,), include_template_features=True),
    )

    assert set(dataset.columns) >= {
        "market_template",
        "template_group",
        "template_confidence",
        "template_entity_count",
        "query_terms",
        "poll_mode",
    }
    assert dataset.loc[dataset["market_id"] == "m1", "market_template"].iloc[0] == "politics_candidate"
