from typing import Literal

from pydantic import BaseModel


Severity = Literal["error", "warn", "info"]
Category = Literal["character", "relationship", "plot", "foreshadow", "worldview"]


class Issue(BaseModel):
    severity: Severity
    category: Category
    location: str          # verbatim quote 10-50 chars, or "" if whole-chapter issue
    description: str
    suggestion: str


class ReviewResponse(BaseModel):
    chapter_id: int
    issues: list[Issue]
    log_id: int            # generation_logs id (audit)
