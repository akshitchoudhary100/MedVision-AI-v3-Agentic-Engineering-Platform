from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.llm.base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """Adapter for APIs that implement the OpenAI Chat Completions interface."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
    ) -> None:
        if not model.strip():
            raise ValueError("LLM model ID cannot be empty.")

        if not api_key.strip():
            raise RuntimeError(
                "The API key for the selected LLM provider is not configured."
            )

        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_api_messages(messages),
        }

        if tools:
            payload["tools"] = tools

        completion = self.client.chat.completions.create(**payload)

        if not completion.choices:
            raise RuntimeError("The LLM provider returned no completion choices.")

        message = completion.choices[0].message
        normalized_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }

        normalized_tool_calls = []

        for tool_call in message.tool_calls or []:
            raw_arguments = tool_call.function.arguments or "{}"

            try:
                arguments = (
                    json.loads(raw_arguments)
                    if isinstance(raw_arguments, str)
                    else raw_arguments
                )
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Model returned invalid JSON arguments for tool "
                    f"{tool_call.function.name!r}."
                ) from exc

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Tool arguments for {tool_call.function.name!r} "
                    "must be a JSON object."
                )

            normalized_tool_calls.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": arguments,
                    },
                }
            )

        if normalized_tool_calls:
            normalized_message["tool_calls"] = normalized_tool_calls

        # Match the response shape currently consumed by _parse_model_response().
        return {"message": normalized_message}

    @staticmethod
    def _to_api_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")

            if role == "assistant" and message.get("tool_calls"):
                tool_calls = []

                for call in message["tool_calls"]:
                    function = call.get("function") or {}
                    arguments = function.get("arguments", {})

                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments)

                    call_id = call.get("id")
                    if not call_id:
                        raise ValueError(
                            "Assistant tool call is missing its call ID."
                        )

                    tool_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": function["name"],
                                "arguments": arguments,
                            },
                        }
                    )

                converted.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or None,
                        "tool_calls": tool_calls,
                    }
                )

            elif role == "tool":
                call_id = message.get("tool_call_id")
                name = message.get("name") or message.get("tool_name")

                if not call_id or not name:
                    raise ValueError(
                        "Tool result must contain tool_call_id and tool name."
                    )

                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": str(message.get("content", "")),
                    }
                )

            else:
                converted.append(
                    {
                        "role": role,
                        "content": message.get("content") or "",
                    }
                )

        return converted