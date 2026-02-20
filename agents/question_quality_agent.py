"""Question quality scoring agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import QuestionQualityResult

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_PROMPT = "question_quality_v1.md"
_PROMPT_NAME = "question_quality_v1"
_SCHEMA_OVERRIDE = """Use this JSON schema for your final response:
{
  "ambiguity_score": 0.0 to 1.0 number,
  "resolution_risk_score": 0.0 to 1.0 number,
  "trigger_events": [object, ...],
  "rationale_bullets": ["string", "..."] (1 to 5 items)
}
Return only valid JSON with exactly these keys and no extras."""


class QuestionQualityAgent:
    """Agent that evaluates question quality."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        normalized_model = model.strip() if isinstance(model, str) else ""
        self._model = normalized_model or DEFAULT_MODEL
        self._template = load_prompt(DEFAULT_PROMPT)

    def evaluate(self, question: str) -> QuestionQualityResult:
        question_text = question.strip()
        if not question_text:
            raise ValueError("question must be non-empty")

        prompt = f"{self._template}\n\n{_SCHEMA_OVERRIDE}\n\nQuestion:\n{question_text}\n"
        return self._client.generate_json(
            model=self._model,
            prompt_name=_PROMPT_NAME,
            user_prompt=prompt,
            schema=QuestionQualityResult,
            temperature=DEFAULT_TEMPERATURE,
        )
