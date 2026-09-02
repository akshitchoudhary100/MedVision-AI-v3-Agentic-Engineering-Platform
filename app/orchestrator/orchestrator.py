from app.agents.base import BaseAgent
from app.schemas.result import AgentResult
from app.schemas.state import AgentState
from app.schemas.task import AgentType


class Orchestrator:
    """Coordinates tasks with the appropriate agent."""

    def __init__(self, agents: dict[AgentType, BaseAgent]) -> None:
        self.agents = agents

    def run(self, state: AgentState) -> AgentResult:
        agent_type = state.task.agent_type

        if agent_type not in self.agents:
            raise ValueError(
                f"No agent registered for type: {agent_type}"
            )

        agent = self.agents[agent_type]

        return agent.run(state)