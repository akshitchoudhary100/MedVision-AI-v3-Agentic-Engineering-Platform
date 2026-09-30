from abc import ABC, abstractmethod
from typing import Any


class BaseLLM(ABC):
    """Base interface for language-model providers."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Generate a model response."""
        raise NotImplementedError