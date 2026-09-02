from abc import ABC, abstractmethod


class BasePolicy(ABC):
    """Base contract for agent tool permissions."""

    @abstractmethod
    def is_allowed(self, tool_name: str) -> bool:
        """Return whether the tool is allowed."""
        raise NotImplementedError