from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from llm.client import LLMClient
from llm.policy import DEFAULT_SEED, DEFAULT_TOP_P, resolve_sampling_policy


@dataclass(frozen=True)
class _DemoSchema:
    answer: str


class _TopPSupportedBackend:
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
        top_p: float,
        seed: int | None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "seed": seed,
            }
        )
        return self._response


class _SeedOnlyBackend:
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


def _generate(
    client: LLMClient,
    *,
    top_p: float = DEFAULT_TOP_P,
    seed: int | None = DEFAULT_SEED,
) -> _DemoSchema:
    return client.generate_json(
        model="gpt-test",
        prompt_name="top-p-policy",
        user_prompt="Return deterministic response",
        schema=_DemoSchema,
        top_p=top_p,
        seed=seed,
    )


def test_resolve_sampling_policy_includes_default_top_p() -> None:
    policy = resolve_sampling_policy()
    assert policy.top_p == DEFAULT_TOP_P
    assert policy.as_metadata()["top_p"] == DEFAULT_TOP_P


@pytest.mark.parametrize("top_p", [0.0, -0.1, 1.01])
def test_resolve_sampling_policy_rejects_invalid_top_p(top_p: float) -> None:
    with pytest.raises(ValueError, match="top_p"):
        resolve_sampling_policy(top_p=top_p)


def test_generate_json_passes_top_p_when_backend_supports_it() -> None:
    backend = _TopPSupportedBackend('{"answer":"top-p"}')
    client = LLMClient(backend=backend)

    result = _generate(client, top_p=0.35, seed=7)

    assert result == _DemoSchema(answer="top-p")
    assert len(backend.calls) == 1
    assert backend.calls[0]["top_p"] == 0.35
    assert backend.calls[0]["seed"] == 7


def test_generate_json_skips_top_p_for_seed_only_backend_signature() -> None:
    backend = _SeedOnlyBackend('{"answer":"seed-only"}')
    client = LLMClient(backend=backend)

    result = _generate(client, top_p=0.2, seed=9)

    assert result == _DemoSchema(answer="seed-only")
    assert len(backend.calls) == 1
    assert "top_p" not in backend.calls[0]
    assert backend.calls[0]["seed"] == 9
