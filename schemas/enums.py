from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    """Base enum with stable string serialization."""

    def __str__(self) -> str:
        return self.value


class MarketStatus(StringEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    VOID = "VOID"
    UNRESOLVED = "UNRESOLVED"


class LiquidityBucket(StringEnum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class DataSource(StringEnum):
    GAMMA = "gamma"
    SUBGRAPH = "subgraph"
    WEBSOCKET = "websocket"


class TriggerEventType(StringEnum):
    ELECTION = "ELECTION"
    CPI = "CPI"
    COURT = "COURT"
    EARNINGS = "EARNINGS"
    OTHER = "OTHER"


class ForecastMethod(StringEnum):
    TSFM = "TSFM"
    EWMA = "EWMA"
    KALMAN = "KALMAN"
    ROLLING_QUANTILE = "ROLLING_QUANTILE"


class BandCalibration(StringEnum):
    RAW = "raw"
    CONFORMAL = "conformal"


class AlertSeverity(StringEnum):
    HIGH = "HIGH"
    MED = "MED"
    FYI = "FYI"


class AlertReasonCode(StringEnum):
    BAND_BREACH = "BAND_BREACH"
    LOW_OI_CONFIRMATION = "LOW_OI_CONFIRMATION"
    LOW_AMBIGUITY = "LOW_AMBIGUITY"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    OI_DIVERGENCE = "OI_DIVERGENCE"
    OTHER = "OTHER"
