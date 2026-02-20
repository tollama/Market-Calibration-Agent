from llm.cache import make_cache_key
from llm.sqlite_cache import SQLiteLLMCache


def test_sqlite_cache_key_for_is_deterministic() -> None:
    cache = SQLiteLLMCache(":memory:")
    payload_a = {
        "model": "gpt-test",
        "prompt": "What is calibration?",
        "params": {"temperature": 0.0, "max_tokens": 256},
    }
    payload_b = {
        "params": {"max_tokens": 256, "temperature": 0.0},
        "prompt": "What is calibration?",
        "model": "gpt-test",
    }

    try:
        key_a = cache.key_for(**payload_a)
        key_b = cache.key_for(**payload_b)

        assert key_a == key_b
        assert key_a == make_cache_key(payload_a)
    finally:
        cache.close()


def test_sqlite_cache_persists_across_instances(tmp_path) -> None:
    db_path = tmp_path / "llm_cache.sqlite3"
    payload = {"nested": {"value": "safe"}}

    first = SQLiteLLMCache(db_path)
    key = first.key_for(model="gpt-test", prompt="hello")
    try:
        first.set(key, payload)
    finally:
        first.close()

    second = SQLiteLLMCache(db_path)
    try:
        result = second.get(key)
        assert result == payload

        assert result is not None
        result["nested"]["value"] = "changed"
        assert second.get(key) == payload
    finally:
        second.close()


def test_sqlite_cache_overwrite_existing_value(tmp_path) -> None:
    db_path = tmp_path / "llm_cache.sqlite3"
    cache = SQLiteLLMCache(db_path)
    key = cache.key_for(model="gpt-test", prompt="overwrite")

    try:
        cache.set(key, {"answer": "first"})
        cache.set(key, {"answer": "second"})

        assert cache.get(key) == {"answer": "second"}
    finally:
        cache.close()


def test_sqlite_cache_clear_removes_entries(tmp_path) -> None:
    db_path = tmp_path / "llm_cache.sqlite3"
    cache = SQLiteLLMCache(db_path)
    key_a = cache.key_for(model="gpt-test", prompt="a")
    key_b = cache.key_for(model="gpt-test", prompt="b")

    try:
        cache.set(key_a, {"answer": 1})
        cache.set(key_b, {"answer": 2})
        cache.clear()

        assert cache.get(key_a) is None
        assert cache.get(key_b) is None
    finally:
        cache.close()
