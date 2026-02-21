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
    source: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)
    resolved_at: Optional[datetime] = None
    generated_at: Optional[datetime] = None


class MarketDetailResponse(BaseModel):
    market_id: str
    category: Optional[str] = None
    liquidity_bucket: Optional[str] = None
    trust_score: Optional[float] = None
    as_of: Optional[datetime] = None
    latest_alert: Optional[AlertItem] = None


class MarketsResponse(BaseModel):
    items: List[MarketDetailResponse] = Field(default_factory=list)
    total: int


class MarketMetricsResponse(BaseModel):
    market_id: str
    scoreboard_by_window: List[Dict[str, Any]] = Field(default_factory=list)
    alert_total: int = 0
    alert_severity_counts: Dict[str, int] = Field(default_factory=dict)


class TSFMModelConfig(BaseModel):
    provider: str = "tollama"
    model_name: str = "chronos"
    model_version: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class TSFMTransformConfig(BaseModel):
    space: str = "logit"
    eps: float = 1e-6


class TSFMForecastRequest(BaseModel):
    market_id: str
    as_of_ts: datetime
    freq: str = "5m"
    horizon_steps: int = 12
    quantiles: List[float] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
    y: List[float]
    y_ts: Optional[List[datetime]] = None
    observed_ts: Optional[datetime] = None
    max_gap_minutes: Optional[int] = None
    x_past: Dict[str, List[float]] = Field(default_factory=dict)
    x_future: Dict[str, List[float]] = Field(default_factory=dict)
    transform: TSFMTransformConfig = Field(default_factory=TSFMTransformConfig)
    model: TSFMModelConfig = Field(default_factory=TSFMModelConfig)
    liquidity_bucket: Optional[str] = None


class TSFMForecastResponse(BaseModel):
    market_id: str
    as_of_ts: datetime
    freq: str
    horizon_steps: int
    quantiles: List[float]
    yhat_q: Dict[str, List[float]]
    meta: Dict[str, Any] = Field(default_factory=dict)
    conformal_last_step: Optional[Dict[str, Any]] = None


class MarketComparisonRequest(BaseModel):
    forecast: TSFMForecastRequest
    baseline_liquidity_bucket: str = "low"


class MarketComparisonResponse(BaseModel):
    market_id: str
    baseline: TSFMForecastResponse
    tollama: TSFMForecastResponse
    delta_last_q50: Optional[float] = None
