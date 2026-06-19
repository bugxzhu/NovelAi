from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class PendingUpdateRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    chapter_id: int
    update_type: str
    operation: str  # 'create' | 'update'
    target_table: str
    target_id: int | None
    reason: str
    status: str
    # Derived summary fields (extracted from proposed_change in API layer)
    entity_name: str
    entity_type: str
    field_name: str
    old_value: str
    proposed_value: str


class PendingUpdateDetail(PendingUpdateRead):
    proposed_change: dict
    decision_note: str
    decided_at: datetime | None
    extractor_model: str | None
    extractor_log_id: int | None
    chapter_title: str
    target_entity_name: str | None


# Alias — accept/reject endpoints return the same shape as Read
AcceptRejectResponse = PendingUpdateRead


class FinalizeResponse(BaseModel):
    chapter_id: int
    summary: str
    pending_created: int
    log_id: int


class RejectBody(BaseModel):
    note: str = ""
