from pathlib import Path
from typing import Any

from app.tools.base import BaseTool


class ReadFileTool(BaseTool):
    """Read a text file from an allowed repository."""

    name = "read_file"
    description = "Read the contents of a text file."

    def execute(self, path: str, **kwargs: Any) -> str:
        file_path = Path(path)

        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        return file_path.read_text(encoding="utf-8")