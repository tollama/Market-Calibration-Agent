"""Question quality scoring agent."""

from llm.client import LLMClient, load_prompt
from llm.schemas import QuestionQualityResult


class QuestionQualityAgent:
    """Agent that evaluates question quality."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model
        self._template = load_prompt("question_quality_v1.md")

    def evaluate(self, question: str) -> QuestionQualityResult:
        question_text = question.strip()
        if not question_text:
            raise ValueError("question must be non-empty")

        prompt = f"{self._template}\n\nQuestion:\n{question_text}\n"
        return self._client.generate_json(
            model=self._model,
            prompt_name="question_quality_v1",
            user_prompt=prompt,
            schema=QuestionQualityResult,
            temperature=0.0,
        )
