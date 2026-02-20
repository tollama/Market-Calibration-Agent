from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines.ingest_gamma_raw import run_ingest_gamma_raw
from storage.writers import RawWriter


class _Connector:
    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [{"record_id": "m-1"}]

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = limit, params
        return [{"record_id": "e-1"}]


def test_i01_gamma_raw_path_contract_exposes_canonical_prd_dt_partition(tmp_path: Path) -> None:
    """Traceability: PRD1 I-01 (raw store contract for gamma dt partition path metadata)."""
    dt = "2026-02-24"
    summary = run_ingest_gamma_raw(connector=_Connector(), raw_writer=RawWriter(tmp_path), dt=dt)

    path_meta = summary["path_meta"]
    assert path_meta["raw_gamma_dt_relpath"] == f"raw/gamma/dt={dt}"
    assert Path(path_meta["raw_gamma_dt_path"]).relative_to(tmp_path) == Path(
        "raw", "gamma", f"dt={dt}"
    )
