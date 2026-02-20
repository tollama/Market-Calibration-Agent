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
    backend = _StubBackend([long_line, "line two", "line three", "line four", "line five"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=False)

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[0] == "x" * 140
    assert all(len(line) <= 140 for line in result.lines)


def test_explain_includes_disclaimer_when_enabled() -> None:
    backend = _StubBackend(["line one", "line two", "line three", "line four", "line five"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom")

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[-1] == "투자 조언 아님"


def test_explain_does_not_force_disclaimer_when_disabled() -> None:
    backend = _StubBackend(["line one", "line two", "line three", "line four", "line five"])
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=False)

    result = agent.explain("Market context text.")

    assert len(result.lines) == 5
    assert result.lines[-1] == "line five"
    assert all("투자 조언 아님" not in line for line in result.lines)


def test_explain_marks_line_when_numeric_token_not_in_source() -> None:
    backend = _StubBackend(
        [
            "확률은 73%다",
            "추가 해설",
            "시장 맥락",
            "변동성 유의",
            "결론 요약",
        ]
    )
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=False)

    result = agent.explain("시장 참여자 반응이 엇갈린다.")

    assert len(result.lines) == 5
    assert "(근거 불충분)" in result.lines[0]
    assert all(len(line) <= 140 for line in result.lines)


def test_explain_disclaimer_still_overrides_last_line() -> None:
    backend = _StubBackend(
        [
            "맥락 요약",
            "근거 설명",
            "리스크 정리",
            "변수 점검",
            "반드시 오른다",
        ]
    )
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom", include_disclaimer=True)

    result = agent.explain("현재는 방향성 단서가 제한적이다.")

    assert len(result.lines) == 5
    assert result.lines[-1] == "투자 조언 아님"
