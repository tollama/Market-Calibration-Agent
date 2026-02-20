"""Five-line explanation agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import ExplainFiveLinesResult

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_PROMPT = "explain_5lines_v1.md"
_PROMPT_NAME = "explain_5lines_v1"
_EVIDENCE_GUARDRAIL = (
    "If the provided text lacks evidence for a claim, explicitly state uncertainty "
    "and do not invent facts."
)


class ExplainAgent:
    """Agent that generates a 5-line explanation."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        normalized_model = model.strip() if isinstance(model, str) else ""
        self._model = normalized_model or DEFAULT_MODEL
        self._template = load_prompt(DEFAULT_PROMPT)

    def explain(self, text: str) -> ExplainFiveLinesResult:
        input_text = text.strip()
        if not input_text:
            raise ValueError("text must be non-empty")

        prompt = f"{_EVIDENCE_GUARDRAIL}\n\n{self._template}\n\nText:\n{input_text}\n"
        return self._client.generate_json(
            model=self._model,
            prompt_name=_PROMPT_NAME,
            user_prompt=prompt,
            schema=ExplainFiveLinesResult,
            temperature=DEFAULT_TEMPERATURE,
        )
