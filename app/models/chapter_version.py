"""Pydantic models for chapter_versions endpoints.

Note: the underlying ChapterVersion SQLAlchemy model (app.memory.schema)
has only `created_at` (no `updated_at`), so we declare the timestamp
explicitly here rather than pulling in TimestampMixin.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

# Allowed snapshot reasons. Kept in sync with ChapterVersion.reason column
# (String(30)). Order of the set is not significant; we sort() for stable
# error messages.
ALLOWED_REASONS = {
    "manual",
    "pre_ai_accept",
    "pre_polish_accept",
    "pre_finalize",
    "pre_restore",
}


class ChapterVersionCreate(BaseModel):
    content: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        if v not in ALLOWED_REASONS:
            raise ValueError(
                f"reason must be one of {sorted(ALLOWED_REASONS)}, got {v!r}"
            )
        return v


class ChapterVersionRead(BaseModel):
    """Single version. `content` is None on the POST response (and gets
    dropped via response_model_exclude_none on that route) and populated
    on GET /api/chapter-versions/{id}."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    char_count: int
    reason: str
    created_at: datetime
    content: str | None = None


class ChapterVersionListItem(BaseModel):
    """List item — no content payload, includes delta vs newer neighbor."""
    id: int
    chapter_id: int
    char_count: int
    delta_char_count: int  # newer_state.char_count - this.char_count
    reason: str
    created_at: datetime


class ChapterVersionRestoreResponse(BaseModel):
    restored_version_id: int
    new_pre_restore_id: int
    new_char_count: int
    restored_content: str
