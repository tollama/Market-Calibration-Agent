from __future__ import annotations

import asyncio

import httpx
import pytest

from connectors.polymarket_gamma import (
    GammaConnector,
    GammaRequestError,
    GammaResponseError,
)


def test_fetch_markets_raw_preserves_original_shape_and_cursor_pagination() -> None:
    calls: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "m-1",
                            "outcomePrices": [0.4, 0.6],
                            "metaData": {"startDate": "2026-01-01T00:00:00Z"},
                        }
                    ],
                    "next_cursor": "cursor-2",
                },
            )
        if cursor == "cursor-2":
            return httpx.Response(
                200,
                json={"data": [{"id": "m-2", "outcomePrices": [0.2, 0.8]}]},
            )
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict[str, object]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            return await connector.fetch_markets_raw(limit=1, params={"status": "open"})

    records = asyncio.run(run_test())

    assert [record["id"] for record in records] == ["m-1", "m-2"]
    assert "outcomePrices" in records[0]
    assert "outcome_prices" not in records[0]
    assert "metaData" in records[0]
    assert "record_id" not in records[0]
    assert "record_type" not in records[0]
    assert calls[0]["limit"] == "1"
    assert calls[0]["status"] == "open"
    assert calls[1]["cursor"] == "cursor-2"


def test_fetch_markets_keeps_existing_normalized_contract() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "m-1",
                        "outcomePrices": [0.4, 0.6],
                        "metaData": {"startDate": "2026-01-01T00:00:00Z"},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict[str, object]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=10)

    records = asyncio.run(run_test())

    assert len(records) == 1
    assert records[0]["record_type"] == "market"
    assert records[0]["record_id"] == "m-1"
    assert records[0]["market_id"] == "m-1"
    assert "outcome_prices" in records[0]
    assert "outcomePrices" not in records[0]
    assert "meta_data" in records[0]


def test_fetch_events_raw_raises_response_error_for_non_object_items() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [1, 2, 3]})

    transport = httpx.MockTransport(handler)

    async def run_test() -> None:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            await connector.fetch_events_raw(limit=100)

    with pytest.raises(GammaResponseError):
        asyncio.run(run_test())


def test_fetch_events_raw_timeout_raises_gamma_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)

    async def run_test() -> None:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            await connector.fetch_events_raw(limit=100)

    with pytest.raises(GammaRequestError):
        asyncio.run(run_test())
