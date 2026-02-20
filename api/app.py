"""Read-only FastAPI application for derived artifacts."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from .dependencies import LocalDerivedStore, get_derived_store
from .schemas import (
    AlertItem,
    AlertsResponse,
    PostmortemResponse,
    ScoreboardItem,
    ScoreboardResponse,
)

app = FastAPI(title="Market Calibration Read-Only API", version="0.1.0")


def _select_latest_postmortem_path(
    *,
    store: LocalDerivedStore,
    market_id: str,
) -> Optional[Path]:
    prefix = f"{market_id}_"
    latest_path: Optional[Path] = None
    latest_key: Optional[tuple[int, date, str]] = None

    for path in store.postmortem_dir.glob("*.md"):
        if not path.is_file():
            continue
        if not path.name.startswith(prefix):
            continue

        resolved_date_token = path.stem[len(prefix) :]
        try:
            resolved_date = date.fromisoformat(resolved_date_token)
            candidate_key = (1, resolved_date, resolved_date_token)
        except ValueError:
            candidate_key = (0, date.min, resolved_date_token)

        if latest_key is None or candidate_key > latest_key:
            latest_key = candidate_key
            latest_path = path

    return latest_path


@app.get("/scoreboard", response_model=ScoreboardResponse)
def get_scoreboard(
    window: str = Query(default="90d"),
    tag: Optional[str] = Query(default=None),
    liquidity_bucket: Optional[str] = Query(default=None),
    min_trust_score: Optional[float] = Query(default=None),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> ScoreboardResponse:
    records = store.load_scoreboard(window=window)

    if tag:
        records = [record for record in records if record.get("category") == tag]
    if liquidity_bucket:
        records = [
            record
            for record in records
            if record.get("liquidity_bucket") == liquidity_bucket
        ]
    if min_trust_score is not None:
        records = [
            record
            for record in records
            if isinstance(record.get("trust_score"), (int, float))
            and float(record["trust_score"]) >= min_trust_score
        ]

    items = [ScoreboardItem(**record) for record in records]
    return ScoreboardResponse(items=items, total=len(items))


@app.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    severity: Optional[str] = Query(default=None),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> AlertsResponse:
    if severity is None:
        records, total = store.load_alerts(since=since, limit=limit, offset=offset)
    else:
        normalized_severity = severity.upper()
        allowed_severities = {"HIGH", "MED", "FYI"}
        if normalized_severity not in allowed_severities:
            raise HTTPException(
                status_code=422,
                detail="Invalid severity. Expected one of: HIGH, MED, FYI.",
            )

        all_records, _ = store.load_alerts(since=since, limit=10**9, offset=0)
        filtered = [
            record
            for record in all_records
            if str(record.get("severity", "")).upper() == normalized_severity
        ]
        total = len(filtered)
        records = filtered[offset : offset + limit]

    items = [AlertItem(**record) for record in records]
    return AlertsResponse(items=items, total=total, limit=limit, offset=offset)


@app.get("/postmortem/{market_id}", response_model=PostmortemResponse)
def get_postmortem(
    market_id: str,
    store: LocalDerivedStore = Depends(get_derived_store),
) -> PostmortemResponse:
    try:
        content, source_path = store.load_postmortem(market_id=market_id)
    except FileNotFoundError:
        latest_path = _select_latest_postmortem_path(store=store, market_id=market_id)
        if latest_path is None:
            raise HTTPException(
                status_code=404,
                detail=f"Postmortem not found: {market_id}",
            )
        content = latest_path.read_text(encoding="utf-8")
        source_path = latest_path

    return PostmortemResponse(
        market_id=market_id,
        content=content,
        source_path=str(source_path),
    )
