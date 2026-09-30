from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Base contract for tools available to agents."""

    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool."""
        raise NotImplementedError

    @abstractmethod
    def definition(self) -> dict[str, Any]:
        """Return the tool schema exposed to the LLM."""
        raise NotImplementedError