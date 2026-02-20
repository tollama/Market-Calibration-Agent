from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import MarketStatus


class MarketRegistry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    market_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    slug: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    category_tags: list[str] = Field(default_factory=list, max_length=20)
    outcomes: list[str] = Field(min_length=2, max_length=20)
    enable_order_book: bool = Field(alias="enableOrderBook")
    start_ts: datetime
    end_ts: datetime
    status: MarketStatus

    @field_validator("category_tags", mode="after")
    @classmethod
    def validate_category_tags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(tag.lower() for tag in normalized)):
            raise ValueError("category_tags must be unique (case-insensitive)")
        return normalized

    @field_validator("outcomes", mode="after")
    @classmethod
    def validate_outcomes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) < 2:
            raise ValueError("outcomes must include at least two non-empty values")
        if len(normalized) != len(set(outcome.lower() for outcome in normalized)):
            raise ValueError("outcomes must be unique (case-insensitive)")
        return normalized

    @field_validator("start_ts", "end_ts")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_time_bounds(self) -> "MarketRegistry":
        if self.end_ts < self.start_ts:
            raise ValueError("end_ts must be greater than or equal to start_ts")
        return self
