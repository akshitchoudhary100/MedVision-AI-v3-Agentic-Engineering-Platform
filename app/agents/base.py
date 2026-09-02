from abc import ABC, abstractmethod

from app.schemas.result import AgentResult
from app.schemas.state import AgentState, AgentStatus


class BaseAgent(ABC):
    """Base contract and lifecycle for all V3 agents."""

    def run(self, state: AgentState) -> AgentResult:
        state.status = AgentStatus.RUNNING

        try:
            result = self._execute(state)

            state.status = AgentStatus.COMPLETED

            return result

        except Exception as exc:
            state.status = AgentStatus.FAILED
            state.errors.append(str(exc))

            return AgentResult(
                task_id=state.task.task_id,
                success=False,
                errors=[str(exc)],
            )

    @abstractmethod
    def _execute(self, state: AgentState) -> AgentResult:
        """Perform agent-specific work."""
        raise NotImplementedError