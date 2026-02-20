import asyncio

import httpx
import pytest

import connectors.polymarket_gamma as gamma_module
from connectors.polymarket_gamma import GammaConnector, GammaRequestError


def test_fetch_markets_cursor_pagination_and_normalization() -> None:
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
                            "id": 1,
                            "question": "Will it rain tomorrow?",
                            "outcomePrices": [0.35, 0.65],
                        }
                    ],
                    "next_cursor": "cursor-2",
                },
            )
        if cursor == "cursor-2":
            return httpx.Response(
                200,
                json={"data": [{"id": 2, "question": "Will it snow?"}]},
            )
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    async def run_test() -> list[dict[str, str]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            return await connector.fetch_markets(limit=1)

    records = asyncio.run(run_test())

    assert [record["market_id"] for record in records] == ["1", "2"]
    assert records[0]["record_type"] == "market"
    assert "outcome_prices" in records[0]
    assert calls[0]["limit"] == "1"
    assert calls[1]["cursor"] == "cursor-2"


def test_fetch_events_offset_pagination_for_list_payload() -> None:
    offsets: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        offsets.append(offset)
        pages = {
            0: [{"id": "event-1", "startDate": "2026-01-01T00:00:00Z"}],
            1: [{"id": "event-2", "startDate": "2026-01-02T00:00:00Z"}],
            2: [],
        }
        return httpx.Response(200, json=pages[offset])

    transport = httpx.MockTransport(handler)
    async def run_test() -> list[dict[str, str]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            return await connector.fetch_events(limit=1, params={"offset": 0})

    records = asyncio.run(run_test())

    assert [record["event_id"] for record in records] == ["event-1", "event-2"]
    assert records[0]["start_date"] == "2026-01-01T00:00:00Z"
    assert offsets == [0, 1, 2]


def test_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(gamma_module.asyncio, "sleep", fake_sleep)

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"data": [{"id": "mkt-1"}]})

    transport = httpx.MockTransport(handler)
    async def run_test() -> list[dict[str, str]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(
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
    assert records[0]["market_id"] == "mkt-1"


def test_timeout_raises_gamma_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    async def run_test() -> None:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(client=client, max_retries=0)
            await connector.fetch_markets()

    with pytest.raises(GammaRequestError):
        asyncio.run(run_test())

def test_optional_rate_limit_waits_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return fake_clock["t"]

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        fake_clock["t"] += delay

    monkeypatch.setattr(gamma_module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(gamma_module.asyncio, "sleep", fake_sleep)

    async def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        if offset == 0:
            return httpx.Response(200, json=[{"id": "event-1"}])
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async def run_test() -> list[dict[str, str]]:
        async with httpx.AsyncClient(base_url="https://gamma.example", transport=transport) as client:
            connector = GammaConnector(
                client=client,
                max_retries=0,
                max_requests_per_second=2.0,
            )
            return await connector.fetch_events(limit=1, params={"offset": 0})

    records = asyncio.run(run_test())

    assert [record["event_id"] for record in records] == ["event-1"]
    assert sleeps == [0.5]
