from typing import Literal

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


PlotLineType = Literal["main", "sub"]
PlotLineStatus = Literal["planned", "active", "resolved", "abandoned"]


class PlotLineRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    type: PlotLineType
    title: str
    summary: str
    description: str
    status: PlotLineStatus
    start_chapter: int | None
    end_chapter: int | None


class PlotLineCreate(BaseModel):
    project_id: int
    type: PlotLineType = "sub"
    title: str
    summary: str = ""
    description: str = ""
    status: PlotLineStatus = "planned"
    start_chapter: int | None = None
    end_chapter: int | None = None


class PlotLineUpdate(BaseModel):
    type: PlotLineType | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    status: PlotLineStatus | None = None
    start_chapter: int | None = None
    end_chapter: int | None = None
