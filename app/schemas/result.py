from uuid import UUID

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    task_id: UUID

    success: bool

    summary: str = ""

    findings: list[str] = Field(default_factory=list)

    evidence: list[str] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)