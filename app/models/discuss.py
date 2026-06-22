from pydantic import BaseModel


class DiscussBranch(BaseModel):
    label: str
    title: str
    summary: str
    conflicts: str
    opportunities: str
    character_impact: str


class DiscussRequest(BaseModel):
    question: str


class DiscussResponse(BaseModel):
    question: str
    branches: list[DiscussBranch]
    recommended: str
    reasoning: str
    log_id: int
