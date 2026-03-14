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


# ---- Trust Intelligence Pipeline v3.0 schemas ----


class SHAPFeatureItem(BaseModel):
    feature_name: str
    shap_value: float
    rank: int
    direction: str


class ConstraintViolationItem(BaseModel):
    constraint_name: str
    constraint_type: str
    expected: str
    actual: str
    severity: str


class TrustIntelligenceResponse(BaseModel):
    """Full Trust Intelligence Pipeline v3.0 output for a market."""

    market_id: str
    pipeline_version: str = "3.0"
    trust_score: float
    trust_score_v1: Optional[float] = None

    # L1: Uncertainty
    entropy: float
    normalized_uncertainty: float
    prediction_probability: float

    # L2: Conformal
    conformal_method: str
    conformal_p_low: float
    conformal_p_high: float
    coverage_validity: bool
    coverage_tightness: float

    # L3: SHAP
    shap_stability: float
    shap_iterations: int
    top_features: List[SHAPFeatureItem] = Field(default_factory=list)

    # L4: Constraints
    constraint_satisfied: bool
    risk_category: str
    violations: List[ConstraintViolationItem] = Field(default_factory=list)
    constraints_checked: int = 0

    # L5: Aggregation
    weights: Dict[str, float] = Field(default_factory=dict)
    component_scores: Dict[str, float] = Field(default_factory=dict)
    calibration_status: str = "well_calibrated"
    ece: float = 0.0
    ocr: float = 0.0

    # Audit
    chain_of_trust_entries: int = 0
