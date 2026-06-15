from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class LoreEntryBase(BaseModel):
    type: str
    name: str
    title: str = ""
    description: str = ""
    attributes: dict = {}
    parent_id: int | None = None
    tags: list[str] = []


class LoreEntryCreate(LoreEntryBase):
    project_id: int


class LoreEntryUpdate(BaseModel):
    type: str | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None
    attributes: dict | None = None
    parent_id: int | None = None
    tags: list[str] | None = None


class LoreEntryRead(LoreEntryBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
