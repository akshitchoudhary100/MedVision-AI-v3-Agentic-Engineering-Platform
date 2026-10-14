from __future__ import annotations

import json
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
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages),
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

    @staticmethod
    def _to_ollama_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")

            if role == "tool":
                # Ollama does not need the OpenAI tool_call_id.
                converted.append(
                    {
                        "role": "tool",
                        "content": str(message.get("content", "")),
                    }
                )
                continue

            item: dict[str, Any] = {
                "role": role,
                "content": message.get("content") or "",
            }

            if role == "assistant" and message.get("tool_calls"):
                ollama_calls = []

                for call in message["tool_calls"]:
                    function = call.get("function") or {}
                    arguments = function.get("arguments", {})

                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)

                    if not isinstance(arguments, dict):
                        raise ValueError(
                            "Ollama tool arguments must be a JSON object."
                        )

                    ollama_calls.append(
                        {
                            "function": {
                                "name": function["name"],
                                "arguments": arguments,
                            }
                        }
                    )

                item["tool_calls"] = ollama_calls

            converted.append(item)

        return converted