"""SQLite-backed cache for parsed LLM responses."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from llm.cache import make_cache_key


class SQLiteLLMCache:
    """Thread-safe persistent cache for parsed LLM responses."""

    def __init__(self, db_path: str | Path = "llm_cache.sqlite3") -> None:
        self._db_path = str(db_path)
        self._lock = RLock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = self._require_connection()
        with self._lock:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _require_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("cache is closed")
        return self._conn

    def key_for(self, **parts: Any) -> str:
        """Create a deterministic cache key from keyword inputs."""
        return make_cache_key(parts)

    def get(self, key: str) -> Any | None:
        """Fetch and parse cached JSON, returning a deep copy when present."""
        conn = self._require_connection()
        with self._lock:
            row = conn.execute(
                "SELECT value FROM llm_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            parsed = json.loads(row[0])
            return deepcopy(parsed)

    def set(self, key: str, value: Any) -> None:
        """Serialize and upsert cache value."""
        conn = self._require_connection()
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn.execute(
                """
                INSERT INTO llm_cache (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, serialized, updated_at),
            )
            conn.commit()

    def clear(self) -> None:
        """Remove all cache entries."""
        conn = self._require_connection()
        with self._lock:
            conn.execute("DELETE FROM llm_cache")
            conn.commit()

    def close(self) -> None:
        """Close the SQLite connection (idempotent)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
