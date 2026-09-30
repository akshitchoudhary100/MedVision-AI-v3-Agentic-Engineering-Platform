from typing import Any

import requests

from app.llm.base import BaseLLM


class OllamaLLM(BaseLLM):
    """Ollama-backed implementation of the V3 LLM interface."""

    def __init__(
        self,
        model: str = "qwen3:4b",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self.model = model
        self.base_url = base_url

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "num_predict": 1000,
            },
        }

        if tools:
            payload["tools"] = tools

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300,
        )

        response.raise_for_status()

        return response.json()