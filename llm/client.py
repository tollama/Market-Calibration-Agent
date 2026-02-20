"""LLM client wrapper with strict JSON parsing and cache integration."""

from __future__ import annotations

import inspect
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .cache import LLMCache
from .policy import DEFAULT_SEED, DEFAULT_TEMPERATURE, resolve_sampling_policy
from .schemas import from_dict_strict, parse_json_as

T = TypeVar("T")
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class CacheBackend(Protocol):
    """Duck-typed cache backend interface used by LLMClient."""

    def key_for(self, **parts: Any) -> str:
        """Build a deterministic cache key."""

    def get(self, key: str) -> Any | None:
        """Fetch a cached value by key."""

    def set(self, key: str, value: Any) -> None:
        """Store a value by key."""


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


def _backend_accepts_seed(complete_fn: Any) -> bool:
    """Return True when a completion callable can receive a seed kwarg."""
    try:
        parameters = inspect.signature(complete_fn).parameters.values()
    except (TypeError, ValueError):
        return False
    for parameter in parameters:
        if parameter.name == "seed":
            return True
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return False


class LLMClient:
    """Client for structured JSON generations."""

    def __init__(
        self,
        backend: LLMBackend,
        cache: CacheBackend | None = None,
        cache_backend: CacheBackend | None = None,
    ) -> None:
        self._backend = backend
        self._backend_accepts_seed = _backend_accepts_seed(backend.complete)
        resolved_cache = cache_backend if cache_backend is not None else cache
        self._cache: CacheBackend = resolved_cache if resolved_cache is not None else LLMCache()

    @property
    def cache(self) -> CacheBackend:
        return self._cache

    def generate_json(
        self,
        *,
        model: str,
        prompt_name: str,
        user_prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        seed: int | None = DEFAULT_SEED,
        max_tokens: int | None = None,
        cache_context: dict[str, Any] | None = None,
    ) -> T:
        """Generate and parse strict JSON output into a schema object."""
        sampling_policy = resolve_sampling_policy(temperature=temperature, seed=seed)
        cache_key = self._cache.key_for(
            model=model,
            prompt_name=prompt_name,
            system_prompt=system_prompt or "",
            user_prompt=user_prompt,
            temperature=sampling_policy.temperature,
            seed=sampling_policy.seed,
            max_tokens=max_tokens,
            schema=schema.__name__,
            sampling_policy=sampling_policy.as_metadata(),
            cache_context=cache_context or {},
        )

        cached = self._cache.get(cache_key)
        if cached is not None:
            if not isinstance(cached, dict):
                raise TypeError("cached value must be a dictionary")
            return from_dict_strict(cached, schema)

        complete_kwargs: dict[str, Any] = {
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": sampling_policy.temperature,
            "max_tokens": max_tokens,
        }
        if self._backend_accepts_seed:
            complete_kwargs["seed"] = sampling_policy.seed

        raw_output = self._backend.complete(**complete_kwargs)
        parsed = parse_json_as(raw_output, schema)
        self._cache.set(cache_key, asdict(parsed))
        return parsed


def load_prompt(filename: str) -> str:
    """Load a prompt from the local prompt directory."""
    prompt_path = _PROMPTS_DIR / filename
    if not prompt_path.is_file():
        raise FileNotFoundError(f"prompt file does not exist: {filename}")
    return prompt_path.read_text(encoding="utf-8")
