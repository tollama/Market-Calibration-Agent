"""Protocol definitions for prediction market connectors.

These protocols define the abstract capabilities that platform-specific
connectors must satisfy. Not all platforms support all capabilities --
the connector factory returns ``None`` for unsupported interfaces.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MarketDataConnector(Protocol):
    """Fetches market and event listing data (REST or similar)."""

    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class MetricsConnector(Protocol):
    """Fetches supplemental metrics (open interest, volume, activity)."""

    def fetch_open_interest(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> Any: ...

    def fetch_volume(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> Any: ...

    def fetch_activity(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> Any: ...


@runtime_checkable
class RealtimeConnector(Protocol):
    """Streams real-time market data via WebSocket or similar transport."""

    async def stream_messages(
        self,
        url: str,
        *,
        subscribe_message: Any = None,
        message_limit: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]: ...


__all__ = [
    "MarketDataConnector",
    "MetricsConnector",
    "RealtimeConnector",
]
