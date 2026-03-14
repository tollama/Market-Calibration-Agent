import pandas as pd

from pipelines.scan_live_markets import scan_live_markets
from pipelines.train_resolved_model import train_resolved_model


def _training_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_id": f"m{idx}",
                "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
                "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
                "label": 1 if idx % 2 == 0 else 0,
                "market_prob": 0.6 if idx % 2 == 0 else 0.4,
                "returns": 0.06 if idx % 2 == 0 else -0.03,
                "vol": 0.02,
                "volume_velocity": 0.1,
                "oi_change": 0.04 if idx % 2 == 0 else -0.02,
                "tte_seconds": 7200,
                "liquidity_bucket_id": 2 if idx % 2 == 0 else 0,
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


def test_scan_live_markets_scores_and_ranks_rows() -> None:
    model, _, _ = train_resolved_model(_training_rows())
    live = pd.DataFrame(
        [
            {
                "market_id": "x1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "p_yes": 0.48,
                "returns": 0.05,
                "vol": 0.02,
                "volume_velocity": 0.15,
                "oi_change": 0.03,
                "tte_seconds": 3600,
                "liquidity_bucket_id": 2,
                "liquidity_bucket": "HIGH",
                "spread": 0.01,
                "liquidity": 5000,
            },
            {
                "market_id": "x2",
                "question": "Will Team X win tonight?",
                "category": "Sports",
                "p_yes": 0.52,
                "returns": -0.03,
                "vol": 0.03,
                "volume_velocity": 0.05,
                "oi_change": -0.02,
                "tte_seconds": 5400,
                "liquidity_bucket_id": 0,
                "liquidity_bucket": "LOW",
                "spread": 0.02,
                "liquidity": 1000,
            },
        ]
    )

    scanned = scan_live_markets(live, model=model)
    assert set(scanned.columns) >= {"pred", "recalibrated_pred", "edge", "signal", "ranking_score"}
    assert scanned["ranking_score"].iloc[0] >= scanned["ranking_score"].iloc[-1]

