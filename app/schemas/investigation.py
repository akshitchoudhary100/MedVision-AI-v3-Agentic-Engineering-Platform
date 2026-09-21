from pydantic import BaseModel, Field


class InvestigationReport(BaseModel):
    """Structured findings produced by an investigation."""

    question: str
    summary: str
    findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)