import asyncio

import httpx
import pytest

import connectors.kalshi as kalshi_module
from connectors.kalshi import KalshiConnector, KalshiRequestError


def test_fetch_markets_cursor_pagination_and_normalization() -> None:
    calls: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "PRES-2028-D",
                            "title": "Democratic nominee wins?",
                            "yes_bid": 45,
                            "yes_ask": 47,
                            "volume": 12345,
                            "open_interest": 5000,
                            "event_ticker": "PRES-2028",
                        }
                    ],
                    "cursor": "cursor-page-2",
                },
            )
        if cursor == "cursor-page-2":
            return httpx.Response(
                200,
                json={
                    "markets": [
                        {
                            "ticker": "PRES-2028-R",
                            "title": "Republican nominee wins?",
                            "yes_bid": 53,
                            "yes_ask": 55,
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"markets": []})

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=500)

    records = asyncio.run(run_test())

    assert len(records) == 2
    assert records[0]["market_id"] == "PRES-2028-D"
    assert records[0]["record_type"] == "market"
    assert records[0]["platform"] == "kalshi"
    assert records[1]["market_id"] == "PRES-2028-R"
    assert "cursor-page-2" in str(calls[1].get("cursor", ""))


def test_fetch_events_returns_normalized_events() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "event_ticker": "PRES-2028",
                        "title": "2028 Presidential Election",
                        "category": "Politics",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(client=client, max_retries=0)
            return await connector.fetch_events(limit=100)

    records = asyncio.run(run_test())

    assert len(records) == 1
    assert records[0]["event_id"] == "PRES-2028"
    assert records[0]["record_type"] == "event"
    assert records[0]["platform"] == "kalshi"


def test_fetch_historical_markets_uses_historical_endpoint() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "HIST-1",
                        "title": "Historical market",
                        "event_ticker": "HIST-EVENT",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(client=client, max_retries=0)
            return await connector.fetch_historical_markets(limit=10, params={"mve_filter": "exclude"})

    records = asyncio.run(run_test())

    assert calls == ["/historical/markets"]
    assert records[0]["market_id"] == "HIST-1"
    assert records[0]["platform"] == "kalshi"


def test_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(kalshi_module.asyncio, "sleep", fake_sleep)

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"markets": [{"ticker": "MKT-1"}]})

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(
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
    assert records[0]["market_id"] == "MKT-1"


def test_timeout_raises_kalshi_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)

    async def run_test() -> None:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(client=client, max_retries=0)
            await connector.fetch_markets()

    with pytest.raises(KalshiRequestError):
        asyncio.run(run_test())


def test_snake_case_normalization() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "TEST-1",
                        "yesSubTitle": "Yes outcome",
                        "noSubTitle": "No outcome",
                        "openInterest": 999,
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_test() -> list[dict]:
        async with httpx.AsyncClient(base_url="https://kalshi.example", transport=transport) as client:
            connector = KalshiConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=10)

    records = asyncio.run(run_test())

    assert "yes_sub_title" in records[0]
    assert "no_sub_title" in records[0]
    assert "open_interest" in records[0]
