from pathlib import Path
from typing import Any

from app.tools.base import BaseTool


class SearchCodeTool(BaseTool):
    """Search source files while ignoring generated directories."""

    IGNORED_DIRECTORIES = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
    }

    name = "search_code"
    description = "Search source files for a text pattern."

    def execute(
        self,
        root_path: str,
        query: str,
        **kwargs: Any,
    ) -> list[str]:
        root = Path(root_path)

        if not root.is_dir():
            raise NotADirectoryError(
                f"Directory not found: {root_path}"
            )

        matches: list[str] = []

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            if any(
                part in self.IGNORED_DIRECTORIES
                for part in file_path.parts
            ):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            if query.lower() in content.lower():
                matches.append(str(file_path))

        return matches