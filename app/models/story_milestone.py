from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class StoryMilestoneRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    order_index: int
    type: str
    title: str
    description: str
    chapter_start: int | None
    chapter_end: int | None
    status: str


class StoryMilestoneCreate(BaseModel):
    project_id: int
    order_index: int = 0
    type: str = "里程碑"
    title: str
    description: str = ""
    chapter_start: int | None = None
    chapter_end: int | None = None
    status: str = "planned"


class StoryMilestoneUpdate(BaseModel):
    order_index: int | None = None
    type: str | None = None
    title: str | None = None
    description: str | None = None
    chapter_start: int | None = None
    chapter_end: int | None = None
    status: str | None = None
