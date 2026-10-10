"""
Relevance-ranked code search, replacing plain keyword search.

Four signals, each explainable and deterministic:
  1. keyword match in the file path/filename        (cheap, high precision)
  2. keyword occurrence count in file content        (your existing behavior)
  3. keyword match against symbol names/docstrings   (more semantic than raw grep)
  4. import-graph proximity                          (a file connected to an
     already-relevant file is probably relevant too, even with zero keyword
     hits of its own -- this is how redis_cache.py gets surfaced even if the
     word "redis" never literally appears in it)

Returns a ranked list with scores and reasons, not a flat path list, so the
LLM has an actual signal to decide with instead of guessing from filenames.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.tools.code_index import CodeIndex

WEIGHT_PATH_MATCH = 3.0
WEIGHT_CONTENT_HIT = 0.5
WEIGHT_SYMBOL_MATCH = 2.0
IMPORT_PROPAGATION_FACTOR = 0.15
MAX_CONTENT_HITS_COUNTED = 6
TOP_K_DEFAULT = 5


@dataclass
class RankedFile:
    path: str
    score: float = 0.0
    matched_symbols: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def rank_files(index: CodeIndex, query: str, root_path: str, top_k: int = TOP_K_DEFAULT) -> list[RankedFile]:
    query_lower = query.lower()
    scores: dict[str, RankedFile] = {}

    def add_score(path: str, amount: float, reason: str) -> None:
        entry = scores.setdefault(path, RankedFile(path=path))
        entry.score += amount
        entry.reasons.append(reason)

    # Signals 1 + 2: path match, content occurrence count
    for rel_path in index.import_graph.keys():
        if query_lower in rel_path.lower():
            add_score(rel_path, WEIGHT_PATH_MATCH, "query matches filename/path")

        try:
            content = Path(root_path, rel_path).read_text(encoding="utf-8").lower()
        except Exception:
            continue

        hits = min(content.count(query_lower), MAX_CONTENT_HITS_COUNTED)
        if hits:
            add_score(rel_path, hits * WEIGHT_CONTENT_HIT, f"{hits} keyword occurrence(s) in content")

    # Signal 3: symbol name / docstring match
    for symbol_name, locations in index.symbol_table.items():
        name_match = query_lower in symbol_name.lower()
        for loc in locations:
            if name_match:
                add_score(loc.file, WEIGHT_SYMBOL_MATCH, f"symbol name matches: {symbol_name}")
                scores[loc.file].matched_symbols.append(symbol_name)
            if loc.docstring and query_lower in loc.docstring.lower():
                add_score(loc.file, WEIGHT_SYMBOL_MATCH, f"docstring of {symbol_name} matches")
                scores[loc.file].matched_symbols.append(symbol_name)

    # Signal 4: one-hop import-graph propagation from files that already scored.
    # Snapshot first so we propagate from original scores, not newly-boosted ones.
    seed_scores = {path: entry.score for path, entry in scores.items()}
    for file, base_score in seed_scores.items():
        neighbors = index.import_graph.get(file, set()) | index.reverse_import_graph.get(file, set())
        for neighbor in neighbors:
            add_score(
                neighbor,
                base_score * IMPORT_PROPAGATION_FACTOR,
                f"connected via import graph to {file}",
            )

    ranked = sorted(scores.values(), key=lambda r: r.score, reverse=True)
    return ranked[:top_k]


def format_for_llm(ranked: list[RankedFile]) -> str:
    """
    Render ranked results as evidence the LLM can reason about, instead of
    a bare path list. This is what the search_code tool observation should
    look like now.
    """
    lines = ["Ranked search results (highest relevance first):\n"]
    for i, r in enumerate(ranked, 1):
        symbols = f" | matched symbols: {', '.join(sorted(set(r.matched_symbols)))}" if r.matched_symbols else ""
        lines.append(f"{i}. {r.path}  (score: {r.score:.1f}){symbols}")
        lines.append(f"   why: {'; '.join(r.reasons[:3])}")
    return "\n".join(lines)
