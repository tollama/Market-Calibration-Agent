from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

try:
    import websockets as _websockets
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests.
    _websockets = None


class PolymarketWSConnector:
    """Async websocket connector for Polymarket stream payloads."""

    def __init__(
        self,
        *,
        ping_interval: float = 20.0,
        reconnect_base: float = 0.5,
        reconnect_max: float = 8.0,
        max_retries: int = 5,
    ) -> None:
        if ping_interval < 0:
            raise ValueError("ping_interval must be >= 0")
        if reconnect_base < 0:
            raise ValueError("reconnect_base must be >= 0")
        if reconnect_max < 0:
            raise ValueError("reconnect_max must be >= 0")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self.ping_interval = ping_interval
        self.reconnect_base = reconnect_base
        self.reconnect_max = reconnect_max
        self.max_retries = max_retries

    async def stream_messages(
        self,
        url: str,
        *,
        subscribe_message: Any = None,
        message_limit: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if message_limit is not None and message_limit < 0:
            raise ValueError("message_limit must be >= 0 when provided")

        if message_limit == 0:
            return

        ws_module = self._require_websockets()
        connection_errors = self._connection_error_types(ws_module)
        yielded = 0
        retries = 0

        while message_limit is None or yielded < message_limit:
            try:
                async with ws_module.connect(
                    url,
                    ping_interval=self.ping_interval,
                ) as websocket:
                    retries = 0
                    if subscribe_message is not None:
                        await websocket.send(json.dumps(subscribe_message))

                    async for frame in websocket:
                        payload = self._decode_json_dict(frame)
                        if payload is None:
                            continue

                        yield payload
                        yielded += 1
                        if message_limit is not None and yielded >= message_limit:
                            return

                    # When no limit is set, end when the server finishes the stream.
                    if message_limit is None:
                        return
            except connection_errors:
                if retries >= self.max_retries:
                    raise

                delay = min(self.reconnect_base * (2**retries), self.reconnect_max)
                retries += 1
                await asyncio.sleep(delay)

    @staticmethod
    def _require_websockets() -> Any:
        if _websockets is None:
            raise RuntimeError(
                "websockets package is required for PolymarketWSConnector "
                "(install it with `pip install websockets`)."
            )
        return _websockets

    @staticmethod
    def _connection_error_types(ws_module: Any) -> tuple[type[BaseException], ...]:
        error_types: list[type[BaseException]] = [
            OSError,
            ConnectionError,
            asyncio.TimeoutError,
        ]

        candidates = [
            ("exceptions", "WebSocketException"),
            ("exceptions", "ConnectionClosed"),
            ("exceptions", "ConnectionClosedError"),
            ("exceptions", "ConnectionClosedOK"),
            ("exceptions", "InvalidURI"),
            ("exceptions", "InvalidStatus"),
            ("", "ConnectionClosed"),
        ]
        for container_name, type_name in candidates:
            container = ws_module
            if container_name:
                container = getattr(ws_module, container_name, None)
            error_type = getattr(container, type_name, None) if container else None
            if isinstance(error_type, type) and issubclass(error_type, BaseException):
                error_types.append(error_type)

        unique_types: list[type[BaseException]] = []
        for error_type in error_types:
            if error_type not in unique_types:
                unique_types.append(error_type)
        return tuple(unique_types)

    @staticmethod
    def _decode_json_dict(frame: Any) -> dict[str, Any] | None:
        if isinstance(frame, bytes):
            try:
                frame = frame.decode("utf-8")
            except UnicodeDecodeError:
                return None

        if not isinstance(frame, str):
            return None

        try:
            payload = json.loads(frame)
        except json.JSONDecodeError:
            return None

        if isinstance(payload, dict):
            return payload
        return None
