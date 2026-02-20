"""Question quality scoring agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import QuestionQualityResult, StrictJSONError

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_PROMPT = "question_quality_v1.md"
_PROMPT_NAME = "question_quality_v1"
_MAX_ATTEMPTS = 3
_SCHEMA_OVERRIDE = """Use this JSON schema for your final response:
{
  "market_id": "non-empty string",
  "ambiguity_score": 0.0 to 1.0 number,
  "resolution_risk_score": 0.0 to 1.0 number,
  "trigger_events": [object, ...],
  "rationale_bullets": ["string", "..."] (1 to 5 items),
  "llm_model": "non-empty string",
  "prompt_version": "non-empty string"
}
Return only valid JSON with exactly these keys and no extras.
Set `market_id` to the provided market ID.
Set `llm_model` to the model name you are responding with.
Set `prompt_version` to `question_quality_v1`."""
_RETRY_PROMPT_SUFFIX = (
    "Previous output failed strict JSON validation. "
    "Return only one JSON object that exactly matches the required schema and keys."
)


class QuestionQualityAgent:
    """Agent that evaluates question quality."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        normalized_model = model.strip() if isinstance(model, str) else ""
        self._model = normalized_model or DEFAULT_MODEL
        self._template = load_prompt(DEFAULT_PROMPT)

    def evaluate(
        self,
        question: str,
        *,
        market_id: str = "unknown_market",
    ) -> QuestionQualityResult:
        question_text = question.strip()
        if not question_text:
            raise ValueError("question must be non-empty")

        normalized_market_id = market_id.strip() if isinstance(market_id, str) else ""
        if not normalized_market_id:
            normalized_market_id = "unknown_market"

        base_prompt = (
            f"{self._template}\n\n{_SCHEMA_OVERRIDE}\n\n"
            f"Market ID:\n{normalized_market_id}\n\n"
            f"Question:\n{question_text}\n"
        )

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            prompt = base_prompt
            if attempt > 1:
                prompt = (
                    f"{base_prompt}\n\n{_RETRY_PROMPT_SUFFIX}\n"
                    f"Retry attempt {attempt}/{_MAX_ATTEMPTS}.\n"
                )
            try:
                return self._client.generate_json(
                    model=self._model,
                    prompt_name=_PROMPT_NAME,
                    user_prompt=prompt,
                    schema=QuestionQualityResult,
                    temperature=DEFAULT_TEMPERATURE,
                )
            except StrictJSONError:
                if attempt == _MAX_ATTEMPTS:
                    raise

        raise RuntimeError("question quality evaluation failed unexpectedly")
