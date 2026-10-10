from app.agents.tool_calling_agent import ToolCallingAgent
from app.orchestrator.orchestrator import Orchestrator
from app.llm.ollama_llm import OllamaLLM
from app.policies.investigation_policy import create_investigation_policy
from app.schemas.result import AgentResult
from app.schemas.state import AgentState
from app.schemas.task import AgentTask, AgentType

from app.tools.code_index import build_index
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.read_symbol_tool import ReadSymbolTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


def run_investigation(
    prompt: str,
    repo_path: str,
) -> tuple[AgentResult, AgentState]:

    # Build repository index once per investigation
    index = build_index(repo_path)

    # Register tools
    registry = ToolRegistry()

    registry.register(SearchCodeTool(index=index))
    registry.register(ReadSymbolTool(index=index))
    registry.register(ReadFileTool())
    registry.register(GitLogTool())

    # Policy
    policy = create_investigation_policy()

    # LLM
    llm = OllamaLLM(model="granite4:3b")

    # Investigation agent
    investigation_agent = ToolCallingAgent(
        llm=llm,
        tools=registry,
        policy=policy,
        max_steps=5,
    )

    # Orchestrator
    orchestrator = Orchestrator(
        agents={
            AgentType.INVESTIGATION: investigation_agent
        }
    )

    # Task
    task = AgentTask(
        description=prompt,
        agent_type=AgentType.INVESTIGATION,
        metadata={"repo_path": repo_path},
    )

    state = AgentState(task=task)

    result = orchestrator.run(state)

    return result, state