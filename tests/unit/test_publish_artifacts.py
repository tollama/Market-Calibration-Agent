from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipelines.publish_artifacts import write_publish_artifacts


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_write_publish_artifacts_writes_scoreboard_and_alert_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_to_parquet(self: pd.DataFrame, path: Path, **_: object) -> None:
        payload = self.to_dict(orient="records")
        Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet, raising=True)

    scoreboard_rows = [
        {"market_id": "m1", "trust_score": 73.5},
        {"market_id": "m2", "trust_score": 61.2},
    ]
    alert_rows = [
        {"alert_id": "a1", "market_id": "m1", "severity": "HIGH"},
        {"alert_id": "a2", "market_id": "m2", "severity": "MED"},
    ]

    summary = write_publish_artifacts(
        root=tmp_path,
        dt="2026-02-20",
        scoreboard_rows=scoreboard_rows,
        alert_rows=alert_rows,
    )

    expected_scoreboard_path = (
        tmp_path / "derived" / "metrics" / "dt=2026-02-20" / "scoreboard.parquet"
    )
    expected_alerts_path = tmp_path / "raw" / "alerts" / "dt=2026-02-20" / "alerts.jsonl"

    assert summary == {
        "scoreboard_path": str(expected_scoreboard_path),
        "alerts_path": str(expected_alerts_path),
        "scoreboard_count": 2,
        "alert_count": 2,
    }

    assert expected_scoreboard_path.exists()
    assert expected_alerts_path.exists()
    assert json.loads(expected_scoreboard_path.read_text(encoding="utf-8")) == scoreboard_rows
    assert _read_jsonl(expected_alerts_path) == alert_rows


def test_write_publish_artifacts_handles_none_and_empty_rows(tmp_path: Path) -> None:
    summary = write_publish_artifacts(
        root=tmp_path,
        dt="2026-02-20",
        scoreboard_rows=None,
        alert_rows=[],
    )

    assert summary == {
        "scoreboard_path": None,
        "alerts_path": None,
        "scoreboard_count": 0,
        "alert_count": 0,
    }
    assert not (tmp_path / "derived").exists()
    assert not (tmp_path / "raw").exists()


def test_write_publish_artifacts_writes_alerts_without_scoreboard(tmp_path: Path) -> None:
    alert_rows = [{"alert_id": "a1", "market_id": "m1", "severity": "HIGH"}]

    summary = write_publish_artifacts(
        root=tmp_path,
        dt="2026-02-20",
        scoreboard_rows=[],
        alert_rows=alert_rows,
    )

    expected_alerts_path = tmp_path / "raw" / "alerts" / "dt=2026-02-20" / "alerts.jsonl"
    assert summary == {
        "scoreboard_path": None,
        "alerts_path": str(expected_alerts_path),
        "scoreboard_count": 0,
        "alert_count": 1,
    }
    assert expected_alerts_path.exists()
    assert _read_jsonl(expected_alerts_path) == alert_rows
