from __future__ import annotations

import pytest

from agents.alert_agent import AlertThresholds
from pipelines.alert_policy_loader import (
    load_alert_min_trust_score,
    load_alert_thresholds,
)


def _default_thresholds() -> dict[str, float]:
    defaults = AlertThresholds()
    return {
        "low_oi_confirmation": defaults.low_oi_confirmation,
        "low_ambiguity": defaults.low_ambiguity,
        "volume_spike": defaults.volume_spike,
    }


def test_load_alert_thresholds_falls_back_to_defaults_when_file_missing(
    tmp_path,
) -> None:
    config_path = tmp_path / "alerts-missing.yaml"

    assert load_alert_thresholds(config_path=config_path) == _default_thresholds()
    assert load_alert_min_trust_score(config_path=config_path) is None


def test_load_alert_thresholds_uses_defaults_when_keys_missing(tmp_path) -> None:
    config_path = tmp_path / "alerts.yaml"
    config_path.write_text(
        "alerts:\n"
        "  enabled: true\n"
        "thresholds:\n"
        "  mispricing_bps: 100\n",
        encoding="utf-8",
    )

    assert load_alert_thresholds(config_path=config_path) == _default_thresholds()


def test_load_alert_thresholds_parses_alias_keys(tmp_path) -> None:
    config_path = tmp_path / "alerts.yaml"
    config_path.write_text(
        "alert_policy:\n"
        "  thresholds:\n"
        "    low_oi_threshold: -0.05\n"
        "    low_ambiguity_threshold: 0.40\n"
        "    volume_spike_threshold: 1.75\n",
        encoding="utf-8",
    )

    assert load_alert_thresholds(config_path=config_path) == {
        "low_oi_confirmation": -0.05,
        "low_ambiguity": 0.40,
        "volume_spike": 1.75,
    }


def test_load_alert_min_trust_score_parses_valid_value(tmp_path) -> None:
    config_path = tmp_path / "alerts.yaml"
    config_path.write_text(
        "alerts:\n"
        "  min_trust_score: '72.5'\n",
        encoding="utf-8",
    )

    assert load_alert_min_trust_score(config_path=config_path) == pytest.approx(72.5)


@pytest.mark.parametrize("invalid_value", [-1, 101, "not-a-number"])
def test_load_alert_min_trust_score_rejects_invalid_values(
    tmp_path, invalid_value
) -> None:
    config_path = tmp_path / "alerts.yaml"
    config_path.write_text(
        f"min_trust_score: {invalid_value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_alert_min_trust_score(config_path=config_path)
