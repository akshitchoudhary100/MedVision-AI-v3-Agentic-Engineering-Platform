"""PostgreSQL-persisted entry points for the LangGraph investigation workflow.

This adapter deliberately does not change the FastAPI/SSE contract. It can be
used by tests or a later API integration phase. Every invocation for the same
run must use the same run_id/thread_id to resume its saved checkpoint.
"""
from __future__ import annotations

from typing import Any

from langgraph.types import Command

from app.orchestrator.postgres_checkpointer import postgres_checkpointer
from app.orchestrator.langgraph_graph import build_investigation_graph, resume_review


def _config(run_id: str) -> dict[str, Any]:
    if not run_id or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    return {"configurable": {"thread_id": run_id}}


def invoke_persistent_investigation(
    *,
    run_id: str,
    query: str,
    repo_path: str,
    database_url: str | None = None,
    max_revisions: int = 2,
    investigator=None,
) -> dict[str, Any]:
    """Start an investigation and persist graph checkpoints to PostgreSQL."""
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not repo_path or not repo_path.strip():
        raise ValueError("repo_path must be a non-empty string")

    initial_state = {
        "run_id": run_id,
        "query": query,
        "repo_path": repo_path,
        "status": "running",
        "attempt": 0,
        "max_revisions": max_revisions,
        "review_decision": None,
        "review_feedback": None,
        "summary": "",
        "findings": [],
        "evidence": [],
        "errors": [],
        "tool_calls": [],
        "result": {},
    }
    with postgres_checkpointer(database_url) as saver:
        graph = build_investigation_graph(checkpointer=saver, investigator=investigator)
        return graph.invoke(initial_state, config=_config(run_id))


def resume_persistent_review(
    *,
    run_id: str,
    decision: str,
    feedback: str = "",
    database_url: str | None = None,
    investigator=None,
) -> dict[str, Any]:
    """Resume an interrupted human-review workflow using its original run_id."""
    with postgres_checkpointer(database_url) as saver:
        graph = build_investigation_graph(checkpointer=saver, investigator=investigator)
        command: Command = resume_review(decision, feedback)
        return graph.invoke(command, config=_config(run_id))
