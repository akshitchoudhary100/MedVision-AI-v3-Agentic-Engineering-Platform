from typing import Any
from dataclasses import dataclass
from app.tools.base import BaseTool
from app.tools.code_index import CodeIndex
from app.tools.search_code_ranked import format_for_llm, rank_files , RankedFile


@dataclass
class SearchResult:
    ranked_files: list[RankedFile]

    @property
    def paths(self) -> list[str]:
        return [item.path for item in self.ranked_files]

    def as_text(self) -> str:
        return format_for_llm(self.ranked_files)


class SearchCodeTool(BaseTool):
    name = "search_code"

    description = (
        "Search a repository and return relevance-ranked source files "
        "with reasons explaining why each file is relevant."
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
                        "query": {
                            "type": "string",
                            "description": "Keyword or concept to search for.",
                        },
                        "root_path": {
                            "type": "string",
                            "description": "Repository root path.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of ranked files to return.",
                            "default": 5,
                        },
                    },
                    "required": ["query", "root_path"],
                },
            },
        }

    def execute(
        self,
        query: str,
        root_path: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> SearchResult:

        if not query.strip():
            raise ValueError("Search query cannot be empty.")

        if self.index is None or self.index.root != root_path:
            raise ValueError(
                "Code index is not initialized for this repository."
            )

        ranked = rank_files(
            index=self.index,
            query=query,
            root_path=root_path,
            top_k=top_k,
        )

        if not ranked:
           return SearchResult(ranked_files=[])

        return SearchResult(ranked_files=ranked)