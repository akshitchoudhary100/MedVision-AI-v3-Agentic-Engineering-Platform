from app.agents.tool_calling_agent import ToolCallingAgent
from app.llm.ollama_llm import OllamaLLM
from app.policies.investigation_policy import create_investigation_policy
from app.schemas.state import AgentState
from app.schemas.task import AgentTask, AgentType
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool
from app.tools.read_file import ReadFileTool
from app.tools.git_log import GitLogTool
from app.tools.read_symbol_tool import ReadSymbolTool
from app.tools.code_index import build_index

V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"


def main() -> None:

    # Build code index once for the repository.
    index = build_index(V2_REPO)

    # Create tool registry.
    tools = ToolRegistry()

    tools.register(
        SearchCodeTool(index=index)
    )

    tools.register(
        ReadFileTool()
    )

    tools.register(
        GitLogTool()
    )

    tools.register(
        ReadSymbolTool(index=index)
    )

    # LLM
    llm = OllamaLLM(
        model="granite4:3b"
    )

    # Policy
    policy = create_investigation_policy()

    # Agent
    agent = ToolCallingAgent(
        llm=llm,
        tools=tools,
        policy=policy,
        max_steps=10,
    )

    # Task
    task = AgentTask(
        description="Investigate how Redis caching works in the inference system.",
        agent_type=AgentType.INVESTIGATION,
        metadata={
            "repo_path": V2_REPO,
        },
    )

    state = AgentState(
        task=task
    )

    # Run agent
    result = agent.run(state)

    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)

    print(result)


if __name__ == "__main__":
    main()