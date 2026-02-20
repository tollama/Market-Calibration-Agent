"""LLM client wrapper with strict JSON parsing and cache integration."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .cache import LLMCache
from .schemas import from_dict_strict, parse_json_as

T = TypeVar("T")
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class LLMBackend(Protocol):
    """Minimal backend interface expected by LLMClient."""

    def complete(
        self,
        *,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """Generate a raw text completion."""


class LLMClient:
    """Client for structured JSON generations."""

    def __init__(self, backend: LLMBackend, cache: LLMCache | None = None) -> None:
        self._backend = backend
        self._cache = cache if cache is not None else LLMCache()

    @property
    def cache(self) -> LLMCache:
        return self._cache

    def generate_json(
        self,
        *,
        model: str,
        prompt_name: str,
        user_prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cache_context: dict[str, Any] | None = None,
    ) -> T:
        """Generate and parse strict JSON output into a schema object."""
        cache_key = self._cache.key_for(
            model=model,
            prompt_name=prompt_name,
            system_prompt=system_prompt or "",
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            schema=schema.__name__,
            cache_context=cache_context or {},
        )

        cached = self._cache.get(cache_key)
        if cached is not None:
            if not isinstance(cached, dict):
                raise TypeError("cached value must be a dictionary")
            return from_dict_strict(cached, schema)

        raw_output = self._backend.complete(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = parse_json_as(raw_output, schema)
        self._cache.set(cache_key, asdict(parsed))
        return parsed


def load_prompt(filename: str) -> str:
    """Load a prompt from the local prompt directory."""
    prompt_path = _PROMPTS_DIR / filename
    if not prompt_path.is_file():
        raise FileNotFoundError(f"prompt file does not exist: {filename}")
    return prompt_path.read_text(encoding="utf-8")
