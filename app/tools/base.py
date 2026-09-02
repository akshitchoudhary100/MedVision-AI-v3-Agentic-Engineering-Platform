from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Base contract for tools available to agents."""

    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError