from __future__ import annotations

import json

import pytest

from calibration.conformal import ConformalAdjustment
from calibration.conformal_state import (
    load_conformal_adjustment,
    load_cptc_state,
    save_conformal_adjustment,
    save_cptc_state,
)


def test_save_and_load_conformal_adjustment_roundtrip(tmp_path) -> None:
    path = tmp_path / "conformal_state.json"
    adjustment = ConformalAdjustment(
        target_coverage=0.8,
        quantile_level=0.9,
        center_shift=0.03,
        width_scale=1.2,
        sample_size=500,
    )

    save_conformal_adjustment(adjustment, path=path, metadata={"source": "unit-test"})
    loaded = load_conformal_adjustment(path)

    assert loaded == adjustment


def test_load_conformal_adjustment_missing_file_returns_none(tmp_path) -> None:
    assert load_conformal_adjustment(tmp_path / "missing.json") is None


def test_load_conformal_adjustment_supports_legacy_flat_payload(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "target_coverage": 0.8,
                "quantile_level": 0.9,
                "center_shift": 0.03,
                "width_scale": 1.1,
                "sample_size": 100,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_conformal_adjustment(path)
    assert loaded is not None
    assert loaded.width_scale == pytest.approx(1.1)


def test_save_and_load_cptc_state_roundtrip(tmp_path) -> None:
    path = tmp_path / "cptc_state.json"
    save_cptc_state(
        change_point_detected=True,
        change_point_index=30,
        test_statistic=2.5,
        threshold=1.8,
        n_pre=30,
        n_post=20,
        path=path,
        metadata={"source": "unit-test"},
    )
    loaded = load_cptc_state(path)
    assert loaded is not None
    assert loaded["change_point"]["detected"] is True
    assert loaded["change_point"]["index"] == 30
    assert loaded["change_point"]["test_statistic"] == pytest.approx(2.5)
    assert loaded["conformal_method"] == "cptc"


def test_load_cptc_state_missing_file_returns_none(tmp_path) -> None:
    assert load_cptc_state(tmp_path / "missing.json") is None


def test_save_cptc_state_no_change_point(tmp_path) -> None:
    path = tmp_path / "cptc_state.json"
    save_cptc_state(
        change_point_detected=False,
        change_point_index=None,
        test_statistic=0.5,
        threshold=1.8,
        n_pre=50,
        n_post=0,
        path=path,
    )
    loaded = load_cptc_state(path)
    assert loaded is not None
    assert loaded["change_point"]["detected"] is False
    assert loaded["change_point"]["index"] is None
