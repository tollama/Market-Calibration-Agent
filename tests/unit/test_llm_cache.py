from llm.cache import LLMCache, make_cache_key


def test_make_cache_key_is_deterministic_for_same_payload() -> None:
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

    key_a = make_cache_key(payload_a)
    key_b = make_cache_key(payload_b)

    assert key_a == key_b
    assert len(key_a) == 64


def test_make_cache_key_changes_when_input_changes() -> None:
    key_a = make_cache_key({"model": "gpt-test", "prompt": "A"})
    key_b = make_cache_key({"model": "gpt-test", "prompt": "B"})

    assert key_a != key_b


def test_cache_round_trip_with_hash_key() -> None:
    cache = LLMCache()
    key = cache.key_for(model="gpt-test", prompt="hello", temperature=0.0)
    cache.set(key, {"answer": "42"})

    assert cache.get(key) == {"answer": "42"}


def test_cache_returns_deep_copy() -> None:
    cache = LLMCache()
    key = cache.key_for(model="gpt-test", prompt="hello")
    cache.set(key, {"nested": {"value": "safe"}})

    result = cache.get(key)
    assert result == {"nested": {"value": "safe"}}

    assert result is not None
    result["nested"]["value"] = "changed"
    assert cache.get(key) == {"nested": {"value": "safe"}}


def test_cache_miss_returns_none() -> None:
    cache = LLMCache()
    assert cache.get("missing") is None
