from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://gamma-api.polymarket.com"


class GammaConnectorError(Exception):
    """Base exception for Gamma connector errors."""


class GammaRequestError(GammaConnectorError):
    """Raised when an HTTP request fails after retries."""


class GammaHTTPError(GammaConnectorError):
    """Raised when the server returns a non-retryable HTTP error."""

    def __init__(self, status_code: int, url: str, body: str | None = None) -> None:
        self.status_code = status_code
        self.url = url
        self.body = body
        preview = (body or "").strip().replace("\n", " ")
        if len(preview) > 200:
            preview = f"{preview[:197]}..."
        message = f"Gamma API returned HTTP {status_code} for {url}"
        if preview:
            message = f"{message}: {preview}"
        super().__init__(message)


class GammaResponseError(GammaConnectorError):
    """Raised when the response cannot be parsed or paginated safely."""


class GammaConnector:
    """Async Polymarket Gamma API client with pagination, retries, and normalization."""

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

    async def __aenter__(self) -> "GammaConnector":
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
            limit=limit,
            params=params,
        )

    async def _fetch_paginated(
        self,
        *,
        endpoint: str,
        record_type: str,
        limit: int,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be > 0")

        base_params: dict[str, Any] = dict(params or {})
        base_params.setdefault("limit", limit)

        cursor: str | None = None
        offset = int(base_params.get("offset", 0))
        force_offset_mode = "offset" in base_params
        seen_pagination_tokens: set[str] = set()
        normalized_records: list[dict[str, Any]] = []

        while True:
            page_params = dict(base_params)
            if cursor is not None:
                page_params["cursor"] = cursor
                page_params.pop("offset", None)
            elif force_offset_mode:
                page_params["offset"] = offset
                page_params.pop("cursor", None)

            payload = await self._request_json(endpoint=endpoint, params=page_params)
            items, next_cursor, has_more, is_list_payload = self._extract_page(
                payload, record_type
            )

            if not items:
                break

            normalized_records.extend(
                self._normalize_record(item, record_type) for item in items
            )

            if next_cursor:
                token = f"cursor:{next_cursor}"
                if token in seen_pagination_tokens:
                    raise GammaResponseError(
                        f"Repeated pagination cursor detected: {next_cursor}"
                    )
                seen_pagination_tokens.add(token)
                cursor = next_cursor
                continue

            should_offset_page = force_offset_mode or has_more or (
                is_list_payload and len(items) >= limit
            )
            if should_offset_page:
                offset += len(items)
                token = f"offset:{offset}"
                if token in seen_pagination_tokens:
                    raise GammaResponseError(
                        f"Repeated pagination offset detected: {offset}"
                    )
                seen_pagination_tokens.add(token)
                force_offset_mode = True
                continue

            break

        return normalized_records

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
                    "Gamma request failed (%s). Retrying in %.2fs (attempt %s/%s).",
                    exc.__class__.__name__,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                if attempt >= self._max_retries:
                    raise GammaHTTPError(
                        response.status_code,
                        str(response.request.url),
                        response.text,
                    )
                delay = self._retry_delay(attempt)
                self._logger.warning(
                    "Gamma API returned retryable status %s. Retrying in %.2fs (attempt %s/%s).",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.is_error:
                raise GammaHTTPError(
                    response.status_code,
                    str(response.request.url),
                    response.text,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise GammaResponseError(
                    f"Gamma API returned invalid JSON from {response.request.url}"
                ) from exc

        raise GammaRequestError(
            f"Gamma request failed after {self._max_retries + 1} attempts."
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
            self._backoff_base * (self._backoff_factor ** attempt),
        )
        if self._backoff_jitter > 0:
            spread = delay * self._backoff_jitter
            delay += random.uniform(-spread, spread)
        return max(0.0, delay)

    def _extract_page(
        self, payload: Any, record_type: str
    ) -> tuple[list[Mapping[str, Any]], str | None, bool, bool]:
        items_raw: Any
        next_cursor: str | None = None
        has_more = False
        is_list_payload = False

        if isinstance(payload, list):
            items_raw = payload
            is_list_payload = True
        elif isinstance(payload, Mapping):
            items_raw = None
            candidate_keys = (
                f"{record_type}s",
                "data",
                "results",
                "items",
            )
            for key in candidate_keys:
                candidate_value = payload.get(key)
                if isinstance(candidate_value, list):
                    items_raw = candidate_value
                    break

            if items_raw is None:
                raise GammaResponseError(
                    f"Could not find list records in {record_type} response payload."
                )

            next_cursor_value = payload.get("next_cursor") or payload.get("nextCursor")
            if next_cursor_value not in (None, "", False):
                next_cursor = str(next_cursor_value)

            has_more = bool(payload.get("has_more") or payload.get("hasMore"))
        else:
            raise GammaResponseError("Unsupported response payload type.")

        if not isinstance(items_raw, list):
            raise GammaResponseError("Expected a list of records in response payload.")

        items: list[Mapping[str, Any]] = []
        for entry in items_raw:
            if not isinstance(entry, Mapping):
                raise GammaResponseError("Each record in response payload must be an object.")
            items.append(entry)
        return items, next_cursor, has_more, is_list_payload

    def _normalize_record(
        self, record: Mapping[str, Any], record_type: str
    ) -> dict[str, Any]:
        normalized = self._normalize_value(record)
        if not isinstance(normalized, dict):
            raise GammaResponseError("Normalized record must be a dict.")

        record_id = self._extract_record_id(normalized, record_type)
        normalized["record_type"] = record_type
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
        candidate_keys = [f"{record_type}_id", "id", "condition_id", "slug"]
        for key in candidate_keys:
            value = record.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @classmethod
    def _to_snake_case(cls, value: str) -> str:
        step_1 = cls._SNAKE_CASE_1.sub(r"\1_\2", value)
        return cls._SNAKE_CASE_2.sub(r"\1_\2", step_1).replace("-", "_").lower()
