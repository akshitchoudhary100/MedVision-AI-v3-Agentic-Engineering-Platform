import subprocess
from typing import Any

from app.tools.base import BaseTool


class GitLogTool(BaseTool):
    """Read Git commit history from a repository."""

    name = "git_log"
    description = "Read recent Git commit history from a repository."

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the Git repository.",
                        },
                        "max_commits": {
                            "type": "integer",
                            "description": "Maximum number of commits to return.",
                        },
                    },
                    "required": ["repo_path"],
                },
            },
        }

    def execute(
        self,
        repo_path: str,
        max_commits: int = 10,
        **kwargs: Any,
    ) -> list[str]:

        if max_commits <= 0:
            raise ValueError("max_commits must be greater than zero")

        result = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "log",
                f"-{max_commits}",
                "--oneline",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.splitlines()