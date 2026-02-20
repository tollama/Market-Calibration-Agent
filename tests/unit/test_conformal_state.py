from __future__ import annotations

import json

import pytest

from calibration.conformal import ConformalAdjustment
from calibration.conformal_state import load_conformal_adjustment, save_conformal_adjustment


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
