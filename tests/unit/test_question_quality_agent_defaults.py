from __future__ import annotations

from agents.question_quality_agent import (
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    QuestionQualityAgent,
)
from llm.client import LLMClient


class _StubBackend:
    def __init__(self) -> None:
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
        return (
            '{"ambiguity_score":0.18,"resolution_risk_score":0.27,'
            '"trigger_events":[{"type":"deadline","date":"2026-03-01"}],'
            '"rationale_bullets":["Question is specific and includes a time horizon."]}'
        )


def test_evaluate_falls_back_to_default_model_when_model_is_empty() -> None:
    backend = _StubBackend()
    client = LLMClient(backend=backend)
    agent = QuestionQualityAgent(client=client, model="   ")

    agent.evaluate(" Is this specific enough? ")

    assert len(backend.calls) == 1
    assert backend.calls[0]["model"] == DEFAULT_MODEL
    assert backend.calls[0]["temperature"] == DEFAULT_TEMPERATURE


def test_evaluate_uses_default_temperature_with_explicit_model() -> None:
    backend = _StubBackend()
    client = LLMClient(backend=backend)
    agent = QuestionQualityAgent(client=client, model="gpt-custom")

    agent.evaluate("What evidence supports this forecast?")

    assert len(backend.calls) == 1
    assert backend.calls[0]["model"] == "gpt-custom"
    assert backend.calls[0]["temperature"] == DEFAULT_TEMPERATURE
