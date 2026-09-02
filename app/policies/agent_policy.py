from app.policies.base import BasePolicy


class AgentPolicy(BasePolicy):
    """Simple allow-list policy for an agent."""

    def __init__(self, allowed_tools: set[str]) -> None:
        self.allowed_tools = allowed_tools

    def is_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools