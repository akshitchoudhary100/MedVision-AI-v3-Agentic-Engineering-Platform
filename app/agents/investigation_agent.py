from typing import Any

from app.agents.base import BaseAgent
from app.policies.base import BasePolicy
from app.schemas.result import AgentResult
from app.schemas.state import AgentState, WorkflowState
from app.tools.registry import ToolRegistry


class InvestigationAgent(BaseAgent):
    """Investigates a repository using read-only tools."""

    def __init__(
        self,
        tools: ToolRegistry,
        policy: BasePolicy,
    ) -> None:
        self.tools = tools
        self.policy = policy

    def _execute(self, state: AgentState) -> AgentResult:
        repo_path = state.task.metadata.get("repo_path")

        if not repo_path:
            raise ValueError("repo_path is required for investigation")

        state.workflow_state = WorkflowState.INVESTIGATING

        # Step 1: Inspect Git history
        state.current_step = "Inspecting repository history"

        git_history = self._execute_tool(
            "git_log",
            repo_path=repo_path,
            max_commits=10,
        )

        state.observations.extend(git_history)
        state.tool_calls.append("git_log")

        # Step 2: Search the repository
        state.current_step = "Searching repository"

        search_results = self._execute_tool(
            "search_code",
            root_path=repo_path,
            query=state.task.description,
        )

        state.tool_calls.append("search_code")

        # Step 3: Read relevant files
        state.current_step = "Reading relevant files"

        files_to_read = search_results[:5]

        for file_path in files_to_read:
            content = self._execute_tool(
                "read_file",
                path=file_path,
            )

            state.observations.append(
                f"FILE: {file_path}\n{content}"
            )

            state.tool_calls.append("read_file")

        # Step 4: Create findings
        findings = [
            f"Found {len(search_results)} files matching the investigation query.",
            f"Retrieved {len(git_history)} recent Git commits.",
            f"Read {len(files_to_read)} relevant files.",
        ]

        state.findings.extend(findings)

        state.current_step = "Investigation completed"

        return AgentResult(
            task_id=state.task.task_id,
            success=True,
            summary="Repository investigation completed.",
            findings=findings,
            evidence=state.observations,
        )  

    def _execute_tool(self, name: str, **kwargs: Any) -> Any:
        if not self.policy.is_allowed(name):
            raise PermissionError(
                f"Tool '{name}' is not allowed by the investigation policy."
            )

        return self.tools.execute(name, **kwargs)