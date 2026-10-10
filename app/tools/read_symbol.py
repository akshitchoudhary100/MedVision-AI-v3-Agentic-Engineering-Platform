"""
Targeted reading: return one function/class's source, not the whole file.

Two effects:
  1. Keeps the LLM's context focused on the relevant code, not an entire
     file it has to re-skim for the one part that matters.
  2. Gives the evidence validator a precise, checkable claim. "I read
     function get_cached_prediction" is now verifiable against the same
     AST index used for retrieval -- this is what closes the symbol-level
     grounding gap documented in ADR-005, rather than just mitigating it
     with a prompt instruction.
"""

from pathlib import Path

from app.tools.code_index import CodeIndex


def read_symbol(index: CodeIndex, root_path: str, file: str, symbol_name: str) -> str:
    locations = index.symbol_table.get(symbol_name, [])
    match = next((loc for loc in locations if loc.file == file), None)

    if match is None:
        other_files = index.symbol_defining_file(symbol_name)
        hint = f" It IS defined in: {other_files}." if other_files else " It was not found anywhere in the index."
        raise ValueError(
            f"Symbol '{symbol_name}' was not found in '{file}'.{hint} "
            "Call search_code again or read_symbol on the correct file."
        )

    lines = Path(root_path, file).read_text(encoding="utf-8").splitlines()
    snippet = "\n".join(lines[match.start_line - 1 : match.end_line])

    return f"# {file}:{match.start_line}-{match.end_line} ({match.kind} {symbol_name})\n{snippet}"


def validate_symbol_claim(index: CodeIndex, symbol_name: str, files_actually_inspected: set[str]) -> bool:
    """
    For the evidence validator: was `symbol_name` actually grounded, either
    via read_symbol on its defining file, or via a full read_file on that
    same file? Returns False if the symbol's defining file was never touched.
    """
    defining_files = set(index.symbol_defining_file(symbol_name))
    if not defining_files:
        return True  # unknown symbol (e.g. a stdlib/third-party call) -- not our repo's problem to ground
    return bool(defining_files & files_actually_inspected)