from __future__ import annotations

from pathlib import Path

from app.llm.ollama_llm import OllamaLLM
from app.orchestrator.langgraph_agent_loop import run_agent_loop
from app.policies.investigation_policy import create_investigation_policy
from app.schemas.result import AgentResult
from app.schemas.state import AgentState, AgentStatus, WorkflowState
from app.schemas.task import AgentTask, AgentType
from app.tools.code_index import build_index
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.read_symbol_tool import ReadSymbolTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


def run_langgraph_investigation(
    prompt: str,
    repo_path: str,
) -> tuple[AgentResult, AgentState]:
    """Run a real per-step LangGraph agent loop with the existing Ollama/tools/policy."""
    repo_path = str(Path(repo_path).expanduser().resolve())
    task = AgentTask(
        description=prompt,
        agent_type=AgentType.INVESTIGATION,
        metadata={"repo_path": repo_path},
    )
    agent_state = AgentState(task=task)

    try:
        index = build_index(repo_path)
        registry = ToolRegistry()
        registry.register(SearchCodeTool(index=index))
        registry.register(ReadSymbolTool(index=index))
        registry.register(ReadFileTool())
        registry.register(GitLogTool())

        policy = create_investigation_policy()
        # Keep the Phase 3 provider interface and chosen model unchanged.
        llm = OllamaLLM(model="granite4:3b")

        loop_state = run_agent_loop(
            query=prompt,
            repo_path=repo_path,
            llm=llm,
            tools=registry,
            policy=policy,
            max_steps=12,
        )

        agent_state.current_step = f"langgraph_reason_step_{loop_state.get('step_count', 0)}"
        agent_state.tool_calls = list(loop_state.get("tool_calls", []))
        agent_state.observations = [
            str(message.get("content", ""))
            for message in loop_state.get("messages", [])
            if message.get("role") == "tool"
        ]
        agent_state.findings = list(loop_state.get("findings", []))
        agent_state.errors = list(loop_state.get("errors", []))

        if loop_state.get("status") == "completed":
            agent_state.status = AgentStatus.COMPLETED
            agent_state.workflow_state = WorkflowState.COMPLETED
            result = AgentResult(
                task_id=task.task_id,
                success=True,
                summary=str(loop_state.get("summary", "")),
                findings=list(loop_state.get("findings", [])),
                evidence=list(loop_state.get("evidence", [])),
                errors=list(loop_state.get("errors", [])),
            )
        else:
            agent_state.status = AgentStatus.FAILED
            result = AgentResult(
                task_id=task.task_id,
                success=False,
                summary=str(loop_state.get("summary", "")),
                findings=list(loop_state.get("findings", [])),
                evidence=list(loop_state.get("evidence", [])),
                errors=list(loop_state.get("errors", [])) or [
                    "LangGraph investigation loop did not complete successfully."
                ],
            )
        return result, agent_state
    except Exception as exc:
        agent_state.status = AgentStatus.FAILED
        agent_state.errors.append(f"LangGraph investigation setup failed: {exc}")
        return AgentResult(task_id=task.task_id, success=False, errors=list(agent_state.errors)), agent_state
