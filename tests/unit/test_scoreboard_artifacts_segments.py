from __future__ import annotations

import math

import pytest

from calibration.metrics import summarize_metrics, summarize_metrics_extended
from calibration.trust_score import compute_trust_score
from pipelines.build_scoreboard_artifacts import build_scoreboard_rows


def test_build_scoreboard_rows_adds_category_liquidity_tte_segment_with_unknown() -> None:
    rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "tte_bucket": "0-7d",
            "pred": 0.90,
            "label": 1,
        },
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.80,
            "label": 1,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "tte_bucket": "8-30d",
            "pred": 0.20,
            "label": 0,
        },
    ]

    _, summary_metrics = build_scoreboard_rows(rows)

    cross_segment = summary_metrics["by_category_liquidity_tte"]
    assert set(cross_segment) == {
        ("politics", "high", "0-7d"),
        ("politics", "high", "unknown"),
        ("sports", "low", "8-30d"),
    }

    expected_unknown_bucket = summarize_metrics([0.80], [1])
    assert cross_segment[("politics", "high", "unknown")]["brier"] == pytest.approx(
        expected_unknown_bucket["brier"], rel=0, abs=1e-12
    )
    assert cross_segment[("politics", "high", "unknown")]["log_loss"] == pytest.approx(
        expected_unknown_bucket["log_loss"], rel=0, abs=1e-12
    )
    assert cross_segment[("politics", "high", "unknown")]["ece"] == pytest.approx(
        expected_unknown_bucket["ece"], rel=0, abs=1e-12
    )


def test_build_scoreboard_rows_global_includes_slope_and_intercept() -> None:
    rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.10,
            "label": 0,
        },
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.40,
            "label": 0,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.80,
            "label": 1,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.90,
            "label": 1,
        },
    ]

    _, summary_metrics = build_scoreboard_rows(rows)
    global_metrics = summary_metrics["global"]

    expected = summarize_metrics_extended([0.10, 0.40, 0.80, 0.90], [0, 0, 1, 1])
    assert "slope" in global_metrics
    assert "intercept" in global_metrics
    assert global_metrics["slope"] == pytest.approx(expected["slope"], rel=0, abs=1e-12)
    assert global_metrics["intercept"] == pytest.approx(expected["intercept"], rel=0, abs=1e-12)


def test_build_scoreboard_rows_trust_weights_override_changes_score() -> None:
    rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.70,
            "label": 1,
            "liquidity_depth": 0.90,
            "stability": 0.10,
            "question_quality": 0.20,
            "manipulation_suspect": 0.80,
        }
    ]

    default_rows, _ = build_scoreboard_rows(rows)
    custom_weights = {
        "liquidity_depth": 0.0,
        "stability": 1.0,
        "question_quality": 0.0,
        "manipulation_suspect": 0.0,
    }
    weighted_rows, _ = build_scoreboard_rows(rows, trust_weights=custom_weights)

    default_score = float(default_rows[0]["trust_score"])
    weighted_score = float(weighted_rows[0]["trust_score"])

    expected_weighted = compute_trust_score(
        {
            "liquidity_depth": 0.90,
            "stability": 0.10,
            "question_quality": 0.20,
            "manipulation_suspect": 0.80,
        },
        custom_weights,
    )
    assert math.isclose(weighted_score, expected_weighted, rel_tol=0.0, abs_tol=1e-12)
    assert weighted_score != pytest.approx(default_score, rel=0, abs=1e-12)
