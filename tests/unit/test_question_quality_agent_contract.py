from __future__ import annotations

import pytest

from agents.question_quality_agent import DEFAULT_TEMPERATURE, QuestionQualityAgent
from llm.client import LLMClient
from llm.schemas import StrictJSONError


class _QueuedBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

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
        if not self._responses:
            raise AssertionError("no queued response available")
        return self._responses.pop(0)


def test_question_quality_agent_retries_on_strict_parse_failures() -> None:
    backend = _QueuedBackend(
        responses=[
            '{"ambiguity_score":0.2}',  # missing required keys
            "not-json",  # invalid JSON
            (
                '{"market_id":"market-42","ambiguity_score":0.18,"resolution_risk_score":0.29,'
                '"trigger_events":[{"type":"deadline","date":"2026-03-01"}],'
                '"rationale_bullets":["Question is time-bound and falsifiable."],'
                '"llm_model":"gpt-5.3-codex","prompt_version":"question_quality_v1"}'
            ),
        ]
    )
    client = LLMClient(backend=backend)
    agent = QuestionQualityAgent(client=client, model="gpt-5.3-codex")

    result = agent.evaluate("Will this resolve clearly?", market_id="market-42")

    assert result.market_id == "market-42"
    assert result.prompt_version == "question_quality_v1"
    assert len(backend.calls) == 3
    assert all(call["temperature"] == DEFAULT_TEMPERATURE for call in backend.calls)
    assert '"llm_model": "non-empty string"' in str(backend.calls[0]["user_prompt"])
    assert '"prompt_version": "non-empty string"' in str(backend.calls[0]["user_prompt"])
    assert "Retry attempt 2/3." in str(backend.calls[1]["user_prompt"])
    assert "Retry attempt 3/3." in str(backend.calls[2]["user_prompt"])


def test_question_quality_agent_raises_after_three_failed_parse_attempts() -> None:
    backend = _QueuedBackend(
        responses=[
            "not-json",
            '{"market_id":"market-42"}',
            '{"resolution_risk_score":0.2}',
        ]
    )
    client = LLMClient(backend=backend)
    agent = QuestionQualityAgent(client=client, model="gpt-5.3-codex")

    with pytest.raises(StrictJSONError):
        agent.evaluate("Will this resolve clearly?", market_id="market-42")

    assert len(backend.calls) == 3
    assert all(call["temperature"] == DEFAULT_TEMPERATURE for call in backend.calls)
