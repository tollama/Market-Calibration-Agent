from __future__ import annotations

import pytest

from calibration.trust_score import (
    W_LIQUIDITY,
    W_MANIPULATION,
    W_QUESTION_QUALITY,
    W_STABILITY,
)
from pipelines.trust_policy_loader import load_trust_weights

_DEFAULT_WEIGHTS = {
    "liquidity_depth": W_LIQUIDITY,
    "stability": W_STABILITY,
    "question_quality": W_QUESTION_QUALITY,
    "manipulation_suspect": W_MANIPULATION,
}


def _assert_weights_close(
    actual: dict[str, float],
    expected: dict[str, float],
) -> None:
    assert set(actual) == set(expected)
    for key in expected:
        assert actual[key] == pytest.approx(expected[key], rel=0, abs=1e-12)
    assert sum(actual.values()) == pytest.approx(1.0, rel=0, abs=1e-12)


def test_load_trust_weights_fallbacks_to_defaults_when_file_or_keys_missing(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    from_default_path = load_trust_weights()
    _assert_weights_close(from_default_path, _DEFAULT_WEIGHTS)

    config_path = tmp_path / "config.yaml"
    config_path.write_text("app:\n  name: test-app\n", encoding="utf-8")
    from_missing_keys = load_trust_weights(config_path)
    _assert_weights_close(from_missing_keys, _DEFAULT_WEIGHTS)


def test_load_trust_weights_reads_top_level_weights_from_default_yaml_path(
    tmp_path, monkeypatch
) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default_config = configs_dir / "default.yaml"
    default_config.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    liquidity_depth: 2",
                "    stability: 1",
                "    question_quality: 1",
                "    manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    weights = load_trust_weights()
    expected = {
        "liquidity_depth": 0.5,
        "stability": 0.25,
        "question_quality": 0.25,
        "manipulation_suspect": 0.0,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_partial_override_applies_defaults_for_missing_keys(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    stability: 1.0",
                "    unknown_key: 99.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)

    total = W_LIQUIDITY + 1.0 + W_QUESTION_QUALITY + W_MANIPULATION
    expected = {
        "liquidity_depth": W_LIQUIDITY / total,
        "stability": 1.0 / total,
        "question_quality": W_QUESTION_QUALITY / total,
        "manipulation_suspect": W_MANIPULATION / total,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_normalizes_total_to_one(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    liquidity_depth: 2",
                "    stability: 2",
                "    question_quality: 2",
                "    manipulation_suspect: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)
    expected = {
        "liquidity_depth": 0.25,
        "stability": 0.25,
        "question_quality": 0.25,
        "manipulation_suspect": 0.25,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_supports_legacy_calibration_path(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "calibration:",
                "  trust_score:",
                "    liquidity_depth: 1",
                "    stability: 1",
                "    question_quality: 2",
                "    manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)
    expected = {
        "liquidity_depth": 0.25,
        "stability": 0.25,
        "question_quality": 0.5,
        "manipulation_suspect": 0.0,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_supports_legacy_calibration_weights_path(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "calibration:",
                "  trust_score:",
                "    weights:",
                "      liquidity_depth: 1",
                "      stability: 1",
                "      question_quality: 2",
                "      manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)
    expected = {
        "liquidity_depth": 0.25,
        "stability": 0.25,
        "question_quality": 0.5,
        "manipulation_suspect": 0.0,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_prefers_top_level_weights_over_legacy_path(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    liquidity_depth: 4",
                "    stability: 0",
                "    question_quality: 0",
                "    manipulation_suspect: 0",
                "calibration:",
                "  trust_score:",
                "    liquidity_depth: 0",
                "    stability: 4",
                "    question_quality: 0",
                "    manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)
    expected = {
        "liquidity_depth": 1.0,
        "stability": 0.0,
        "question_quality": 0.0,
        "manipulation_suspect": 0.0,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_partial_top_level_still_takes_precedence_over_legacy(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    liquidity_depth: 4",
                "calibration:",
                "  trust_score:",
                "    liquidity_depth: 0",
                "    stability: 4",
                "    question_quality: 0",
                "    manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    weights = load_trust_weights(config_path)
    total = 4 + W_STABILITY + W_QUESTION_QUALITY + W_MANIPULATION
    expected = {
        "liquidity_depth": 4 / total,
        "stability": W_STABILITY / total,
        "question_quality": W_QUESTION_QUALITY / total,
        "manipulation_suspect": W_MANIPULATION / total,
    }
    _assert_weights_close(weights, expected)


def test_load_trust_weights_rejects_negative_weight(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "trust_score:",
                "  weights:",
                "    liquidity_depth: -0.1",
                "    stability: 0.3",
                "    question_quality: 0.3",
                "    manipulation_suspect: 0.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-negative"):
        load_trust_weights(config_path)


def test_load_trust_weights_rejects_zero_total(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "calibration:",
                "  trust_score:",
                "    liquidity_depth: 0",
                "    stability: 0",
                "    question_quality: 0",
                "    manipulation_suspect: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="At least one trust score weight must be positive"):
        load_trust_weights(config_path)
