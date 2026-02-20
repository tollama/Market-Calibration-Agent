from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

import pytest

import connectors.polymarket_ws as ws_module
from connectors.polymarket_ws import PolymarketWSConnector


class FakeWebSocketException(Exception):
    """Base fake websocket exception for reconnect tests."""


class FakeConnectionClosed(FakeWebSocketException):
    """Raised when the fake stream disconnects."""


class FakeWebSocket:
    def __init__(self, frames: Iterable[Any]) -> None:
        self._frames = iter(frames)
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)

    def __aiter__(self) -> "FakeWebSocket":
        return self

    async def __anext__(self) -> Any:
        try:
            frame = next(self._frames)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

        if isinstance(frame, BaseException):
            raise frame
        return frame


class FakeConnectionContext:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


class FakeWebSocketsModule:
    class exceptions:
        WebSocketException = FakeWebSocketException
        ConnectionClosed = FakeConnectionClosed

    def __init__(self, connections: list[FakeWebSocket]) -> None:
        self._connections = list(connections)
        self.connect_calls: list[dict[str, Any]] = []

    def connect(self, url: str, *, ping_interval: float) -> FakeConnectionContext:
        self.connect_calls.append({"url": url, "ping_interval": ping_interval})
        if not self._connections:
            raise AssertionError("No fake websocket connection left.")
        return FakeConnectionContext(self._connections.pop(0))


def _collect_messages(
    connector: PolymarketWSConnector,
    *,
    url: str,
    subscribe_message: Any = None,
    message_limit: int | None = None,
) -> list[dict[str, Any]]:
    async def run() -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        async for payload in connector.stream_messages(
            url,
            subscribe_message=subscribe_message,
            message_limit=message_limit,
        ):
            payloads.append(payload)
        return payloads

    return asyncio.run(run())


def test_stream_messages_normal_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = FakeWebSocket(['{"id": 1}', '{"id": 2}'])
    fake_ws_module = FakeWebSocketsModule([fake_socket])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        subscribe_message={"type": "subscribe"},
        message_limit=2,
    )

    assert payloads == [{"id": 1}, {"id": 2}]
    assert len(fake_ws_module.connect_calls) == 1
    assert fake_ws_module.connect_calls[0]["ping_interval"] == 20.0
    assert json.loads(fake_socket.sent_messages[0]) == {"type": "subscribe"}


def test_stream_messages_reconnects_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_socket_1 = FakeWebSocket(['{"id": 1}', FakeConnectionClosed("dropped connection")])
    fake_socket_2 = FakeWebSocket(['{"id": 2}'])
    fake_ws_module = FakeWebSocketsModule([fake_socket_1, fake_socket_2])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(ws_module.asyncio, "sleep", fake_sleep)

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        subscribe_message={"type": "subscribe"},
        message_limit=2,
    )

    assert payloads == [{"id": 1}, {"id": 2}]
    assert sleeps == [0.5]
    assert len(fake_ws_module.connect_calls) == 2
    assert json.loads(fake_socket_1.sent_messages[0]) == {"type": "subscribe"}
    assert json.loads(fake_socket_2.sent_messages[0]) == {"type": "subscribe"}


def test_stream_messages_skips_non_json_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = FakeWebSocket(
        [
            "not-json",
            b"\xff",
            "123",
            '{"accepted": true}',
            '["not", "a", "dict"]',
            '{"accepted": false}',
        ]
    )
    fake_ws_module = FakeWebSocketsModule([fake_socket])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        message_limit=None,
    )

    assert payloads == [{"accepted": True}, {"accepted": False}]


def test_stream_messages_supports_subscribe_message_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_socket = FakeWebSocket(['{"id": 1}'])
    fake_ws_module = FakeWebSocketsModule([fake_socket])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        subscribe_message=[
            {"type": "subscribe", "channel": "one"},
            {"type": "subscribe", "channel": "two"},
        ],
        message_limit=1,
    )

    assert payloads == [{"id": 1}]
    assert [json.loads(message) for message in fake_socket.sent_messages] == [
        {"type": "subscribe", "channel": "one"},
        {"type": "subscribe", "channel": "two"},
    ]


def test_stream_messages_supports_subscribe_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_socket_1 = FakeWebSocket(['{"id": 1}', FakeConnectionClosed("dropped connection")])
    fake_socket_2 = FakeWebSocket(['{"id": 2}'])
    fake_ws_module = FakeWebSocketsModule([fake_socket_1, fake_socket_2])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    reconnect_indices: list[int] = []

    def subscribe_builder(reconnect_index: int) -> dict[str, Any]:
        reconnect_indices.append(reconnect_index)
        return {"type": "subscribe", "reconnect_index": reconnect_index}

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        subscribe_message=subscribe_builder,
        message_limit=2,
    )

    assert payloads == [{"id": 1}, {"id": 2}]
    assert reconnect_indices == [0, 1]
    assert [json.loads(message) for message in fake_socket_1.sent_messages] == [
        {"type": "subscribe", "reconnect_index": 0}
    ]
    assert [json.loads(message) for message in fake_socket_2.sent_messages] == [
        {"type": "subscribe", "reconnect_index": 1}
    ]


def test_stream_messages_last_stats_increments(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket_1 = FakeWebSocket(["not-json", '{"id": 1}', FakeConnectionClosed("dropped")])
    fake_socket_2 = FakeWebSocket([b"\xff", '{"id": 2}'])
    fake_ws_module = FakeWebSocketsModule([fake_socket_1, fake_socket_2])
    monkeypatch.setattr(ws_module, "_websockets", fake_ws_module)

    connector = PolymarketWSConnector()
    payloads = _collect_messages(
        connector,
        url="wss://example.invalid/stream",
        message_limit=2,
    )

    assert payloads == [{"id": 1}, {"id": 2}]
    assert connector.last_stats == {
        "reconnects": 1,
        "yielded": 2,
        "skipped_non_json": 2,
    }
