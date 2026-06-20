from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class RelationshipRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    from_char_id: int
    from_char_name: str        # JOIN characters.name
    to_char_id: int
    to_char_name: str          # JOIN characters.name
    type: str
    strength: float
    description: str
    valid_from_chapter: int
    valid_to_chapter: int | None
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None


class RelationshipHistoryItem(BaseModel):
    """One row in the relationship evolution timeline (per direction pair)."""
    version_id: int            # relationships.id
    valid_from_chapter: int
    valid_to_chapter: int | None
    type: str
    strength: float
    description: str
    change_summary: str
    created_at: datetime


class RelationshipCreate(BaseModel):
    project_id: int
    from_char_id: int
    to_char_id: int
    type: str
    strength: float = 0.0
    description: str = ""
    valid_from_chapter: int = 0  # 0 = before any chapter (initial setup)
    change_summary: str = ""


class RelationshipUpdate(BaseModel):
    # Only type/strength/description are mutable. valid_from/to_chapter,
    # from/to_char_id, project_id are NOT (would break temporal semantics).
    type: str | None = None
    strength: float | None = None
    description: str | None = None


class RelationshipSoftCloseBody(BaseModel):
    valid_to_chapter: int
