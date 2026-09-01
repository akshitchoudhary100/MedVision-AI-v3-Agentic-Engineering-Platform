from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    INVESTIGATION = "investigation"
    CODING = "coding"
    TESTING = "testing"
    PERFORMANCE = "performance"


class AgentTask(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    description: str = Field(min_length=1)
    agent_type: AgentType
    metadata: dict[str, str] = Field(default_factory=dict)