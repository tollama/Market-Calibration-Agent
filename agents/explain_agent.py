"""Five-line explanation agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import ExplainFiveLinesResult

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_PROMPT = "explain_5lines_v1.md"
_PROMPT_NAME = "explain_5lines_v1"
_EVIDENCE_GUARDRAIL = (
    "Every claim must be grounded only in the provided text. "
    "Do not add external facts, numbers, dates, causes, or forecasts. "
    "If evidence is weak or missing for any claim, explicitly state uncertainty "
    "and avoid definitive wording."
)
_MAX_LINE_LENGTH = 140
_DISCLAIMER_TEXT = "투자 조언 아님"


class ExplainAgent:
    """Agent that generates a 5-line explanation."""

    def __init__(self, client: LLMClient, model: str, include_disclaimer: bool = True) -> None:
        self._client = client
        normalized_model = model.strip() if isinstance(model, str) else ""
        self._model = normalized_model or DEFAULT_MODEL
        self._template = load_prompt(DEFAULT_PROMPT)
        self._include_disclaimer = bool(include_disclaimer)

    def explain(self, text: str) -> ExplainFiveLinesResult:
        input_text = text.strip()
        if not input_text:
            raise ValueError("text must be non-empty")

        prompt = f"{_EVIDENCE_GUARDRAIL}\n\n{self._template}\n\nText:\n{input_text}\n"
        generated = self._client.generate_json(
            model=self._model,
            prompt_name=_PROMPT_NAME,
            user_prompt=prompt,
            schema=ExplainFiveLinesResult,
            temperature=DEFAULT_TEMPERATURE,
        )
        return self._apply_output_policy(generated)

    def _apply_output_policy(self, result: ExplainFiveLinesResult) -> ExplainFiveLinesResult:
        lines = [self._truncate_line(line.strip()) for line in result.lines]
        if self._include_disclaimer:
            lines[-1] = self._truncate_line(_DISCLAIMER_TEXT)
        return ExplainFiveLinesResult(lines=lines)

    @staticmethod
    def _truncate_line(line: str) -> str:
        if len(line) <= _MAX_LINE_LENGTH:
            return line
        return line[:_MAX_LINE_LENGTH]
