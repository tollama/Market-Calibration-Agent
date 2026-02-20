"""Five-line explanation agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import ExplainFiveLinesResult


class ExplainAgent:
    """Agent that generates a 5-line explanation."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model
        self._template = load_prompt("explain_5lines_v1.md")

    def explain(self, text: str) -> ExplainFiveLinesResult:
        input_text = text.strip()
        if not input_text:
            raise ValueError("text must be non-empty")

        prompt = f"{self._template}\n\nText:\n{input_text}\n"
        return self._client.generate_json(
            model=self._model,
            prompt_name="explain_5lines_v1",
            user_prompt=prompt,
            schema=ExplainFiveLinesResult,
            temperature=0.0,
        )
