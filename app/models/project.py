from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class ProjectBase(BaseModel):
    title: str
    genre: str = ""
    premise: str = ""
    main_theme: str = ""
    tone: str = ""


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    premise: str | None = None
    main_theme: str | None = None
    tone: str | None = None


class ProjectRead(ProjectBase, ORMBase, TimestampMixin):
    id: int
