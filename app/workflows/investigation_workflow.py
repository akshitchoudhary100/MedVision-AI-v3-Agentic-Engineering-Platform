from app.agents.tool_calling_agent import ToolCallingAgent
from app.orchestrator.orchestrator import Orchestrator
from app.llm.ollama_llm import OllamaLLM
from app.policies.investigation_policy import create_investigation_policy
from app.schemas.result import AgentResult
from app.schemas.state import AgentState
from app.schemas.task import AgentTask, AgentType
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


def run_investigation(
    prompt: str,
    repo_path: str,
) -> tuple[AgentResult, AgentState]:

    registry = ToolRegistry()

    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(GitLogTool())

    policy = create_investigation_policy()

    llm = OllamaLLM(
        model="granite4:3b"
    )

    investigation_agent = ToolCallingAgent(
        llm=llm,
        tools=registry,
        policy=policy,
        max_steps=5,
    )

    orchestrator = Orchestrator(
        agents={
            AgentType.INVESTIGATION: investigation_agent
        }
    )

    task = AgentTask(
        description=prompt,
        agent_type=AgentType.INVESTIGATION,
        metadata={
            "repo_path": repo_path
        },
    )

    state = AgentState(
        task=task
    )

    result = orchestrator.run(state)

    return result, state