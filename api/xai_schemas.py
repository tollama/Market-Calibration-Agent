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


# ---- Constraint Verification API schemas ----


class ConstraintVerifyRequest(BaseModel):
    """Request to verify constraints against a prediction."""

    prediction: float = Field(description="Predicted probability")
    interval: List[float] = Field(
        description="Prediction interval [p_low, p_high]",
        min_length=2,
        max_length=2,
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Context values (trust_score, market_volume_24h, etc.)",
    )
    constraints: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Custom constraint definitions. If None, uses defaults.",
    )


class ConstraintVerifyResponse(BaseModel):
    """Response from constraint verification."""

    constraint_satisfied: bool
    risk_category: str
    violations: List[ConstraintViolationItem] = Field(default_factory=list)
    constraints_checked: int = 0
    verification_time_ms: Optional[float] = None


class ConstraintVerifyBatchRequest(BaseModel):
    """Batch constraint verification request."""

    items: List[ConstraintVerifyRequest]
    constraints: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Shared custom constraints for all items.",
    )


class ConstraintVerifyBatchResponse(BaseModel):
    """Batch constraint verification response."""

    results: List[ConstraintVerifyResponse]
    total: int


# ---- Audit Trail API schemas ----


class AuditTrailEntry(BaseModel):
    """Single audit trail entry for API responses."""

    agent_id: str
    session_id: str = ""
    timestamp: str
    input_hash: str
    output_hash: str
    trust_score_at_step: float
    constraint_checks_passed: bool
    layer_outputs: Dict[str, Any] = Field(default_factory=dict)
    chain_hash: str = ""


class AuditTrailResponse(BaseModel):
    """Audit trail response."""

    session_id: Optional[str] = None
    entries: List[AuditTrailEntry] = Field(default_factory=list)
    total: int = 0
    chain_valid: bool = True


# ---- Orchestrated Trust Intelligence API schemas ----


class OrchestratedTrustRequest(BaseModel):
    """Request for orchestrated trust intelligence with re-evaluation."""

    prediction_probability: float = Field(ge=0.0, le=1.0)
    features: Optional[Dict[str, float]] = None
    context: Optional[Dict[str, Any]] = None
    constraints: Optional[List[Dict[str, Any]]] = None
    confidence_level: float = Field(default=0.9, ge=0.0, le=1.0)
    trust_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=0, le=10)


class ReEvaluationAttemptItem(BaseModel):
    """Record of a single re-evaluation attempt."""

    attempt: int
    strategy: str
    trust_score: float
    recovered: bool
    adjustments: Dict[str, Any] = Field(default_factory=dict)


class OrchestratedTrustResponse(BaseModel):
    """Response from orchestrated trust intelligence."""

    trust_score: float
    needs_escalation: bool
    was_retried: bool
    total_attempts: int
    attempts: List[ReEvaluationAttemptItem] = Field(default_factory=list)
    binding_constraints: List[str] = Field(default_factory=list)
    pipeline_result: TrustIntelligenceResponse


# ---- Model Card and Compliance API schemas ----


class ModelCardRequest(BaseModel):
    """Request for trust intelligence model card generation."""

    model_info: Optional[Dict[str, Any]] = None
    include_pipeline_result: bool = Field(
        default=True,
        description="Run pipeline to populate model card with live data",
    )
    prediction_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    format: str = Field(default="json", description="Output format: json or markdown")


class ModelCardResponse(BaseModel):
    """Model card response."""

    model_card: Optional[Dict[str, Any]] = None
    markdown: Optional[str] = None
    format: str = "json"


class ComplianceReportRequest(BaseModel):
    """Request for compliance report generation."""

    vertical: str = Field(default="general", description="Industry vertical")
    report_period: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=10000)


class ComplianceReportResponse(BaseModel):
    """Compliance report response."""

    report: Dict[str, Any] = Field(default_factory=dict)
