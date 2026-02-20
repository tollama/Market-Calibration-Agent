from __future__ import annotations

import json

from agents.explain_agent import ExplainAgent
from llm.client import LLMClient


class _StubBackend:
    def __init__(self, lines: list[str]) -> None:
        self._payload = json.dumps({"lines": lines}, ensure_ascii=False)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        return self._payload


def test_explain_enforces_max_140_chars_per_line() -> None:
    long_line = "x" * 200
    backend = _StubBackend([long_line, "line 2", "line 3", "line 4", "line 5"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=False)

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[0] == "x" * 140
    assert all(len(line) <= 140 for line in result.lines)


def test_explain_includes_disclaimer_when_enabled() -> None:
    backend = _StubBackend(["line 1", "line 2", "line 3", "line 4", "line 5"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom")

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[-1] == "투자 조언 아님"


def test_explain_does_not_force_disclaimer_when_disabled() -> None:
    backend = _StubBackend(["line 1", "line 2", "line 3", "line 4", "line 5"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=False)

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[-1] == "line 5"
    assert all("투자 조언 아님" not in line for line in result.lines)
