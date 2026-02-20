"""API response schemas for read-only endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScoreboardItem(BaseModel):
    market_id: str
    window: str = "90d"
    trust_score: Optional[float] = None
    brier: Optional[float] = None
    logloss: Optional[float] = None
    ece: Optional[float] = None
    liquidity_bucket: Optional[str] = None
    category: Optional[str] = None
    as_of: Optional[datetime] = None


class ScoreboardResponse(BaseModel):
    items: List[ScoreboardItem] = Field(default_factory=list)
    total: int


class AlertItem(BaseModel):
    market_id: str
    ts: datetime
    severity: str
    reason_codes: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    llm_explain_5lines: List[str] = Field(default_factory=list)
    alert_id: Optional[str] = None


class AlertsResponse(BaseModel):
    items: List[AlertItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class PostmortemResponse(BaseModel):
    market_id: str
    content: str
    source_path: str
