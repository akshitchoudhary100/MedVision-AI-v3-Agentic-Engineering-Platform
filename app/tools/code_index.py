"""
Lightweight static code index for the Investigation Agent's retrieval layer.

Builds, for a given repo root:
  - symbol_table: symbol name -> list of SymbolLocation (file, line range, docstring)
  - import_graph: file -> set of other repo files it imports (best-effort resolution)
  - reverse_import_graph: file -> set of repo files that import it

Pure AST parsing. No embeddings, no vector DB, no network calls. This is a
deterministic, explainable retrieval signal, combined with keyword matching
in search_code_ranked.py, before ever reaching for semantic search.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SymbolLocation:
    file: str
    name: str
    kind: str  # "function" | "class"
    start_line: int
    end_line: int
    docstring: str | None


@dataclass
class CodeIndex:
    root: str
    symbol_table: dict[str, list[SymbolLocation]] = field(default_factory=dict)
    import_graph: dict[str, set[str]] = field(default_factory=dict)
    reverse_import_graph: dict[str, set[str]] = field(default_factory=dict)
    file_to_module: dict[str, str] = field(default_factory=dict)
    module_to_file: dict[str, str] = field(default_factory=dict)

    def symbol_defining_file(self, symbol_name: str) -> list[str]:
        """Used by the evidence validator: where is `symbol_name` actually defined?"""
        return [loc.file for loc in self.symbol_table.get(symbol_name, [])]


def _module_name_for(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def build_index(root_path: str) -> CodeIndex:
    root = Path(root_path)
    index = CodeIndex(root=root_path)

    EXCLUDED_DIRS = {
        ".git",
        ".venv",
        "venv",
        "env",
        "ENV",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "node_modules",
        "dist",
        "build",
        "site-packages",
        ".eggs",
    }


    def _is_excluded(path: Path) -> bool:
        return any(part in EXCLUDED_DIRS for part in path.parts)


    py_files = [
        p
        for p in root.rglob("*.py")
        if not _is_excluded(p.relative_to(root))
    ]

    # Pass 1: map every file to its dotted module path, both directions.
    for path in py_files:
        rel = str(path.relative_to(root))
        module = _module_name_for(root, path)
        index.file_to_module[rel] = module
        index.module_to_file[module] = rel

    # Pass 2: parse each file for symbols + imports.
    for path in py_files:
        rel = str(path.relative_to(root))
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue

        index.import_graph.setdefault(rel, set())

        for node in ast.walk(tree):

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                loc = SymbolLocation(
                    file=rel,
                    name=node.name,
                    kind=kind,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    docstring=ast.get_docstring(node),
                )
                index.symbol_table.setdefault(node.name, []).append(loc)

            if isinstance(node, ast.ImportFrom) and node.module:
                target_file = index.module_to_file.get(node.module)
                if target_file:
                    index.import_graph[rel].add(target_file)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_file = index.module_to_file.get(alias.name)
                    if target_file:
                        index.import_graph[rel].add(target_file)

    # Pass 3: reverse graph.
    for file, targets in index.import_graph.items():
        for target in targets:
            index.reverse_import_graph.setdefault(target, set()).add(file)

    return index