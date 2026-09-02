from typing import Any

from app.tools.base import BaseTool


class ToolRegistry:
    """Registry of tools available to an agent."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Tool not found: {name}") from None

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        return tool.execute(**kwargs)