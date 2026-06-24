from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class ChapterBase(BaseModel):
    order_index: int = 0
    title: str = ""
    outline: str = ""
    content: str = ""
    status: str = "draft"
    plot_line_ids: list[int] = []
    summary: str = ""
    content_hash: str = ""
    last_involved_character_ids: list[int] = []
    last_location_id: int | None = None


class ChapterCreate(ChapterBase):
    project_id: int


class ChapterUpdate(BaseModel):
    order_index: int | None = None
    title: str | None = None
    outline: str | None = None
    content: str | None = None
    status: str | None = None
    plot_line_ids: list[int] | None = None
    summary: str | None = None
    content_hash: str | None = None
    last_involved_character_ids: list[int] | None = None
    last_location_id: int | None = None


class ChapterRead(ChapterBase, ORMBase, TimestampMixin):
    id: int
    project_id: int


class ChapterListItem(BaseModel):
    """Lightweight chapter info for list views — excludes content/content_hash."""
    id: int
    project_id: int
    order_index: int
    title: str
    status: str
    summary: str
    char_count: int
    created_at: datetime
    updated_at: datetime
