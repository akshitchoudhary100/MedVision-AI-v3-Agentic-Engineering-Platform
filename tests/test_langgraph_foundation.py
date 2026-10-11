from __future__ import annotations

from collections import Counter

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.orchestrator.langgraph_graph import build_investigation_graph
from app.schemas.result import AgentResult
from app.schemas.state import AgentState
from app.schemas.task import AgentTask, AgentType


def fake_investigator_factory(outcomes=None):
    outcomes = list(outcomes or [])
    calls = Counter()

    def investigator(query: str, repo_path: str):
        calls["count"] += 1
        if outcomes:
            success, summary = outcomes.pop(0)
        else:
            success, summary = True, f"Investigated: {query}"

        task = AgentTask(
            description=query,
            agent_type=AgentType.INVESTIGATION,
            metadata={"repo_path": repo_path},
        )
        agent_state = AgentState(task=task, tool_calls=["search_code", "read_file"])
        result = AgentResult(
            task_id=task.task_id,
            success=success,
            summary=summary,
            findings=["Finding grounded in inspected source"],
            evidence=["app/config.py", "app/cache.py"] if success else [],
            errors=[] if success else ["simulated failure"],
        )
        return result, agent_state

    return investigator, calls


def initial_state():
    return {
        "run_id": "run-test-1",
        "query": "Investigate cache behavior",
        "repo_path": "/safe/repo",
        "status": "running",
        "attempt": 0,
        "max_revisions": 2,
        "review_decision": None,
        "review_feedback": "",
        "summary": "",
        "findings": [],
        "evidence": [],
        "errors": [],
        "tool_calls": [],
        "result": {},
    }


def test_success_pauses_for_review_then_approves():
    investigator, calls = fake_investigator_factory()
    graph = build_investigation_graph(
        checkpointer=InMemorySaver(),
        investigator=investigator,
    )
    config = {"configurable": {"thread_id": "run-test-1"}}

    paused = graph.invoke(initial_state(), config=config)
    assert paused["status"] == "pending_review"
    assert paused["summary"].startswith("Investigated:")
    assert "__interrupt__" in paused

    completed = graph.invoke(
        Command(resume={"decision": "approve", "feedback": ""}),
        config=config,
    )
    assert completed["status"] == "completed"
    assert completed["review_decision"] == "approve"
    assert calls["count"] == 1


def test_rejection_reinvestigates_with_feedback_then_can_approve():
    investigator, calls = fake_investigator_factory()
    graph = build_investigation_graph(
        checkpointer=InMemorySaver(),
        investigator=investigator,
    )
    config = {"configurable": {"thread_id": "run-test-revise"}}

    first_pause = graph.invoke(initial_state(), config=config)
    assert "__interrupt__" in first_pause

    second_pause = graph.invoke(
        Command(resume={
            "decision": "reject",
            "feedback": "Inspect the cache TTL configuration explicitly.",
        }),
        config=config,
    )
    assert calls["count"] == 2
    assert second_pause["status"] == "pending_review"
    assert "__interrupt__" in second_pause

    completed = graph.invoke(
        Command(resume={"decision": "approve", "feedback": ""}),
        config=config,
    )
    assert completed["status"] == "completed"
    assert calls["count"] == 2


def test_failed_investigation_does_not_interrupt_for_review():
    investigator, _ = fake_investigator_factory([(False, "Could not investigate")])
    graph = build_investigation_graph(
        checkpointer=InMemorySaver(),
        investigator=investigator,
    )
    output = graph.invoke(initial_state(), config={"configurable": {"thread_id": "run-failed"}})
    assert output["status"] == "failed"
    assert "__interrupt__" not in output


def test_rejection_requires_feedback_helper():
    from app.orchestrator.langgraph_graph import resume_review

    with pytest.raises(ValueError, match="feedback is required"):
        resume_review("reject", "")
    assert resume_review("approve").resume == {"decision": "approve", "feedback": ""}
