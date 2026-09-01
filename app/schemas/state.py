from enum import Enum
from pydantic import BaseModel, Field

from app.schemas.task import AgentTask


class WorkflowState(str, Enum):
    CREATED = "created"
    INVESTIGATING = "investigating"
    WAITING_FOR_REVIEW = "waiting_for_review"
    APPROVED = "approved"
    CODING = "coding"
    TESTING = "testing"
    COMPLETED = "completed"
    REJECTED = "rejected"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"

class AgentState(BaseModel):
    task: AgentTask

    status: AgentStatus = AgentStatus.PENDING

    workflow_state: WorkflowState = WorkflowState.CREATED

    current_step: str = ""

    observations: list[str] = Field(default_factory=list)

    findings: list[str] = Field(default_factory=list)

    tool_calls: list[str] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)    