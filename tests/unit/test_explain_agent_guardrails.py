from __future__ import annotations

from agents.explain_agent import DEFAULT_MODEL, DEFAULT_TEMPERATURE, ExplainAgent
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
        return '{"lines":["line 1","line 2","line 3","line 4","line 5"]}'


def test_explain_falls_back_to_default_model_when_model_is_empty() -> None:
    backend = _StubBackend()
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="   ")

    agent.explain(" summarize this ")

    assert len(backend.calls) == 1
    assert backend.calls[0]["model"] == DEFAULT_MODEL
    assert backend.calls[0]["temperature"] == DEFAULT_TEMPERATURE


def test_explain_prepends_evidence_guardrail_instruction() -> None:
    backend = _StubBackend()
    client = LLMClient(backend=backend)
    agent = ExplainAgent(client=client, model="gpt-custom")

    agent.explain("Market context text.")

    assert len(backend.calls) == 1
    user_prompt = backend.calls[0]["user_prompt"]
    assert isinstance(user_prompt, str)
    assert user_prompt.startswith("Every claim must be grounded only in the provided text.")
    assert "Do not add external facts, numbers, dates, causes, or forecasts." in user_prompt
    assert "If evidence is weak or missing for any claim" in user_prompt
    assert "explicitly state uncertainty" in user_prompt
    assert "avoid definitive wording" in user_prompt
