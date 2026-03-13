"""XAI-specific API schemas for the market-calibration trust layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TrustComponentContribution(BaseModel):
    name: str
    raw_value: Optional[float] = None
    effective_value: Optional[float] = None
    weight: Optional[float] = None
    weighted_contribution: Optional[float] = None
    direction: Optional[str] = None
    explanation: Optional[str] = None


class TrustExplanationRequest(BaseModel):
    market_id: str
    ts: Optional[datetime] = None
    components: Dict[str, float] = Field(default_factory=dict)
    weights: Dict[str, float] = Field(default_factory=dict)
    trust_score: Optional[float] = None
    calibration_metrics: Dict[str, Any] = Field(default_factory=dict)
    drift_report: Dict[str, Any] = Field(default_factory=dict)
    liquidity_bucket: Optional[str] = None
    category: Optional[str] = None


class TrustExplanationResponse(BaseModel):
    market_id: str
    mode: str = "deterministic"
    trust_score: Optional[float] = None
    summary: str
    confidence_level: str
    component_breakdown: List[TrustComponentContribution] = Field(default_factory=list)
    calibration_evidence: Dict[str, Any] = Field(default_factory=dict)
    drift_evidence: Dict[str, Any] = Field(default_factory=dict)
    reason_codes: List[str] = Field(default_factory=list)
    narrative: List[str] = Field(default_factory=list)
