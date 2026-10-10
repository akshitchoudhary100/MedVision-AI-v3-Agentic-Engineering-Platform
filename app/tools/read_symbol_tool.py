from typing import Any

from app.tools.base import BaseTool
from app.tools.code_index import CodeIndex
from app.tools.read_symbol import read_symbol


class ReadSymbolTool(BaseTool):
    name = "read_symbol"

    description = (
    "Read one specific function or class from a Python file. "
    "Use this when you need to inspect a particular symbol. "
    "Prefer this over read_file when only one symbol is relevant, "
    "because it returns less code and saves context."
    )

    def __init__(self, index: CodeIndex | None = None) -> None:
        self.index = index

    def definition(self) -> dict[str, Any]:
        return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Repository-relative Python file path.",
                    },
                    "symbol_name": {
                        "type": "string",
                        "description": "Function or class to inspect.",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Repository root path.",
                    },
                },
                "required": [
                    "file",
                    "symbol_name",
                    "root_path",
                ],
            },
        },
    }

    def execute(
        self,
        file: str,
        symbol_name: str,
        root_path: str,
        **kwargs: Any,
    ) -> str:
        if self.index is None:
            raise ValueError("Code index has not been initialized.")

        if self.index.root != root_path:
            raise ValueError(
                "Code index does not belong to this repository."
            )

        return read_symbol(
            index=self.index,
            root_path=root_path,
            file=file,
            symbol_name=symbol_name,
        )