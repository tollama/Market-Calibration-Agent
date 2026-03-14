"""Protocol and helpers for platform-specific market data normalization."""

from __future__ import annotations

from typing import Any, Protocol


class MarketNormalizer(Protocol):
    """Converts platform-specific raw API responses into MarketSnapshot-compatible dicts."""

    def normalize_market(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw market record."""
        ...

    def normalize_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw event record."""
        ...


__all__ = [
    "MarketNormalizer",
]
