from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.common import ORMBase, TimestampMixin


class GenerateRequest(BaseModel):
    beat_text: str = Field(..., min_length=1, max_length=2000)
    instruction: str = Field(default="", max_length=500)
    involved_character_ids: list[int] = Field(..., min_length=1, max_length=20)
    location_id: int | None = None
    model_task: Literal["writer_long", "writer_short"] = "writer_long"
    max_tokens: int = Field(default=4096, ge=64, le=8192)

    @field_validator("involved_character_ids")
    @classmethod
    def _dedup(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for cid in v:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out


class GenerationLogRead(ORMBase, TimestampMixin):
    id: int
    chapter_id: int
    project_id: int
    beat_text: str
    model: str | None
    status: str
    input_tokens: int
    output_tokens: int
    started_at: datetime
    finished_at: datetime | None


class GenerationLogDetail(GenerationLogRead):
    instruction: str
    involved_character_ids: list[int]
    location_id: int | None
    system_prompt: str
    user_prompt: str
    context_summary: dict
    generated_text: str | None
    model_task: str | None
    stop_reason: str | None
