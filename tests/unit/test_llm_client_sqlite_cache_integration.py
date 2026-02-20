from __future__ import annotations

from dataclasses import dataclass

from llm.client import LLMClient
from llm.sqlite_cache import SQLiteLLMCache


@dataclass(frozen=True)
class _DemoSchema:
    answer: str


class _StubBackend:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0

    def complete(
        self,
        *,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        self.calls += 1
        return self._response


def _generate(client: LLMClient) -> _DemoSchema:
    return client.generate_json(
        model="gpt-test",
        prompt_name="cache-integration",
        user_prompt="Say hello",
        schema=_DemoSchema,
    )


def test_generate_json_uses_default_in_memory_cache() -> None:
    backend = _StubBackend('{"answer":"cached"}')
    client = LLMClient(backend=backend)

    first = _generate(client)
    second = _generate(client)

    assert first == _DemoSchema(answer="cached")
    assert second == _DemoSchema(answer="cached")
    assert backend.calls == 1


def test_generate_json_hits_shared_sqlite_cache_across_clients(tmp_path) -> None:
    db_path = tmp_path / "llm_client_cache.sqlite3"
    cache_one = SQLiteLLMCache(db_path)
    cache_two = SQLiteLLMCache(db_path)

    try:
        backend_one = _StubBackend('{"answer":"from-first-client"}')
        client_one = LLMClient(backend=backend_one, cache_backend=cache_one)

        first = _generate(client_one)

        backend_two = _StubBackend('{"answer":"from-second-client"}')
        client_two = LLMClient(backend=backend_two, cache_backend=cache_two)

        second = _generate(client_two)

        assert first == _DemoSchema(answer="from-first-client")
        assert second == _DemoSchema(answer="from-first-client")
        assert backend_one.calls == 1
        assert backend_two.calls == 0
    finally:
        cache_one.close()
        cache_two.close()
