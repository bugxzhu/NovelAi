from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class EventRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    chapter_id: int
    chapter_title: str          # JOIN chapters.title
    chapter_order: int          # JOIN chapters.order_index
    title: str
    description: str
    involved_characters: list[int]       # [character.id, ...]
    involved_character_names: list[str]  # JOIN-derived, UI-friendly
    location_id: int | None
    location_name: str          # JOIN-derived if location_id set, else ""
    plot_line_id: int | None    # always None in M3c-C
    foreshadows: list[int]      # [event.id, ...] this event foreshadows
    payoff_of: list[int]        # derived: [event.id, ...] that foreshadow this event
    payoff_of_titles: list[str] # derived, UI-friendly (parallel to payoff_of)
    is_unpaid: bool             # derived: True iff this event's foreshadows include at
                                # least one target with no external payoff (matches the
                                # ?filter=unpaid semantic so the UI doesn't re-derive)
    extractor_log_id: int | None
    pending_update_id: int | None


class EventCreate(BaseModel):
    project_id: int
    chapter_id: int
    title: str
    description: str
    involved_characters: list[int] = []
    location_id: int | None = None
    plot_line_id: int | None = None
    foreshadows: list[int] = []


class EventUpdate(BaseModel):
    # Only these fields are mutable. chapter_id / project_id are NOT
    # (event归属固定).
    title: str | None = None
    description: str | None = None
    involved_characters: list[int] | None = None
    location_id: int | None = None
    plot_line_id: int | None = None
    foreshadows: list[int] | None = None
