from app.agents.investigation_agent import InvestigationAgent
from app.orchestrator.orchestrator import Orchestrator
from app.policies.investigation_policy import create_investigation_policy
from app.schemas.state import AgentState
from app.schemas.task import AgentTask, AgentType
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"


def main() -> None:
    task = AgentTask(
        description="redis",
        agent_type=AgentType.INVESTIGATION,
        metadata={
            "repo_path": V2_REPO,
        },
    )

    state = AgentState(task=task)

    registry = ToolRegistry()

    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(GitLogTool())

    policy = create_investigation_policy()

    investigation_agent = InvestigationAgent(
        tools=registry,
        policy=policy,
    )

    orchestrator = Orchestrator(
        agents={
            AgentType.INVESTIGATION: investigation_agent,
        }
    )

    result = orchestrator.run(state)

    print("\n=== INVESTIGATION RESULT ===")
    print(f"Success: {result.success}")
    print(f"Summary: {result.summary}")

    print("\n=== FINDINGS ===")
    for finding in result.findings:
        print(f"- {finding}")

    print("\n=== EVIDENCE ===")
    for evidence in result.evidence:
        print(evidence)


if __name__ == "__main__":
    main()