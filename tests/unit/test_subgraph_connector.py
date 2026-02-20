from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from connectors.polymarket_subgraph import (
    GraphQLClient,
    GraphQLQueryError,
    GraphQLTransportError,
    RetryConfig,
    SubgraphQueryRunner,
    fetch_volume,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_graphql_client_retries_with_exponential_backoff_until_success() -> None:
    attempts = {"count": 0}

    def fake_urlopen(_request, timeout):  # noqa: ANN001
        assert timeout == 5
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise URLError("temporary network issue")
        return _FakeHTTPResponse({"data": {"volumeSnapshots": []}})

    sleep_calls: list[float] = []

    client = GraphQLClient(
        "https://example.invalid/subgraph",
        timeout_seconds=5,
        retry_config=RetryConfig(
            max_attempts=4,
            backoff_initial_seconds=0.2,
            backoff_multiplier=2.0,
            backoff_max_seconds=5,
            jitter_ratio=0,
        ),
        sleeper=sleep_calls.append,
        urlopen=fake_urlopen,
    )

    data = client.execute("query { volumeSnapshots { marketId } }")

    assert data == {"volumeSnapshots": []}
    assert attempts["count"] == 3
    assert sleep_calls == [0.2, 0.4]


def test_graphql_client_raises_after_retry_budget_exhausted() -> None:
    def always_fails(_request, timeout):  # noqa: ANN001
        raise URLError(f"still down (timeout={timeout})")

    sleep_calls: list[float] = []

    client = GraphQLClient(
        "https://example.invalid/subgraph",
        retry_config=RetryConfig(max_attempts=2, backoff_initial_seconds=0.1, jitter_ratio=0),
        sleeper=sleep_calls.append,
        urlopen=always_fails,
    )

    with pytest.raises(GraphQLTransportError):
        client.execute("query { openInterestSnapshots { marketId } }")

    assert sleep_calls == [0.1]


def test_query_runner_normalizes_open_interest_and_reports_partial_failures() -> None:
    class StubClient:
        def execute(self, query, *, variables=None, operation_name=None):  # noqa: ANN001
            assert operation_name is None
            assert "openInterestSnapshots" in query
            market_id = variables["marketIds"][0]
            skip = variables["skip"]

            if market_id == "bad-market":
                raise GraphQLQueryError("subgraph semantic failure")

            if skip == 0:
                return {
                    "openInterestSnapshots": [
                        {
                            "market": {"id": "good-market"},
                            "event": {"id": "event-123"},
                            "openInterest": "42.50",
                            "timestamp": "1700000000",
                        }
                    ]
                }
            return {"openInterestSnapshots": []}

    runner = SubgraphQueryRunner(StubClient())
    result = runner.fetch_open_interest(["good-market", "bad-market"], page_size=1)

    assert result.rows == [
        {
            "market_id": "good-market",
            "event_id": "event-123",
            "metric": "open_interest",
            "value": 42.5,
            "timestamp": 1700000000,
            "source": "subgraph",
        }
    ]
    assert result.failures == [
        {
            "market_id": "bad-market",
            "metric": "open_interest",
            "error": "subgraph semantic failure",
        }
    ]

    assert result.as_columnar_dict()["metric"] == ["open_interest"]


def test_fetch_volume_normalizes_records_with_fallback_ids() -> None:
    class StubClient:
        def execute(self, query, *, variables=None, operation_name=None):  # noqa: ANN001
            assert operation_name is None
            assert "volumeSnapshots" in query
            market_id = variables["marketIds"][0]
            if market_id == "mkt-1":
                return {
                    "volumeSnapshots": [
                        {
                            "eventId": "evt-1",
                            "volumeUsd": "100.25",
                            "timestamp": 1700000100,
                        }
                    ]
                }
            return {
                "volumeSnapshots": [
                    {
                        "marketId": "mkt-2",
                        "eventId": "evt-2",
                        "volume": 7,
                        "ts": "1700000200",
                    }
                ]
            }

    result = fetch_volume(StubClient(), ["mkt-1", "mkt-2"])

    assert result.rows == [
        {
            "market_id": "mkt-1",
            "event_id": "evt-1",
            "metric": "volume",
            "value": 100.25,
            "timestamp": 1700000100,
            "source": "subgraph",
        },
        {
            "market_id": "mkt-2",
            "event_id": "evt-2",
            "metric": "volume",
            "value": 7.0,
            "timestamp": 1700000200,
            "source": "subgraph",
        },
    ]
    assert result.failures == []
