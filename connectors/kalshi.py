"""Async Kalshi API client with pagination, retries, and normalization."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


class KalshiConnectorError(Exception):
    """Base exception for Kalshi connector errors."""


class KalshiRequestError(KalshiConnectorError):
    """Raised when an HTTP request fails after retries."""


class KalshiHTTPError(KalshiConnectorError):
    """Raised when the server returns a non-retryable HTTP error."""

    def __init__(self, status_code: int, url: str, body: str | None = None) -> None:
        self.status_code = status_code
        self.url = url
        self.body = body
        preview = (body or "").strip().replace("\n", " ")
        if len(preview) > 200:
            preview = f"{preview[:197]}..."
        message = f"Kalshi API returned HTTP {status_code} for {url}"
        if preview:
            message = f"{message}: {preview}"
        super().__init__(message)


class KalshiResponseError(KalshiConnectorError):
    """Raised when the response cannot be parsed or paginated safely."""


class KalshiConnector:
    """Async Kalshi API client with pagination, retries, and normalization.

    Follows the same patterns as GammaConnector: exponential backoff with
    jitter, rate limiting, snake_case normalization, and cursor pagination.
    """

    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    _SNAKE_CASE_1 = re.compile(r"(.)([A-Z][a-z]+)")
    _SNAKE_CASE_2 = re.compile(r"([a-z0-9])([A-Z])")

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key_id: str | None = None,
        api_key_secret: str | None = None,
        timeout: float | httpx.Timeout = 10.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_factor: float = 2.0,
        backoff_max: float = 8.0,
        backoff_jitter: float = 0.0,
        max_requests_per_second: float | None = None,
        client: httpx.AsyncClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_base < 0:
            raise ValueError("backoff_base must be >= 0")
        if backoff_factor < 1:
            raise ValueError("backoff_factor must be >= 1")
        if backoff_max < 0:
            raise ValueError("backoff_max must be >= 0")
        if backoff_jitter < 0:
            raise ValueError("backoff_jitter must be >= 0")
        if max_requests_per_second is not None and max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be > 0 when provided")

        self._api_key_id = api_key_id
        self._api_key_secret = api_key_secret

        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key_id:
            headers["Authorization"] = f"Bearer {api_key_id}"

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_factor = backoff_factor
        self._backoff_max = backoff_max
        self._backoff_jitter = backoff_jitter
        self._logger = logger or logging.getLogger(__name__)

        self._min_request_interval = (
            1.0 / max_requests_per_second if max_requests_per_second else None
        )
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_started_at: float | None = None

    async def __aenter__(self) -> "KalshiConnector":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_markets(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._fetch_paginated(
            endpoint="/markets",
            record_type="market",
            items_key="markets",
            limit=limit,
            params=params,
        )

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._fetch_paginated(
            endpoint="/events",
            record_type="event",
            items_key="events",
            limit=limit,
            params=params,
        )

    async def _fetch_paginated(
        self,
        *,
        endpoint: str,
        record_type: str,
        items_key: str,
        limit: int,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be > 0")

        base_params: dict[str, Any] = dict(params or {})
        base_params.setdefault("limit", min(limit, 200))

        cursor: str | None = None
        seen_cursors: set[str] = set()
        records: list[dict[str, Any]] = []

        while True:
            page_params = dict(base_params)
            if cursor is not None:
                page_params["cursor"] = cursor

            payload = await self._request_json(endpoint=endpoint, params=page_params)

            if not isinstance(payload, dict):
                raise KalshiResponseError("Expected a JSON object response.")

            items = payload.get(items_key)
            if not isinstance(items, list):
                raise KalshiResponseError(
                    f"Could not find '{items_key}' list in {record_type} response."
                )

            if not items:
                break

            for item in items:
                if not isinstance(item, Mapping):
                    raise KalshiResponseError(
                        "Each record in response payload must be an object."
                    )
                records.append(self._normalize_record(item, record_type))

            if len(records) >= limit:
                records = records[:limit]
                break

            next_cursor = payload.get("cursor")
            if not next_cursor or next_cursor in seen_cursors:
                break

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return records

    async def _request_json(
        self, *, endpoint: str, params: Mapping[str, Any] | None = None
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            await self._wait_for_rate_limit()
            try:
                response = await self._client.get(
                    endpoint,
                    params=params,
                    timeout=self._timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = self._retry_delay(attempt)
                self._logger.warning(
                    "Kalshi request failed (%s). Retrying in %.2fs (attempt %s/%s).",
                    exc.__class__.__name__,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                if attempt >= self._max_retries:
                    raise KalshiHTTPError(
                        response.status_code,
                        str(response.request.url),
                        response.text,
                    )
                delay = self._retry_delay(attempt)
                self._logger.warning(
                    "Kalshi API returned retryable status %s. Retrying in %.2fs (attempt %s/%s).",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.is_error:
                raise KalshiHTTPError(
                    response.status_code,
                    str(response.request.url),
                    response.text,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise KalshiResponseError(
                    f"Kalshi API returned invalid JSON from {response.request.url}"
                ) from exc

        raise KalshiRequestError(
            f"Kalshi request failed after {self._max_retries + 1} attempts."
        ) from last_error

    async def _wait_for_rate_limit(self) -> None:
        if self._min_request_interval is None:
            return

        async with self._rate_limit_lock:
            now = time.monotonic()
            if self._last_request_started_at is None:
                self._last_request_started_at = now
                return

            elapsed = now - self._last_request_started_at
            wait_for = self._min_request_interval - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_started_at = time.monotonic()

    def _retry_delay(self, attempt: int) -> float:
        delay = min(
            self._backoff_max,
            self._backoff_base * (self._backoff_factor**attempt),
        )
        if self._backoff_jitter > 0:
            spread = delay * self._backoff_jitter
            delay += random.uniform(-spread, spread)
        return max(0.0, delay)

    def _normalize_record(
        self, record: Mapping[str, Any], record_type: str
    ) -> dict[str, Any]:
        normalized = self._normalize_value(record)
        if not isinstance(normalized, dict):
            raise KalshiResponseError("Normalized record must be a dict.")

        record_id = self._extract_record_id(normalized, record_type)
        normalized["record_type"] = record_type
        normalized["platform"] = "kalshi"
        if record_id is not None:
            normalized["record_id"] = record_id
            normalized[f"{record_type}_id"] = record_id
        return normalized

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                self._to_snake_case(str(key)): self._normalize_value(nested)
                for key, nested in value.items()
            }
        if isinstance(value, list):
            return [self._normalize_value(item) for item in value]
        return value

    def _extract_record_id(
        self, record: Mapping[str, Any], record_type: str
    ) -> str | None:
        candidate_keys = ["ticker", f"{record_type}_id", "id", "event_ticker"]
        for key in candidate_keys:
            value = record.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @classmethod
    def _to_snake_case(cls, value: str) -> str:
        step_1 = cls._SNAKE_CASE_1.sub(r"\1_\2", value)
        return cls._SNAKE_CASE_2.sub(r"\1_\2", step_1).replace("-", "_").lower()


__all__ = [
    "KalshiConnector",
    "KalshiConnectorError",
    "KalshiHTTPError",
    "KalshiRequestError",
    "KalshiResponseError",
]
