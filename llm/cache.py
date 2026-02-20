"""Hash-based cache utilities for LLM responses."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Mapping


def _stable_json(payload: Mapping[str, Any]) -> str:
    """Serialize a mapping in a deterministic way for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def make_cache_key(payload: Mapping[str, Any]) -> str:
    """Build a SHA-256 cache key from an arbitrary mapping payload."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8"))
    return digest.hexdigest()


@dataclass
class LLMCache:
    """Thread-safe in-memory cache for parsed LLM responses."""

    _store: dict[str, Any] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def key_for(self, **parts: Any) -> str:
        """Create a hash key from keyword inputs."""
        return make_cache_key(parts)

    def get(self, key: str) -> Any | None:
        """Return a deep copy of cached value, or None if missing."""
        with self._lock:
            value = self._store.get(key)
            return deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        """Set cache value by key."""
        with self._lock:
            self._store[key] = deepcopy(value)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._store.clear()
