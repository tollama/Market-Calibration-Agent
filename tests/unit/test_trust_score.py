from __future__ import annotations

import math

from calibration.trust_score import (
    build_trust_score_row,
    compute_trust_components,
    compute_trust_score,
)


def test_compute_trust_score_uses_default_weights() -> None:
    components = compute_trust_components(
        liquidity_depth=0.70,
        stability=0.40,
        question_quality=0.90,
        manipulation_suspect=0.20,
    )

    score = compute_trust_score(components)

    expected = 100.0 * (
        (0.35 * 0.70)
        + (0.25 * 0.40)
        + (0.25 * 0.90)
        + (0.15 * (1.0 - 0.20))
    )
    assert math.isclose(score, expected, rel_tol=0.0, abs_tol=1e-12)


def test_compute_trust_components_clips_to_unit_interval() -> None:
    components = compute_trust_components(
        liquidity_depth=-2.0,
        stability=1.2,
        question_quality=0.25,
        manipulation_suspect=9.0,
    )

    assert components == {
        "liquidity_depth": 0.0,
        "stability": 1.0,
        "question_quality": 0.25,
        "manipulation_suspect": 1.0,
    }


def test_build_trust_score_row_is_deterministic() -> None:
    components = {
        "question_quality": 0.80,
        "manipulation_suspect": 0.10,
        "liquidity_depth": 0.60,
        "stability": 0.50,
    }
    weights_a = {
        "stability": 2.0,
        "liquidity_depth": 3.0,
        "manipulation_suspect": 1.0,
        "question_quality": 2.0,
    }
    weights_b = {
        "question_quality": 2.0,
        "manipulation_suspect": 1.0,
        "stability": 2.0,
        "liquidity_depth": 3.0,
    }

    row_a = build_trust_score_row(
        "mkt-123",
        "2026-02-20T12:00:00Z",
        components,
        weights=weights_a,
    )
    row_b = build_trust_score_row(
        "mkt-123",
        "2026-02-20T12:00:00Z",
        components,
        weights=weights_b,
    )

    assert row_a == row_b
    assert row_a["components"] == {
        "liquidity_depth": 0.60,
        "stability": 0.50,
        "question_quality": 0.80,
        "manipulation_suspect": 0.10,
    }
    assert row_a["weights"] == {
        "liquidity_depth": 3.0 / 8.0,
        "stability": 2.0 / 8.0,
        "question_quality": 2.0 / 8.0,
        "manipulation_suspect": 1.0 / 8.0,
    }

    expected_score = 100.0 * (
        (3.0 / 8.0 * 0.60)
        + (2.0 / 8.0 * 0.50)
        + (2.0 / 8.0 * 0.80)
        + (1.0 / 8.0 * (1.0 - 0.10))
    )
    assert math.isclose(row_a["trust_score"], expected_score, rel_tol=0.0, abs_tol=1e-12)
    assert row_a["formula_version"] == "v1"
