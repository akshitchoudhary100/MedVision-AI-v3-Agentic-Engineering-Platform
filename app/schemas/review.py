from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class ReviewRequest(BaseModel):
    task_id: UUID
    decision: ReviewDecision
    reviewer: str
    comment: str = ""