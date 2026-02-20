from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from calibration.metrics import summarize_metrics
from calibration.trust_score import compute_trust_score
from pipelines.build_scoreboard_artifacts import (
    build_scoreboard_rows,
    render_scoreboard_markdown,
    write_scoreboard_artifacts,
)
from storage.writers import ParquetWriter


def test_build_scoreboard_rows_computes_metrics_and_trust_score() -> None:
    rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.80,
            "label": 1,
            "liquidity_depth": 0.90,
            "stability": 0.60,
            "question_quality": 0.80,
            "manipulation_suspect": 0.10,
        },
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.60,
            "label": 1,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.30,
            "label": 0,
            "liquidity_depth": 0.20,
            "stability": 0.40,
            "question_quality": 0.30,
            "manipulation_suspect": 0.70,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.40,
            "label": 1,
            "liquidity_depth": 0.30,
            "stability": 0.50,
            "question_quality": 0.40,
            "manipulation_suspect": 0.60,
        },
    ]

    score_rows, summary_metrics = build_scoreboard_rows(rows)

    assert set(summary_metrics["by_category"]) == {"politics", "sports"}
    assert set(summary_metrics["by_liquidity_bucket"]) == {"high", "low"}

    expected_global = summarize_metrics([0.80, 0.60, 0.30, 0.40], [1, 1, 0, 1])
    assert summary_metrics["global"]["brier"] == pytest.approx(
        expected_global["brier"], rel=0, abs=1e-12
    )
    assert summary_metrics["global"]["log_loss"] == pytest.approx(
        expected_global["log_loss"], rel=0, abs=1e-12
    )
    assert summary_metrics["global"]["ece"] == pytest.approx(
        expected_global["ece"], rel=0, abs=1e-12
    )

    by_market = {row["market_id"]: row for row in score_rows}
    mkt1 = by_market["mkt-1"]
    mkt2 = by_market["mkt-2"]

    expected_mkt1_metrics = summarize_metrics([0.80, 0.60], [1, 1])
    assert mkt1["brier"] == pytest.approx(expected_mkt1_metrics["brier"], rel=0, abs=1e-12)
    assert mkt1["log_loss"] == pytest.approx(expected_mkt1_metrics["log_loss"], rel=0, abs=1e-12)
    assert mkt1["ece"] == pytest.approx(expected_mkt1_metrics["ece"], rel=0, abs=1e-12)

    mkt1_components = {
        "liquidity_depth": (0.90 + 0.50) / 2.0,
        "stability": (0.60 + 0.50) / 2.0,
        "question_quality": (0.80 + 0.50) / 2.0,
        "manipulation_suspect": (0.10 + 0.50) / 2.0,
    }
    assert math.isclose(
        float(mkt1["trust_score"]),
        compute_trust_score(mkt1_components),
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    mkt2_components = {
        "liquidity_depth": (0.20 + 0.30) / 2.0,
        "stability": (0.40 + 0.50) / 2.0,
        "question_quality": (0.30 + 0.40) / 2.0,
        "manipulation_suspect": (0.70 + 0.60) / 2.0,
    }
    assert math.isclose(
        float(mkt2["trust_score"]),
        compute_trust_score(mkt2_components),
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_render_scoreboard_markdown_contains_sections() -> None:
    rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "pred": 0.70,
            "label": 1,
        },
        {
            "market_id": "mkt-2",
            "category": "sports",
            "liquidity_bucket": "low",
            "pred": 0.20,
            "label": 0,
        },
    ]

    score_rows, summary_metrics = build_scoreboard_rows(rows)
    markdown = render_scoreboard_markdown(score_rows, summary_metrics)

    assert "# Scoreboard Report" in markdown
    assert "## Global Metrics" in markdown
    assert "## Segment Metrics (Category)" in markdown
    assert "## Market Scoreboard" in markdown
    assert "mkt-1" in markdown
    assert "mkt-2" in markdown


def test_write_scoreboard_artifacts_writes_expected_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_write(
        self: ParquetWriter,
        data,
        *,
        dataset: str,
        dt=None,
        filename: str = "data.parquet",
        dedupe_key=None,
        index: bool = False,
    ) -> Path:
        captured["dataset"] = dataset
        captured["dt"] = dt
        captured["filename"] = filename
        captured["dedupe_key"] = dedupe_key
        captured["index"] = index
        output = self.partition_path(dataset, dt) / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(list(data), sort_keys=True), encoding="utf-8")
        return output

    monkeypatch.setattr(ParquetWriter, "write", fake_write, raising=True)

    score_rows = [
        {
            "market_id": "mkt-1",
            "category": "politics",
            "liquidity_bucket": "high",
            "sample_size": 2,
            "trust_score": 74.0,
            "brier": 0.10,
            "log_loss": 0.30,
            "ece": 0.05,
            "liquidity_depth": 0.7,
            "stability": 0.6,
            "question_quality": 0.8,
            "manipulation_suspect": 0.2,
        }
    ]
    summary_metrics = {
        "global": {"brier": 0.10, "log_loss": 0.30, "ece": 0.05},
        "by_category": {"politics": {"brier": 0.10, "log_loss": 0.30, "ece": 0.05}},
        "by_liquidity_bucket": {"high": {"brier": 0.10, "log_loss": 0.30, "ece": 0.05}},
    }

    parquet_path, report_path = write_scoreboard_artifacts(
        score_rows,
        summary_metrics,
        root=tmp_path,
        dt="2026-02-20",
    )

    assert captured["dataset"] == "metrics"
    assert captured["dt"] == "2026-02-20"
    assert captured["filename"] == "scoreboard.parquet"
    assert captured["dedupe_key"] is None
    assert captured["index"] is False

    assert parquet_path == tmp_path / "derived" / "metrics" / "dt=2026-02-20" / "scoreboard.parquet"
    assert report_path == tmp_path / "derived" / "reports" / "scoreboard-2026-02-20.md"

    parquet_payload = json.loads(parquet_path.read_text(encoding="utf-8"))
    assert parquet_payload == score_rows

    markdown = report_path.read_text(encoding="utf-8")
    assert "Scoreboard Report" in markdown
    assert "mkt-1" in markdown
