from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentResult(BaseModel):
    task_id: UUID
    success: bool

    summary: str = ""

    findings: list[str] = Field(default_factory=list)

    evidence: list[str] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)

    risk_level: RiskLevel = RiskLevel.LOW

    requires_human_approval: bool = True