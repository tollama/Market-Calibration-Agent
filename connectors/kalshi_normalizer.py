"""Normalizer that maps Kalshi API responses to MarketSnapshot-compatible dicts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class KalshiNormalizer:
    """Converts raw Kalshi market/event records into a canonical dict format
    compatible with ``MarketSnapshot`` and ``MarketRegistry``."""

    PLATFORM = "kalshi"

    def normalize_market(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single Kalshi market record."""
        ticker = raw.get("ticker", "")
        market_id = f"kalshi:{ticker}" if ticker else ""
        event_ticker = raw.get("event_ticker", "")
        event_id = f"kalshi:{event_ticker}" if event_ticker else ""

        yes_bid = _to_float(raw.get("yes_bid"), default=0.0) / 100.0
        yes_ask = _to_float(raw.get("yes_ask"), default=0.0) / 100.0
        p_yes = (yes_bid + yes_ask) / 2.0 if (yes_bid + yes_ask) > 0 else 0.5
        p_yes = max(0.0, min(1.0, p_yes))
        p_no = 1.0 - p_yes

        volume = _to_float(raw.get("volume"), default=0.0)
        open_interest = _to_float(raw.get("open_interest"), default=0.0)

        close_time_str = raw.get("close_time") or raw.get("expiration_time")
        tte_seconds = 0
        if close_time_str:
            try:
                close_dt = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                tte_seconds = max(0, int((close_dt - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError):
                tte_seconds = 0

        return {
            "market_id": market_id,
            "event_id": event_id,
            "p_yes": round(p_yes, 6),
            "p_no": round(p_no, 6),
            "volume_24h": volume,
            "open_interest": open_interest,
            "num_traders_proxy": int(_to_float(raw.get("volume_24h"), default=0.0)),
            "tte_seconds": tte_seconds,
            "platform": self.PLATFORM,
            "title": raw.get("title", ""),
            "subtitle": raw.get("subtitle", ""),
            "category": raw.get("category", ""),
            "status": raw.get("status", ""),
        }

    def normalize_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single Kalshi event record."""
        event_ticker = raw.get("event_ticker", "")
        event_id = f"kalshi:{event_ticker}" if event_ticker else ""

        return {
            "event_id": event_id,
            "title": raw.get("title", ""),
            "category": raw.get("category", ""),
            "status": raw.get("status", ""),
            "platform": self.PLATFORM,
            "mutually_exclusive": raw.get("mutually_exclusive", False),
            "series_ticker": raw.get("series_ticker", ""),
        }


def _to_float(value: Any, *, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


__all__ = ["KalshiNormalizer"]
