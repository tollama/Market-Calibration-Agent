"""Factory functions for creating platform-specific connectors."""

from __future__ import annotations

from typing import Any

from schemas.enums import Platform

from .base import MarketDataConnector, MetricsConnector, RealtimeConnector


def create_connector(
    platform: Platform,
    *,
    config: dict[str, Any] | None = None,
) -> MarketDataConnector:
    """Instantiate the correct market data connector for a platform."""
    cfg = config or {}

    if platform == Platform.POLYMARKET:
        from .polymarket_gamma import GammaConnector

        return GammaConnector(
            base_url=cfg.get("base_url", "https://gamma-api.polymarket.com"),
            max_retries=cfg.get("max_retries", 3),
            backoff_base=cfg.get("backoff_base", 0.5),
        )

    if platform == Platform.KALSHI:
        from .kalshi import KalshiConnector

        return KalshiConnector(
            base_url=cfg.get("base_url", "https://api.elections.kalshi.com/trade-api/v2"),
            api_key_id=cfg.get("api_key_id"),
            api_key_secret=cfg.get("api_key_secret"),
            max_retries=cfg.get("max_retries", 3),
        )

    if platform == Platform.MANIFOLD:
        from .manifold import ManifoldConnector

        return ManifoldConnector(
            base_url=cfg.get("base_url", "https://api.manifold.markets/v0"),
            max_retries=cfg.get("max_retries", 3),
        )

    raise ValueError(f"Unsupported platform: {platform}")


def create_metrics_connector(
    platform: Platform,
    *,
    config: dict[str, Any] | None = None,
) -> MetricsConnector | None:
    """Return a metrics connector if the platform supports it, else None."""
    if platform == Platform.POLYMARKET:
        from .polymarket_subgraph import GraphQLClient, SubgraphQueryRunner

        cfg = config or {}
        endpoint = cfg.get("subgraph_endpoint")
        if not endpoint:
            return None
        client = GraphQLClient(endpoint)
        return SubgraphQueryRunner(client)  # type: ignore[return-value]

    return None


def create_realtime_connector(
    platform: Platform,
    *,
    config: dict[str, Any] | None = None,
) -> RealtimeConnector | None:
    """Return a realtime connector if the platform supports it, else None."""
    if platform == Platform.POLYMARKET:
        from .polymarket_ws import PolymarketWSConnector

        cfg = config or {}
        return PolymarketWSConnector(
            ping_interval=cfg.get("ping_interval", 20.0),
            reconnect_base=cfg.get("reconnect_base", 0.5),
            reconnect_max=cfg.get("reconnect_max", 8.0),
            max_retries=cfg.get("max_retries", 5),
        )

    return None


__all__ = [
    "create_connector",
    "create_metrics_connector",
    "create_realtime_connector",
]
