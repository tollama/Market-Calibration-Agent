from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AlertReasonCode,
    AlertSeverity,
    BandCalibration,
    ForecastMethod,
    TriggerEventType,
)


class TriggerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: TriggerEventType
    when: date
    keywords: list[str] = Field(min_length=1, max_length=20)

    @field_validator("keywords", mode="after")
    @classmethod
    def validate_keywords(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("keywords must include at least one non-empty value")
        if len(normalized) != len(set(keyword.lower() for keyword in normalized)):
            raise ValueError("keywords must be unique (case-insensitive)")
        return normalized


class QuestionQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    market_id: str = Field(min_length=1, max_length=128)
    llm_model: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(
        min_length=2,
        max_length=32,
        pattern=r"^v\d+\.\d+(?:\.\d+)?$",
    )
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    resolution_risk_score: float = Field(ge=0.0, le=1.0)
    trigger_events: list[TriggerEvent] = Field(default_factory=list, max_length=20)
    rationale_bullets: list[str] = Field(min_length=1, max_length=5)

    @field_validator("rationale_bullets", mode="after")
    @classmethod
    def validate_rationale_bullets(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("rationale_bullets must contain at least one non-empty line")
        if len(normalized) > 5:
            raise ValueError("rationale_bullets must contain at most 5 lines")
        if any(len(line) > 280 for line in normalized):
            raise ValueError("each rationale bullet must be <= 280 characters")
        return normalized


class ForecastBand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ts: datetime
    market_id: str = Field(min_length=1, max_length=128)
    horizon_steps: int = Field(ge=1)
    step_seconds: int = Field(ge=1)
    q10: float = Field(ge=0.0, le=1.0)
    q50: float = Field(ge=0.0, le=1.0)
    q90: float = Field(ge=0.0, le=1.0)
    method: ForecastMethod
    model_id: str = Field(min_length=1, max_length=128)
    band_calibration: BandCalibration

    @field_validator("ts")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_quantile_order(self) -> "ForecastBand":
        if not (self.q10 <= self.q50 <= self.q90):
            raise ValueError("quantiles must satisfy q10 <= q50 <= q90")
        return self


class AlertEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    p_yes: float | None = Field(default=None, ge=0.0, le=1.0)
    q10: float | None = Field(default=None, ge=0.0, le=1.0)
    q90: float | None = Field(default=None, ge=0.0, le=1.0)
    oi_change_1h: float | None = None
    volume_velocity: float | None = Field(default=None, ge=0.0)
    ambiguity_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_band_bounds(self) -> "AlertEvidence":
        if self.q10 is not None and self.q90 is not None and self.q10 > self.q90:
            raise ValueError("evidence.q10 must be <= evidence.q90")
        return self


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ts: datetime
    market_id: str = Field(min_length=1, max_length=128)
    severity: AlertSeverity
    reason_codes: list[AlertReasonCode] = Field(min_length=1, max_length=16)
    evidence: AlertEvidence
    llm_explain_5lines: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("ts")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must be timezone-aware")
        return value

    @field_validator("reason_codes", mode="after")
    @classmethod
    def validate_reason_codes(cls, values: list[AlertReasonCode]) -> list[AlertReasonCode]:
        if len(values) != len(set(values)):
            raise ValueError("reason_codes must not contain duplicates")
        return values

    @field_validator("llm_explain_5lines", mode="after")
    @classmethod
    def validate_explain_lines(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(line) > 140 for line in normalized):
            raise ValueError("each explain line must be <= 140 characters")
        return normalized


class TrustScoreComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liquidity_depth: float = Field(ge=0.0, le=1.0)
    stability: float = Field(ge=0.0, le=1.0)
    question_quality: float = Field(ge=0.0, le=1.0)
    manipulation_suspect: float = Field(ge=0.0, le=1.0)


class TrustScoreWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liquidity_depth: float = Field(default=0.35, ge=0.0, le=1.0)
    stability: float = Field(default=0.25, ge=0.0, le=1.0)
    question_quality: float = Field(default=0.25, ge=0.0, le=1.0)
    manipulation_suspect: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum_to_one(self) -> "TrustScoreWeights":
        total = (
            self.liquidity_depth
            + self.stability
            + self.question_quality
            + self.manipulation_suspect
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError("trust score weights must sum to 1.0")
        return self


class TrustScore(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ts: datetime
    market_id: str = Field(min_length=1, max_length=128)
    trust_score: float = Field(ge=0.0, le=100.0)
    components: TrustScoreComponents
    weights: TrustScoreWeights = Field(default_factory=TrustScoreWeights)
    formula_version: str = Field(default="v1", pattern=r"^v\d+(?:\.\d+)*$")

    @field_validator("ts")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must be timezone-aware")
        return value
