"""Normalizer that maps Manifold Markets API responses to MarketSnapshot-compatible dicts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ManifoldNormalizer:
    """Converts raw Manifold market records into a canonical dict format
    compatible with ``MarketSnapshot`` and ``MarketRegistry``.

    For multi-outcome markets, each outcome is flattened into a separate
    record to preserve the ``p_yes + p_no = 1.0`` invariant.
    """

    PLATFORM = "manifold"

    def normalize_market(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single Manifold market record (binary).

        For multi-outcome markets, use ``normalize_market_outcomes`` instead.
        """
        market_id_raw = raw.get("id", "")
        market_id = f"manifold:{market_id_raw}" if market_id_raw else ""
        group_id = raw.get("group_slugs", [""])[0] if raw.get("group_slugs") else ""
        event_id = f"manifold:{group_id}" if group_id else market_id

        p_yes = _to_float(raw.get("probability"), default=0.5)
        p_yes = max(0.0, min(1.0, p_yes))
        p_no = 1.0 - p_yes

        volume_24h = _to_float(raw.get("volume24_hours") or raw.get("volume_24_hours"), default=0.0)
        liquidity = _to_float(raw.get("total_liquidity") or raw.get("totalLiquidity"), default=0.0)
        unique_bettors = int(_to_float(raw.get("unique_bettor_count") or raw.get("uniqueBettorCount"), default=0.0))

        close_time_ms = raw.get("close_time") or raw.get("closeTime")
        tte_seconds = 0
        if close_time_ms is not None:
            try:
                close_ts = float(close_time_ms) / 1000.0
                close_dt = datetime.fromtimestamp(close_ts, tz=timezone.utc)
                tte_seconds = max(0, int((close_dt - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OSError):
                tte_seconds = 0

        return {
            "market_id": market_id,
            "event_id": event_id,
            "p_yes": round(p_yes, 6),
            "p_no": round(p_no, 6),
            "volume_24h": volume_24h,
            "open_interest": liquidity,
            "num_traders_proxy": unique_bettors,
            "tte_seconds": tte_seconds,
            "platform": self.PLATFORM,
            "title": raw.get("question", "") or raw.get("title", ""),
            "slug": raw.get("slug", ""),
            "outcome_type": raw.get("outcome_type") or raw.get("outcomeType", "BINARY"),
        }

    def normalize_market_outcomes(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize a multi-outcome market into per-outcome records.

        For binary markets, returns a single-item list.
        For multiple-choice markets, each outcome becomes a separate record
        with ``market_id = manifold:{id}:{index}``.
        """
        outcome_type = raw.get("outcome_type") or raw.get("outcomeType", "BINARY")

        if outcome_type in ("BINARY", "PSEUDO_NUMERIC", "STONK"):
            return [self.normalize_market(raw)]

        answers = raw.get("answers", [])
        if not answers:
            return [self.normalize_market(raw)]

        market_id_raw = raw.get("id", "")
        group_id = raw.get("group_slugs", [""])[0] if raw.get("group_slugs") else ""
        event_id = f"manifold:{market_id_raw}"

        volume_24h = _to_float(raw.get("volume24_hours") or raw.get("volume_24_hours"), default=0.0)
        liquidity = _to_float(raw.get("total_liquidity") or raw.get("totalLiquidity"), default=0.0)
        unique_bettors = int(_to_float(raw.get("unique_bettor_count") or raw.get("uniqueBettorCount"), default=0.0))

        close_time_ms = raw.get("close_time") or raw.get("closeTime")
        tte_seconds = 0
        if close_time_ms is not None:
            try:
                close_ts = float(close_time_ms) / 1000.0
                close_dt = datetime.fromtimestamp(close_ts, tz=timezone.utc)
                tte_seconds = max(0, int((close_dt - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OSError):
                tte_seconds = 0

        records = []
        for idx, answer in enumerate(answers):
            answer_id = answer.get("id", str(idx))
            p_yes = _to_float(answer.get("probability") or answer.get("prob"), default=0.0)
            p_yes = max(0.0, min(1.0, p_yes))

            records.append({
                "market_id": f"manifold:{market_id_raw}:{answer_id}",
                "event_id": event_id,
                "p_yes": round(p_yes, 6),
                "p_no": round(1.0 - p_yes, 6),
                "volume_24h": volume_24h / max(len(answers), 1),
                "open_interest": liquidity / max(len(answers), 1),
                "num_traders_proxy": unique_bettors,
                "tte_seconds": tte_seconds,
                "platform": self.PLATFORM,
                "title": answer.get("text", ""),
                "slug": raw.get("slug", ""),
                "outcome_type": outcome_type,
                "parent_market_id": f"manifold:{market_id_raw}",
            })

        return records

    def normalize_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Manifold has no separate events. Pass-through for protocol compliance."""
        return {
            "event_id": raw.get("id", ""),
            "platform": self.PLATFORM,
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


__all__ = ["ManifoldNormalizer"]
