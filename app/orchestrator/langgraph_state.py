from __future__ import annotations

from typing import Any, Literal, TypedDict


WorkflowStatus = Literal[
    "running",
    "pending_review",
    "approved",
    "completed",
    "rejected",
    "failed",
]


class InvestigationGraphState(TypedDict, total=False):
    """Serializable state shared by nodes in the V3 investigation graph.

    Keep this state JSON-friendly so it can later be persisted by the
    PostgreSQL LangGraph checkpointer. Runtime objects such as the LLM,
    registry, and database sessions do not belong in graph state.
    """

    run_id: str
    query: str
    repo_path: str
    status: WorkflowStatus
    attempt: int
    max_revisions: int
    review_decision: Literal["approve", "reject"] | None
    review_feedback: str
    summary: str
    findings: list[str]
    evidence: list[str]
    errors: list[str]
    tool_calls: list[str]
    result: dict[str, Any]
