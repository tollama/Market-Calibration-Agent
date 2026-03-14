import asyncio

import httpx
import pytest

import connectors.manifold as manifold_module
from connectors.manifold import ManifoldConnector, ManifoldRequestError


def test_fetch_markets_before_pagination_and_normalization() -> None:
    calls: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        before = request.url.params.get("before")
        if before is None:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "abc123",
                        "question": "Will it rain tomorrow?",
                        "probability": 0.65,
                        "volume24Hours": 1234.5,
                        "totalLiquidity": 5000.0,
                        "uniqueBettorCount": 42,
                        "outcomeType": "BINARY",
                        "slug": "will-it-rain-tomorrow",
                    }
                ],
            )
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=500)

    records = asyncio.run(run_test())

    assert len(records) == 1
    assert records[0]["id"] == "abc123"
    assert records[0]["record_type"] == "market"
    assert records[0]["platform"] == "manifold"


def test_fetch_events_returns_empty_list() -> None:
    """Manifold has no separate events concept."""

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example") as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            return await connector.fetch_events(limit=100)

    records = asyncio.run(run_test())
    assert records == []


def test_pagination_stops_on_partial_page() -> None:
    """Pagination stops when API returns fewer items than page_size."""
    calls: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        # Return only 2 items; with limit=500 => page_size=500
        # Since 2 < 500, pagination stops after one call.
        return httpx.Response(
            200,
            json=[
                {"id": "item-1", "outcomeType": "BINARY"},
                {"id": "item-2", "outcomeType": "BINARY"},
            ],
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=500)

    records = asyncio.run(run_test())

    assert len(records) == 2
    assert len(calls) == 1  # No second page call


def test_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(manifold_module.asyncio, "sleep", fake_sleep)

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=[{"id": "mkt-1", "outcomeType": "BINARY"}])

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(
                client=client,
                max_retries=2,
                backoff_base=0.1,
                backoff_factor=2.0,
                backoff_jitter=0.0,
            )
            return await connector.fetch_markets(limit=100)

    records = asyncio.run(run_test())

    assert attempts == 3
    assert sleeps == [0.1, 0.2]
    assert len(records) == 1


def test_timeout_raises_manifold_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)

    async def run_test() -> None:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            await connector.fetch_markets()

    with pytest.raises(ManifoldRequestError):
        asyncio.run(run_test())


def test_snake_case_normalization() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "test-1",
                    "outcomeType": "BINARY",
                    "uniqueBettorCount": 10,
                    "totalLiquidity": 500.0,
                    "volume24Hours": 200.0,
                    "closeTime": 1735689600000,
                }
            ],
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=10)

    records = asyncio.run(run_test())

    assert "outcome_type" in records[0]
    assert "unique_bettor_count" in records[0]
    assert "total_liquidity" in records[0]


def test_deduplication_within_single_page() -> None:
    """Ensure duplicate IDs within a page are deduplicated."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"id": "dup-1", "outcomeType": "BINARY"},
                {"id": "dup-1", "outcomeType": "BINARY"},
                {"id": "dup-2", "outcomeType": "BINARY"},
            ],
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://manifold.example", transport=transport) as client:
            connector = ManifoldConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=500)

    records = asyncio.run(run_test())
    ids = [r["id"] for r in records]
    assert ids == ["dup-1", "dup-2"]
