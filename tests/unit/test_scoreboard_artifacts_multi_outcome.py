from __future__ import annotations

import pytest

from calibration.labeling import RESOLVED_FALSE, RESOLVED_TRUE
from calibration.metrics import summarize_metrics
from pipelines.build_scoreboard_artifacts import build_scoreboard_rows


def test_build_scoreboard_rows_converts_label_status_and_excludes_multi_outcome() -> None:
    rows = [
        {
            "market_id": "binary-true",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.90,
            "label_status": RESOLVED_TRUE,
            "outcome_count": 2,
        },
        {
            "market_id": "multi-by-count",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.80,
            "label_status": RESOLVED_FALSE,
            "outcome_count": 3,
        },
        {
            "market_id": "multi-by-outcomes",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.40,
            "label_status": RESOLVED_TRUE,
            "outcomes": ["a", "b", "c"],
        },
        {
            "market_id": "binary-false",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.20,
            "label_status": RESOLVED_FALSE,
            "outcomes": ["yes", "no"],
        },
        {
            "market_id": "multi-by-flag",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.60,
            "label_status": RESOLVED_TRUE,
            "is_multi_outcome": True,
        },
    ]

    score_rows, summary_metrics = build_scoreboard_rows(rows)

    assert {row["market_id"] for row in score_rows} == {"binary-true", "binary-false"}
    assert sum(int(row["sample_size"]) for row in score_rows) == 2

    expected_global = summarize_metrics([0.90, 0.20], [1, 0])
    assert summary_metrics["global"]["brier"] == pytest.approx(
        expected_global["brier"], rel=0, abs=1e-12
    )
    assert summary_metrics["global"]["log_loss"] == pytest.approx(
        expected_global["log_loss"], rel=0, abs=1e-12
    )
    assert summary_metrics["global"]["ece"] == pytest.approx(
        expected_global["ece"], rel=0, abs=1e-12
    )


def test_build_scoreboard_rows_raises_when_binary_rows_absent_after_filtering() -> None:
    rows = [
        {
            "market_id": "multi-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.80,
            "label_status": RESOLVED_TRUE,
            "outcome_count": 3,
        },
        {
            "market_id": "multi-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.20,
            "label_status": RESOLVED_FALSE,
            "is_multi_outcome": True,
        },
    ]

    with pytest.raises(ValueError, match="no binary labeled rows"):
        build_scoreboard_rows(rows)
