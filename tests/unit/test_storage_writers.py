import json
from pathlib import Path

import pandas as pd
import pytest

from storage.writers import ParquetWriter, RawWriter


def test_raw_writer_creates_dt_partition_and_is_idempotent(tmp_path: Path) -> None:
    writer = RawWriter(tmp_path)
    records = [
        {"id": "m1", "question": "first"},
        {"id": "m2", "question": "second"},
        {"id": "m1", "question": "first-updated"},
    ]

    output_path = writer.write(
        records,
        dataset="gamma",
        dt="2026-02-20",
        filename="markets",
    )

    assert output_path == tmp_path / "raw" / "gamma" / "dt=2026-02-20" / "markets.jsonl"
    first_run_lines = output_path.read_text(encoding="utf-8").splitlines()
    first_run_rows = [json.loads(line) for line in first_run_lines]
    assert len(first_run_rows) == 3

    second_output_path = writer.write(
        records,
        dataset="gamma",
        dt="2026-02-20",
        filename="markets",
    )
    assert second_output_path == output_path
    second_run_lines = output_path.read_text(encoding="utf-8").splitlines()
    assert second_run_lines == first_run_lines


def test_parquet_writer_creates_dt_partition_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_to_parquet(self: pd.DataFrame, path: Path, **_: object) -> None:
        payload = self.to_dict(orient="records")
        Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet, raising=True)

    writer = ParquetWriter(tmp_path)
    records = [
        {"id": "e1", "value": 1.0},
        {"id": "e2", "value": 2.0},
        {"id": "e1", "value": 3.0},
    ]

    output_path = writer.write(
        records,
        dataset="features",
        dt="2026-02-20",
        filename="snapshot",
    )

    assert output_path == tmp_path / "derived" / "features" / "dt=2026-02-20" / "snapshot.parquet"
    first_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(first_payload) == 3

    second_output_path = writer.write(
        records,
        dataset="features",
        dt="2026-02-20",
        filename="snapshot",
    )
    assert second_output_path == output_path
    second_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert second_payload == first_payload


def test_parquet_writer_raises_helpful_error_when_engine_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_engine(self: pd.DataFrame, path: Path, **_: object) -> None:
        raise ImportError("Missing optional dependency 'pyarrow'.")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", missing_engine, raising=True)

    writer = ParquetWriter(tmp_path)
    with pytest.raises(RuntimeError, match="pyarrow|fastparquet"):
        writer.write(
            [{"id": "x1", "value": 1}],
            dataset="features",
            dt="2026-02-20",
            filename="snapshot",
        )
