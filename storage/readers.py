from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .writers import normalize_dt


class RawReader:
    """Read JSONL partitions under raw/<dataset>/dt=YYYY-MM-DD."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def partition_path(self, dataset: str, dt: date | datetime | str | None = None) -> Path:
        return self.root / "raw" / dataset / f"dt={normalize_dt(dt)}"

    def read(
        self,
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.jsonl",
    ) -> list[dict[str, Any]]:
        jsonl_name = filename if filename.endswith(".jsonl") else f"{filename}.jsonl"
        path = self.partition_path(dataset, dt) / jsonl_name
        return self._read_jsonl_file(path)

    def read_partition(
        self,
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        partition = self.partition_path(dataset, dt)
        if not partition.exists():
            return []

        rows: list[dict[str, Any]] = []
        for file_path in sorted(partition.glob("*.jsonl")):
            rows.extend(self._read_jsonl_file(file_path))
        return rows

    @staticmethod
    def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                cleaned = line.strip()
                if not cleaned:
                    continue
                rows.append(json.loads(cleaned))
        return rows


class ParquetReader:
    """Read parquet partitions under derived/<dataset>/dt=YYYY-MM-DD."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def partition_path(self, dataset: str, dt: date | datetime | str | None = None) -> Path:
        return self.root / "derived" / dataset / f"dt={normalize_dt(dt)}"

    def read(
        self,
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.parquet",
    ) -> pd.DataFrame:
        parquet_name = filename if filename.endswith(".parquet") else f"{filename}.parquet"
        path = self.partition_path(dataset, dt) / parquet_name
        return pd.read_parquet(path)

    def read_partition(
        self,
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
    ) -> pd.DataFrame:
        partition = self.partition_path(dataset, dt)
        if not partition.exists():
            return pd.DataFrame()

        parquet_paths = sorted(partition.glob("*.parquet"))
        if not parquet_paths:
            return pd.DataFrame()

        frames = [pd.read_parquet(path) for path in parquet_paths]
        return pd.concat(frames, ignore_index=True)
