from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm.cache import make_cache_key
from llm.client import LLMClient
from llm.policy import DEFAULT_SEED, DEFAULT_TEMPERATURE, DEFAULT_TOP_P


@dataclass(frozen=True)
class _DemoSchema:
    answer: str


class _RecordingCache:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}
        self.key_inputs: list[dict[str, Any]] = []
        self.keys: list[str] = []

    def key_for(self, **parts: Any) -> str:
        self.key_inputs.append(parts)
        key = make_cache_key(parts)
        self.keys.append(key)
        return key

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        if not isinstance(value, dict):
            raise TypeError("expected dictionary cache values")
        self._store[key] = value


class _SeedAwareBackend:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
        seed: int | None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "seed": seed,
            }
        )
        return self._response


class _LegacyBackend:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self._response


def _generate(client: LLMClient, *, seed: int | None = DEFAULT_SEED) -> _DemoSchema:
    return client.generate_json(
        model="gpt-test",
        prompt_name="sampling-policy",
        user_prompt="Return deterministic response",
        schema=_DemoSchema,
        seed=seed,
    )


def test_generate_json_cache_key_includes_deterministic_sampling_metadata() -> None:
    backend = _SeedAwareBackend('{"answer":"stable"}')
    cache = _RecordingCache()
    client = LLMClient(backend=backend, cache_backend=cache)

    first = _generate(client)
    second = _generate(client)

    assert first == _DemoSchema(answer="stable")
    assert second == _DemoSchema(answer="stable")
    assert backend.calls == [
        {
            "model": "gpt-test",
            "system_prompt": None,
            "user_prompt": "Return deterministic response",
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": None,
            "seed": DEFAULT_SEED,
        }
    ]
    assert len(cache.key_inputs) == 2
    assert cache.keys[0] == cache.keys[1]
    assert cache.key_inputs[0]["temperature"] == DEFAULT_TEMPERATURE
    assert cache.key_inputs[0]["top_p"] == DEFAULT_TOP_P
    assert cache.key_inputs[0]["seed"] == DEFAULT_SEED
    assert cache.key_inputs[0]["sampling_policy"] == {
        "seed": DEFAULT_SEED,
        "temperature": DEFAULT_TEMPERATURE,
        "top_p": DEFAULT_TOP_P,
    }


def test_generate_json_passes_seed_when_backend_supports_it() -> None:
    backend = _SeedAwareBackend('{"answer":"seeded"}')
    client = LLMClient(backend=backend)

    result = _generate(client, seed=7)

    assert result == _DemoSchema(answer="seeded")
    assert len(backend.calls) == 1
    assert backend.calls[0]["seed"] == 7


def test_generate_json_skips_seed_for_legacy_backend_signature() -> None:
    backend = _LegacyBackend('{"answer":"legacy"}')
    client = LLMClient(backend=backend)

    result = _generate(client)

    assert result == _DemoSchema(answer="legacy")
    assert len(backend.calls) == 1
    assert backend.calls[0]["temperature"] == DEFAULT_TEMPERATURE
