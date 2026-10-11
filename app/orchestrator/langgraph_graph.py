from __future__ import annotations

from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.orchestrator.langgraph_state import InvestigationGraphState


Investigator = Callable[[str, str], tuple[Any, Any]]


def _default_investigator(query: str, repo_path: str) -> tuple[Any, Any]:
    """Import the existing runtime lazily to avoid import-time side effects."""
    from app.workflows.investigation_workflow import run_investigation

    return run_investigation(prompt=query, repo_path=repo_path)


def _investigate(
    state: InvestigationGraphState,
    *,
    investigator: Investigator,
) -> dict[str, Any]:
    query = state["query"].strip()
    repo_path = state["repo_path"].strip()

    if not query:
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), "Investigation query cannot be empty."],
        }
    if not repo_path:
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), "A repository path is required."],
        }

    feedback = state.get("review_feedback", "").strip()
    effective_query = query
    if feedback:
        effective_query = (
            f"{query}\n\nReviewer feedback from the previous attempt:\n{feedback}\n"
            "Revise the investigation to address this feedback."
        )

    try:
        result, agent_state = investigator(effective_query, repo_path)
        result_data = (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else dict(result)
        )
        success = bool(result_data.get("success", False))
        status = "pending_review" if success else "failed"

        return {
            "status": status,
            "attempt": state.get("attempt", 0) + 1,
            "review_decision": None,
            "summary": result_data.get("summary", ""),
            "findings": list(result_data.get("findings", [])),
            "evidence": list(result_data.get("evidence", [])),
            "errors": [*state.get("errors", []), *result_data.get("errors", [])],
            "tool_calls": list(getattr(agent_state, "tool_calls", [])),
            "result": result_data,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "attempt": state.get("attempt", 0) + 1,
            "errors": [*state.get("errors", []), f"Investigation failed: {exc}"],
        }


def _route_after_investigation(
    state: InvestigationGraphState,
) -> str:
    return "human_review" if state.get("status") == "pending_review" else END


def _human_review(state: InvestigationGraphState) -> dict[str, Any]:
    """Pause durably at the review boundary; resumed with Command(resume=...)."""
    decision = interrupt(
        {
            "type": "human_review",
            "run_id": state["run_id"],
            "query": state["query"],
            "attempt": state.get("attempt", 1),
            "summary": state.get("summary", ""),
            "findings": state.get("findings", []),
            "evidence": state.get("evidence", []),
            "allowed_decisions": ["approve", "reject"],
            "reject_requires_feedback": True,
        }
    )

    if not isinstance(decision, dict):
        return {
            "status": "pending_review",
            "errors": [*state.get("errors", []), "Review decision must be an object."],
        }

    choice = decision.get("decision")
    feedback = str(decision.get("feedback", "")).strip()

    if choice == "approve":
        return {
            "review_decision": "approve",
            "review_feedback": "",
            "status": "approved",
        }

    if choice == "reject" and feedback:
        return {
            "review_decision": "reject",
            "review_feedback": feedback,
            "status": "rejected",
        }

    return {
        "review_decision": None,
        "status": "pending_review",
        "errors": [
            *state.get("errors", []),
            "A valid review decision is required; rejection must include feedback.",
        ],
    }


def _route_after_review(state: InvestigationGraphState) -> str:
    decision = state.get("review_decision")
    if decision == "approve":
        return "finalize"
    if decision == "reject":
        if state.get("attempt", 0) <= state.get("max_revisions", 2):
            return "revise"
        return "stop_after_rejections"
    return END


def _revise(state: InvestigationGraphState) -> dict[str, Any]:
    return {
        "status": "running",
        "review_decision": None,
        # Keep the feedback for the next investigation prompt.
        "errors": list(state.get("errors", [])),
    }


def _finalize(state: InvestigationGraphState) -> dict[str, Any]:
    return {"status": "completed"}


def _stop_after_rejections(state: InvestigationGraphState) -> dict[str, Any]:
    return {
        "status": "rejected",
        "errors": [
            *state.get("errors", []),
            "Maximum review/revision attempts reached.",
        ],
    }


def build_investigation_graph(
    *,
    checkpointer: Any = None,
    investigator: Investigator | None = None,
):
    """Build the Phase 4.1 graph around the existing Ollama/plain-Python runtime.

    This is an intentionally safe compatibility slice: the existing
    ToolCallingAgent still owns its internal tool loop in Phase 4.1. The next
    migration step will lift individual LLM/tool steps into graph nodes.
    """
    runner = investigator or _default_investigator

    builder = StateGraph(InvestigationGraphState)
    builder.add_node(
        "investigate",
        lambda state: _investigate(state, investigator=runner),
    )
    builder.add_node("human_review", _human_review)
    builder.add_node("revise", _revise)
    builder.add_node("finalize", _finalize)
    builder.add_node("stop_after_rejections", _stop_after_rejections)

    builder.add_edge(START, "investigate")
    builder.add_conditional_edges(
        "investigate",
        _route_after_investigation,
        {"human_review": "human_review", END: END},
    )
    builder.add_conditional_edges(
        "human_review",
        _route_after_review,
        {
            "finalize": "finalize",
            "revise": "revise",
            "stop_after_rejections": "stop_after_rejections",
            END: END,
        },
    )
    builder.add_edge("revise", "investigate")
    builder.add_edge("finalize", END)
    builder.add_edge("stop_after_rejections", END)

    # In-memory checkpointing makes the graph runnable locally. Phase 4.3 will
    # inject a PostgreSQL checkpointer for durable cross-restart execution.
    active_checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
    return builder.compile(checkpointer=active_checkpointer)


def resume_review(decision: str, feedback: str = "") -> Command:
    """Small typed helper used by the future FastAPI gate endpoint."""
    normalized = decision.strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")
    if normalized == "reject" and not feedback.strip():
        raise ValueError("feedback is required when rejecting")
    return Command(resume={"decision": normalized, "feedback": feedback.strip()})
