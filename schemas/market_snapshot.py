from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import DataSource, LiquidityBucket


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ts: datetime
    market_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    p_yes: float = Field(ge=0.0, le=1.0)
    p_no: float = Field(ge=0.0, le=1.0)
    volume_24h: float = Field(ge=0.0)
    open_interest: float = Field(ge=0.0)
    num_traders_proxy: int = Field(ge=0)
    liquidity_bucket: LiquidityBucket
    tte_seconds: int = Field(ge=0)
    data_source: list[DataSource] = Field(min_length=1, max_length=3)

    @field_validator("ts")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must be timezone-aware")
        return value

    @field_validator("data_source", mode="after")
    @classmethod
    def validate_unique_data_sources(cls, values: list[DataSource]) -> list[DataSource]:
        if len(values) != len(set(values)):
            raise ValueError("data_source must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_probability_mass(self) -> "MarketSnapshot":
        total = self.p_yes + self.p_no
        if abs(total - 1.0) > 1e-3:
            raise ValueError("p_yes + p_no must sum to 1.0 (±1e-3)")
        return self
