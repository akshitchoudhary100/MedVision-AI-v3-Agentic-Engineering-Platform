from typing import Any

from openai import OpenAI

from app.llm.base import BaseLLM


class OpenAILLM(BaseLLM):
    """OpenAI implementation of the V3 LLM interface."""

    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        response = self.client.responses.create(
            model=self.model,
            input=messages,
            tools=tools or [],
        )

        return response