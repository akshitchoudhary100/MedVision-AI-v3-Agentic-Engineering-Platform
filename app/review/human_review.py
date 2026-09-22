from app.schemas.review import ReviewDecision, ReviewRequest
from app.schemas.result import AgentResult
from app.schemas.state import AgentState, AgentStatus, WorkflowState


class HumanReviewGate:
    """Controls workflow transitions based on human review."""

    def review(
        self,
        state: AgentState,
        result: AgentResult,
        request: ReviewRequest,
    ) -> AgentState:

        if request.task_id != state.task.task_id:
            raise ValueError("Review task does not match agent task.")

        if request.decision == ReviewDecision.APPROVE:
            state.status = AgentStatus.COMPLETED
            state.workflow_state = WorkflowState.APPROVED

        elif request.decision == ReviewDecision.REJECT:
            state.status = AgentStatus.COMPLETED
            state.workflow_state = WorkflowState.REJECTED

        elif request.decision == ReviewDecision.REQUEST_CHANGES:
            state.status = AgentStatus.WAITING
            state.workflow_state = WorkflowState.WAITING_FOR_REVIEW

        return state