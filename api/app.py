"""Read-only FastAPI application for derived artifacts."""

from __future__ import annotations

from datetime import datetime
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


@app.get("/scoreboard", response_model=ScoreboardResponse)
def get_scoreboard(
    window: str = Query(default="90d"),
    tag: Optional[str] = Query(default=None),
    liquidity_bucket: Optional[str] = Query(default=None),
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

    items = [ScoreboardItem(**record) for record in records]
    return ScoreboardResponse(items=items, total=len(items))


@app.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: LocalDerivedStore = Depends(get_derived_store),
) -> AlertsResponse:
    records, total = store.load_alerts(since=since, limit=limit, offset=offset)
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
        raise HTTPException(status_code=404, detail=f"Postmortem not found: {market_id}")

    return PostmortemResponse(
        market_id=market_id,
        content=content,
        source_path=str(source_path),
    )
