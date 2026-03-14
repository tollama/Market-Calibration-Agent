"""Async Manifold Markets API client with pagination, retries, and normalization."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.manifold.markets/v0"


class ManifoldConnectorError(Exception):
    """Base exception for Manifold connector errors."""


class ManifoldRequestError(ManifoldConnectorError):
    """Raised when an HTTP request fails after retries."""


class ManifoldHTTPError(ManifoldConnectorError):
    """Raised when the server returns a non-retryable HTTP error."""

    def __init__(self, status_code: int, url: str, body: str | None = None) -> None:
        self.status_code = status_code
        self.url = url
        self.body = body
        preview = (body or "").strip().replace("\n", " ")
        if len(preview) > 200:
            preview = f"{preview[:197]}..."
        message = f"Manifold API returned HTTP {status_code} for {url}"
        if preview:
            message = f"{message}: {preview}"
        super().__init__(message)


class ManifoldResponseError(ManifoldConnectorError):
    """Raised when the response cannot be parsed or paginated safely."""


class ManifoldConnector:
    """Async Manifold Markets API client with pagination, retries, and normalization.

    Manifold's API is open (no authentication required). Markets are fetched
    via ``/markets`` with ``limit`` + ``before`` cursor-based pagination.
    Manifold has no separate events concept, so ``fetch_events`` returns ``[]``.
    """

    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    _SNAKE_CASE_1 = re.compile(r"(.)([A-Z][a-z]+)")
    _SNAKE_CASE_2 = re.compile(r"([a-z0-9])([A-Z])")

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
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

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
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

    async def __aenter__(self) -> "ManifoldConnector":
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
        """Fetch markets via /markets with before-cursor pagination."""
        if limit <= 0:
            raise ValueError("limit must be > 0")

        base_params: dict[str, Any] = dict(params or {})
        page_size = min(limit, 1000)

        before: str | None = None
        seen_ids: set[str] = set()
        records: list[dict[str, Any]] = []

        while True:
            page_params: dict[str, Any] = {**base_params, "limit": page_size}
            if before is not None:
                page_params["before"] = before

            payload = await self._request_json(endpoint="/markets", params=page_params)

            if not isinstance(payload, list):
                raise ManifoldResponseError("Expected a JSON array response from /markets.")

            if not payload:
                break

            for item in payload:
                if not isinstance(item, Mapping):
                    raise ManifoldResponseError(
                        "Each record in response payload must be an object."
                    )
                normalized = self._normalize_record(item, "market")
                item_id = normalized.get("id", "")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                records.append(normalized)

            if len(records) >= limit:
                records = records[:limit]
                break

            last_item = payload[-1]
            last_id = last_item.get("id", "")
            if not last_id or last_id == before:
                break
            before = last_id

            if len(payload) < page_size:
                break

        return records

    async def fetch_events(
        self,
        *,
        limit: int = 500,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Manifold has no separate events concept. Returns empty list."""
        return []

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
                    "Manifold request failed (%s). Retrying in %.2fs (attempt %s/%s).",
                    exc.__class__.__name__,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                if attempt >= self._max_retries:
                    raise ManifoldHTTPError(
                        response.status_code,
                        str(response.request.url),
                        response.text,
                    )
                delay = self._retry_delay(attempt)
                self._logger.warning(
                    "Manifold API returned retryable status %s. Retrying in %.2fs (attempt %s/%s).",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.is_error:
                raise ManifoldHTTPError(
                    response.status_code,
                    str(response.request.url),
                    response.text,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ManifoldResponseError(
                    f"Manifold API returned invalid JSON from {response.request.url}"
                ) from exc

        raise ManifoldRequestError(
            f"Manifold request failed after {self._max_retries + 1} attempts."
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
            raise ManifoldResponseError("Normalized record must be a dict.")

        record_id = normalized.get("id", "")
        normalized["record_type"] = record_type
        normalized["platform"] = "manifold"
        if record_id:
            normalized["record_id"] = str(record_id)
            normalized[f"{record_type}_id"] = str(record_id)
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

    @classmethod
    def _to_snake_case(cls, value: str) -> str:
        step_1 = cls._SNAKE_CASE_1.sub(r"\1_\2", value)
        return cls._SNAKE_CASE_2.sub(r"\1_\2", step_1).replace("-", "_").lower()


__all__ = [
    "ManifoldConnector",
    "ManifoldConnectorError",
    "ManifoldHTTPError",
    "ManifoldRequestError",
    "ManifoldResponseError",
]
