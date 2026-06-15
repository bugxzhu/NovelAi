from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class CharacterBase(BaseModel):
    name: str
    role: str = ""
    personality: dict = {}
    speech_style: str = ""
    background: str = ""
    motivation: str = ""
    appearance: str = ""
    current_state: str = ""
    affiliations: list[int] = []
    known_locations: list[int] = []


class CharacterCreate(CharacterBase):
    project_id: int


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    personality: dict | None = None
    speech_style: str | None = None
    background: str | None = None
    motivation: str | None = None
    appearance: str | None = None
    current_state: str | None = None
    affiliations: list[int] | None = None
    known_locations: list[int] | None = None


class CharacterRead(CharacterBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
