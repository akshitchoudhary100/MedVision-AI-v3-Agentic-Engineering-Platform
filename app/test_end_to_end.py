from app.agents.tool_calling_agent import ToolCallingAgent
from app.review.human_review import HumanReviewGate
from app.orchestrator.orchestrator import Orchestrator

from app.llm.ollama_llm import OllamaLLM

from app.policies.investigation_policy import (
    create_investigation_policy,
)

from app.schemas.review import (
    ReviewDecision,
    ReviewRequest,
)

from app.schemas.state import (
    AgentState,
)

from app.schemas.task import (
    AgentTask,
    AgentType,
)

from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


V2_REPO = (
    "/Users/akshitchoudhary/"
    "MedVision-AI-v2.0-Production-AI-Inference-Platform"
)


def main() -> None:

    # ============================================================
    # 1. TOOL REGISTRY
    # ============================================================

    registry = ToolRegistry()

    registry.register(
        ReadFileTool()
    )

    registry.register(
        SearchCodeTool()
    )

    registry.register(
        GitLogTool()
    )

    # ============================================================
    # 2. POLICY
    # ============================================================

    policy = create_investigation_policy()

    # ============================================================
    # 3. LOCAL LLM
    # ============================================================

    llm = OllamaLLM(
        model="granite4:3b"
    )

    # ============================================================
    # 4. TOOL-CALLING INVESTIGATION AGENT
    # ============================================================

    investigation_agent = ToolCallingAgent(
        llm=llm,
        tools=registry,
        policy=policy,
        max_steps=5,
    )

    # ============================================================
    # 5. ORCHESTRATOR
    # ============================================================

    orchestrator = Orchestrator(
        agents={
            AgentType.INVESTIGATION:
                investigation_agent
        }
    )

    # ============================================================
    # 6. TASK
    # ============================================================

    task = AgentTask(
        description=(
            "Investigate how Redis is used "
            "in the repository."
        ),
        agent_type=AgentType.INVESTIGATION,
        metadata={
            "repo_path": V2_REPO,
        },
    )

    # ============================================================
    # 7. AGENT STATE
    # ============================================================

    state = AgentState(
        task=task
    )

    # ============================================================
    # 8. RUN ORCHESTRATOR
    # ============================================================

    print("\n")
    print("=" * 70)
    print("RUNNING ORCHESTRATOR")
    print("=" * 70)

    result = orchestrator.run(
        state
    )

    # ============================================================
    # 9. DISPLAY AGENT RESULT
    # ============================================================

    print("\n")
    print("=" * 70)
    print("AGENT RESULT")
    print("=" * 70)

    print("\nSuccess:")
    print(result.success)

    print("\nSummary:")
    print(result.summary)

    print("\nFindings:")
    for finding in result.findings:
        print(finding)

    print("\nEvidence:")
    for evidence in result.evidence:
        print(f"  - {evidence}")

    print("\nRisk Level:")
    print(result.risk_level)

    print("\nHuman Approval Required:")
    print(result.requires_human_approval)

    print("\nWorkflow State:")
    print(state.workflow_state)

    print("\nAgent Status:")
    print(state.status)

    # ============================================================
    # 10. HUMAN REVIEW
    # ============================================================

    if (
        result.success
        and result.requires_human_approval
    ):

        print("\n")
        print("=" * 70)
        print("HUMAN REVIEW")
        print("=" * 70)

        print("\nEvidence presented to reviewer:")

        for evidence in result.evidence:
            print(f"  - {evidence}")

        review_gate = HumanReviewGate()

        review_request = ReviewRequest(
            task_id=task.task_id,
            decision=ReviewDecision.APPROVE,
            reviewer="human",
            comment=(
                "Reviewed findings and evidence."
            ),
        )

        state = review_gate.review(
            state=state,
            result=result,
            request=review_request,
        )

    # ============================================================
    # 11. FINAL WORKFLOW STATE
    # ============================================================

    print("\n")
    print("=" * 70)
    print("FINAL WORKFLOW STATE")
    print("=" * 70)

    print(
        f"\nStatus: {state.status}"
    )

    print(
        f"Workflow: {state.workflow_state}"
    )

    print(
        f"Current Step: {state.current_step}"
    )


if __name__ == "__main__":
    main()