from __future__ import annotations

import os

from dotenv import dotenv_values, find_dotenv

from app.llm.base import BaseLLM
from app.llm.ollama_llm import OllamaLLM
from app.llm.openai_compatible_llm import OpenAICompatibleLLM


def _read_settings() -> dict[str, str]:
    """Read .env for each new invocation; shell environment takes precedence."""
    env_path = find_dotenv(usecwd=True)

    settings = {}

    if env_path:
        settings.update(
            {
                key: value
                for key, value in dotenv_values(env_path).items()
                if value is not None
            }
        )

    settings.update(os.environ)
    return settings


def create_llm_from_env() -> BaseLLM:
    settings = _read_settings()

    provider = settings.get("LLM_PROVIDER", "ollama").strip().lower()
    model = settings.get("LLM_MODEL", "").strip()

    if provider == "ollama":
        return OllamaLLM(
            model=model or "granite4:3b",
            base_url=settings.get(
                "OLLAMA_BASE_URL",
                "http://localhost:11434",
            ),
        )

    if provider == "groq":
        return OpenAICompatibleLLM(
            model=model or "openai/gpt-oss-20b",
            api_key=settings.get("GROQ_API_KEY", ""),
            base_url=settings.get(
                "GROQ_BASE_URL",
                "https://api.groq.com/openai/v1",
            ),
        )

    if provider == "openrouter":
        if not model:
            raise RuntimeError(
                "Set LLM_MODEL to a model ID supported by OpenRouter."
            )

        return OpenAICompatibleLLM(
            model=model,
            api_key=settings.get("OPENROUTER_API_KEY", ""),
            base_url=settings.get(
                "OPENROUTER_BASE_URL",
                "https://openrouter.ai/api/v1",
            ),
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER={provider!r}. "
        "Choose 'ollama', 'groq', or 'openrouter'."
    )