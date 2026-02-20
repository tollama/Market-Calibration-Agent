from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


def normalize_dt(value: date | datetime | str | None) -> str:
    """Convert supported date-like values into YYYY-MM-DD."""
    if value is None:
        return datetime.utcnow().date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ValueError("dt string cannot be empty.")
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            if candidate.endswith("Z"):
                candidate = f"{candidate[:-1]}+00:00"
            try:
                return datetime.fromisoformat(candidate).date().isoformat()
            except ValueError as exc:
                raise ValueError(f"Invalid dt value: {value!r}") from exc
    raise TypeError(f"Unsupported dt type: {type(value)!r}")


def _ensure_suffix(filename: str, suffix: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise ValueError("filename cannot be empty.")
    if cleaned.endswith(suffix):
        return cleaned
    return f"{cleaned}{suffix}"


def _dedupe_records(
    records: Sequence[Mapping[str, Any]], dedupe_key: str | None
) -> list[dict[str, Any]]:
    rows = [dict(record) for record in records]
    if dedupe_key is None:
        return rows

    deduped: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for row in rows:
        key = row.get(dedupe_key)
        if key is None:
            deduped.append(row)
            continue
        normalized_key = str(key)
        if normalized_key in index_by_key:
            deduped[index_by_key[normalized_key]] = row
            continue
        index_by_key[normalized_key] = len(deduped)
        deduped.append(row)
    return deduped


def _is_missing_parquet_engine(exc: Exception) -> bool:
    message = str(exc).lower()
    return isinstance(exc, ImportError) or (
        "unable to find a usable engine" in message
        or "optional dependency" in message
        or "pyarrow" in message
        or "fastparquet" in message
    )


class RawWriter:
    """Write raw records to JSONL partitions under raw/<dataset>/dt=YYYY-MM-DD."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def partition_path(self, dataset: str, dt: date | datetime | str | None = None) -> Path:
        return self.root / "raw" / dataset / f"dt={normalize_dt(dt)}"

    def write(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.jsonl",
        dedupe_key: str | None = None,
    ) -> Path:
        rows = _dedupe_records(list(records), dedupe_key)
        output_path = self.partition_path(dataset, dt) / _ensure_suffix(filename, ".jsonl")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_name(f".{output_path.name}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    json.dump(row, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
            temp_path.replace(output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return output_path


class ParquetWriter:
    """Write derived records to parquet partitions under derived/<dataset>/dt=YYYY-MM-DD."""

    def __init__(self, root: str | Path, *, compression: str = "snappy") -> None:
        self.root = Path(root)
        self.compression = compression

    def partition_path(self, dataset: str, dt: date | datetime | str | None = None) -> Path:
        return self.root / "derived" / dataset / f"dt={normalize_dt(dt)}"

    def write(
        self,
        data: pd.DataFrame | Sequence[Mapping[str, Any]],
        *,
        dataset: str,
        dt: date | datetime | str | None = None,
        filename: str = "data.parquet",
        dedupe_key: str | None = None,
        index: bool = False,
    ) -> Path:
        frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(list(data))
        if dedupe_key is not None and dedupe_key in frame.columns:
            frame = frame.drop_duplicates(subset=[dedupe_key], keep="last")

        output_path = self.partition_path(dataset, dt) / _ensure_suffix(filename, ".parquet")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_name(f".{output_path.name}.tmp")
        try:
            frame.to_parquet(temp_path, index=index, compression=self.compression)
            temp_path.replace(output_path)
        except Exception as exc:
            if _is_missing_parquet_engine(exc):
                raise RuntimeError(
                    "Parquet support requires 'pyarrow' or 'fastparquet'."
                ) from exc
            raise
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return output_path
