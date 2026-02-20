"""Polymarket subgraph GraphQL connector with retry/backoff and normalized outputs."""

from __future__ import annotations

import json
import random
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib import error, request


JSONMapping = Mapping[str, Any]
NormalizedRow = dict[str, Any]


class SubgraphConnectorError(RuntimeError):
    """Base error for connector-level failures."""


class GraphQLTransportError(SubgraphConnectorError):
    """Raised for transport-level failures (HTTP/network/JSON)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GraphQLQueryError(SubgraphConnectorError):
    """Raised when the GraphQL response has semantic query errors."""

    def __init__(self, message: str, *, errors: Sequence[JSONMapping] | None = None) -> None:
        super().__init__(message)
        self.errors = list(errors or [])


@dataclass(frozen=True)
class RetryConfig:
    """Retry/backoff configuration for GraphQL transport calls."""

    max_attempts: int = 3
    backoff_initial_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    backoff_max_seconds: float = 8.0
    jitter_ratio: float = 0.1
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_initial_seconds < 0:
            raise ValueError("backoff_initial_seconds must be >= 0")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be >= 1")
        if self.backoff_max_seconds < 0:
            raise ValueError("backoff_max_seconds must be >= 0")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


class GraphQLClient:
    """Minimal GraphQL client with retry/backoff for Polymarket subgraph access."""

    def __init__(
        self,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 10.0,
        retry_config: RetryConfig | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_func: Callable[[], float] = random.random,
        urlopen: Callable[..., Any] = request.urlopen,
    ) -> None:
        self.endpoint = endpoint
        self.headers = dict(headers or {})
        self.timeout_seconds = timeout_seconds
        self.retry_config = retry_config or RetryConfig()
        self._sleep = sleeper
        self._random = random_func
        self._urlopen = urlopen

    def execute(
        self,
        query: str,
        *,
        variables: Mapping[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query and return its ``data`` payload."""
        payload: dict[str, Any] = {
            "query": query,
            "variables": dict(variables or {}),
        }
        if operation_name:
            payload["operationName"] = operation_name

        for attempt in range(1, self.retry_config.max_attempts + 1):
            try:
                response_payload = self._post_json(payload)
                graphql_errors = response_payload.get("errors")
                if graphql_errors:
                    raise GraphQLQueryError(
                        self._format_graphql_errors(graphql_errors),
                        errors=graphql_errors if isinstance(graphql_errors, list) else None,
                    )

                data_payload = response_payload.get("data")
                if not isinstance(data_payload, dict):
                    raise GraphQLQueryError("GraphQL response did not include a valid 'data' object.")
                return data_payload
            except GraphQLTransportError as exc:
                if attempt >= self.retry_config.max_attempts or not exc.retryable:
                    raise
                self._sleep(self._compute_backoff(attempt))

        raise GraphQLTransportError("GraphQL request failed after retries.", retryable=False)

    def _post_json(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.headers,
        }
        req = request.Request(self.endpoint, data=body, headers=headers, method="POST")

        try:
            with self._urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            retryable = exc.code in self.retry_config.retryable_status_codes
            reason = detail or str(exc.reason)
            raise GraphQLTransportError(
                f"HTTP {exc.code} while querying subgraph: {reason}",
                status_code=exc.code,
                retryable=retryable,
            ) from exc
        except (error.URLError, socket.timeout, TimeoutError) as exc:
            raise GraphQLTransportError(
                f"Network error while querying subgraph: {exc}",
                retryable=True,
            ) from exc

        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise GraphQLTransportError(
                "Subgraph response was not valid JSON.",
                retryable=False,
            ) from exc

        if not isinstance(parsed, dict):
            raise GraphQLTransportError(
                "Subgraph response JSON root must be an object.",
                retryable=False,
            )
        return parsed

    def _compute_backoff(self, attempt: int) -> float:
        delay = min(
            self.retry_config.backoff_initial_seconds
            * (self.retry_config.backoff_multiplier ** (attempt - 1)),
            self.retry_config.backoff_max_seconds,
        )
        if self.retry_config.jitter_ratio == 0:
            return delay
        jitter_window = delay * self.retry_config.jitter_ratio
        jitter = (self._random() * 2.0 - 1.0) * jitter_window
        return max(0.0, delay + jitter)

    @staticmethod
    def _format_graphql_errors(errors_payload: Any) -> str:
        if not isinstance(errors_payload, list):
            return "GraphQL query failed with an unknown error payload."

        messages: list[str] = []
        for item in errors_payload:
            if isinstance(item, Mapping):
                message = item.get("message")
                if message:
                    messages.append(str(message))
        if not messages:
            return "GraphQL query failed."
        return "; ".join(messages)


class QueryTemplates:
    """Query templates for Polymarket subgraph aggregation endpoints."""

    OPEN_INTEREST = """
    query OpenInterest($marketIds: [String!], $first: Int!, $skip: Int!) {
      openInterestSnapshots(
        where: { marketId_in: $marketIds }
        first: $first
        skip: $skip
        orderBy: timestamp
        orderDirection: desc
      ) {
        marketId
        eventId
        openInterest
        timestamp
      }
    }
    """.strip()

    ACTIVITY = """
    query Activity($marketIds: [String!], $first: Int!, $skip: Int!) {
      activitySnapshots(
        where: { marketId_in: $marketIds }
        first: $first
        skip: $skip
        orderBy: timestamp
        orderDirection: desc
      ) {
        marketId
        eventId
        activity
        activeUsers
        tradeCount
        timestamp
      }
    }
    """.strip()

    VOLUME = """
    query Volume($marketIds: [String!], $first: Int!, $skip: Int!) {
      volumeSnapshots(
        where: { marketId_in: $marketIds }
        first: $first
        skip: $skip
        orderBy: timestamp
        orderDirection: desc
      ) {
        marketId
        eventId
        volume
        volumeUsd
        timestamp
      }
    }
    """.strip()


NORMALIZED_OUTPUT_FIELDS = (
    "market_id",
    "event_id",
    "metric",
    "value",
    "timestamp",
    "source",
)


@dataclass
class QueryRunResult:
    """Normalized rows plus per-market failures from a query execution."""

    rows: list[NormalizedRow] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_columnar_dict(self) -> dict[str, list[Any]]:
        """Convert normalized rows to ``dict(list)`` form."""
        return {
            field: [row.get(field) for row in self.rows]
            for field in NORMALIZED_OUTPUT_FIELDS
        }


class SubgraphQueryRunner:
    """Runs subgraph queries and returns normalized, schema-stable records."""

    def __init__(self, client: GraphQLClient) -> None:
        self.client = client

    def fetch_open_interest(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> QueryRunResult:
        return self._run_metric_query(
            market_ids=market_ids,
            metric="open_interest",
            query=QueryTemplates.OPEN_INTEREST,
            root_field="openInterestSnapshots",
            value_keys=("openInterest", "open_interest", "value"),
            page_size=page_size,
        )

    def fetch_activity(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> QueryRunResult:
        return self._run_metric_query(
            market_ids=market_ids,
            metric="activity",
            query=QueryTemplates.ACTIVITY,
            root_field="activitySnapshots",
            value_keys=("activity", "activeUsers", "tradeCount", "value"),
            page_size=page_size,
        )

    def fetch_volume(
        self,
        market_ids: Sequence[str],
        *,
        page_size: int = 200,
    ) -> QueryRunResult:
        return self._run_metric_query(
            market_ids=market_ids,
            metric="volume",
            query=QueryTemplates.VOLUME,
            root_field="volumeSnapshots",
            value_keys=("volume", "volumeUsd", "volumeUSDC", "value"),
            page_size=page_size,
        )

    def _run_metric_query(
        self,
        *,
        market_ids: Sequence[str],
        metric: str,
        query: str,
        root_field: str,
        value_keys: Sequence[str],
        page_size: int,
    ) -> QueryRunResult:
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        result = QueryRunResult()

        for market_id in market_ids:
            canonical_market_id = str(market_id)
            skip = 0

            while True:
                try:
                    data = self.client.execute(
                        query,
                        variables={
                            "marketIds": [canonical_market_id],
                            "first": page_size,
                            "skip": skip,
                        },
                    )
                except SubgraphConnectorError as exc:
                    result.failures.append(
                        {
                            "market_id": canonical_market_id,
                            "metric": metric,
                            "error": str(exc),
                        }
                    )
                    break

                records = data.get(root_field)
                if not isinstance(records, list):
                    result.failures.append(
                        {
                            "market_id": canonical_market_id,
                            "metric": metric,
                            "error": f"Missing list payload for '{root_field}'.",
                        }
                    )
                    break

                result.rows.extend(
                    _normalize_records(
                        records,
                        metric=metric,
                        value_keys=value_keys,
                        fallback_market_id=canonical_market_id,
                    )
                )

                if len(records) < page_size:
                    break
                skip += page_size

        return result


def fetch_open_interest(
    client: GraphQLClient,
    market_ids: Sequence[str],
    *,
    page_size: int = 200,
) -> QueryRunResult:
    """Fetch and normalize open interest metrics for markets."""
    return SubgraphQueryRunner(client).fetch_open_interest(market_ids, page_size=page_size)


def fetch_activity(
    client: GraphQLClient,
    market_ids: Sequence[str],
    *,
    page_size: int = 200,
) -> QueryRunResult:
    """Fetch and normalize activity metrics for markets."""
    return SubgraphQueryRunner(client).fetch_activity(market_ids, page_size=page_size)


def fetch_volume(
    client: GraphQLClient,
    market_ids: Sequence[str],
    *,
    page_size: int = 200,
) -> QueryRunResult:
    """Fetch and normalize volume metrics for markets."""
    return SubgraphQueryRunner(client).fetch_volume(market_ids, page_size=page_size)


def _normalize_records(
    records: Sequence[JSONMapping],
    *,
    metric: str,
    value_keys: Sequence[str],
    fallback_market_id: str,
) -> list[NormalizedRow]:
    normalized: list[NormalizedRow] = []

    for record in records:
        if not isinstance(record, Mapping):
            continue

        market_id = _extract_identifier(record, keys=("marketId", "market_id"), nested_key="market")
        event_id = _extract_identifier(record, keys=("eventId", "event_id"), nested_key="event")

        normalized.append(
            {
                "market_id": market_id or fallback_market_id,
                "event_id": event_id,
                "metric": metric,
                "value": _extract_numeric_value(record, value_keys),
                "timestamp": _normalize_timestamp(
                    _extract_first(record, ("timestamp", "ts", "createdAt", "updatedAt"))
                ),
                "source": "subgraph",
            }
        )

    return normalized


def _extract_first(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record:
            return record.get(key)
    return None


def _extract_identifier(
    record: Mapping[str, Any],
    *,
    keys: Sequence[str],
    nested_key: str,
) -> str | None:
    value = _extract_first(record, keys)
    if value not in (None, ""):
        return str(value)

    nested = record.get(nested_key)
    if isinstance(nested, Mapping):
        nested_id = nested.get("id")
        if nested_id not in (None, ""):
            return str(nested_id)
    return None


def _extract_numeric_value(record: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    raw_value = _extract_first(record, keys)
    if raw_value is None or isinstance(raw_value, bool):
        return None

    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    if isinstance(raw_value, str):
        try:
            return float(raw_value.strip())
        except ValueError:
            return None

    return None


def _normalize_timestamp(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and (candidate.isdigit() or (candidate.startswith("-") and candidate[1:].isdigit())):
            return int(candidate)
        return candidate or None
    return None


__all__ = [
    "GraphQLClient",
    "GraphQLQueryError",
    "GraphQLTransportError",
    "QueryRunResult",
    "QueryTemplates",
    "RetryConfig",
    "SubgraphConnectorError",
    "SubgraphQueryRunner",
    "fetch_activity",
    "fetch_open_interest",
    "fetch_volume",
]
