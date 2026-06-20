from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.memory.schema import (
    Chapter,
    Character,
    LoreEntry,
    Project,
    WorldOverview,
)


@dataclass
class CharacterStateSnapshot:
    """M2a simplified: uses character.current_state. M3 will populate change_summary."""
    current_state: str
    change_summary: str = ""


@dataclass
class RelationshipView:
    from_char_id: int
    to_char_id: int
    from_name: str
    to_name: str
    type: str
    strength: float
    description: str


@dataclass
class ChapterSummary:
    chapter_id: int
    order_index: int
    title: str
    summary: str


@dataclass
class ContextBundle:
    project: Project
    world_overview: WorldOverview | None
    characters: list[Character]
    character_states: dict[int, CharacterStateSnapshot]
    relationships: list[RelationshipView]
    lore_entries: list[LoreEntry]
    faction_lore: list[LoreEntry]
    location_lore: list[LoreEntry]
    plot_lines: list[Any]  # M3 will replace with list[PlotLine]
    recent_chapter_summaries: list[ChapterSummary]
    retrieved_chunks: list[Any] = field(default_factory=list)  # M3b: list[RetrievedChunk]


def _fetch_location_with_ancestors(
    db: Session, location_id: int, project_id: int
) -> list[LoreEntry]:
    """Fetch location and all ancestors up the parent_id chain. Filtered to project.
    Raises InvalidContextError if the location doesn't exist or doesn't belong to project.
    """
    chain: list[LoreEntry] = []
    current_id: int | None = location_id
    seen: set[int] = set()
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        loc = db.scalar(
            select(LoreEntry).where(
                LoreEntry.id == current_id,
                LoreEntry.project_id == project_id,
                LoreEntry.type == "location",
            )
        )
        if loc is None:
            raise InvalidContextError(invalid_location_id=location_id)
        chain.append(loc)
        current_id = loc.parent_id
    # Return root-first (ancestors first, target last)
    return list(reversed(chain))


def assemble_context(
    db: Session,
    *,
    chapter_id: int,
    beat_text: str,
    involved_character_ids: list[int],
    location_id: int | None = None,
    recent_chapters: int = 2,
) -> ContextBundle:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)
    project_id = chapter.project_id

    project = db.get(Project, project_id)
    world_overview = db.scalar(
        select(WorldOverview).where(WorldOverview.project_id == project_id)
    )

    # Strict project_id filter on characters
    requested_ids = list(involved_character_ids)
    characters = list(db.scalars(
        select(Character).where(
            Character.id.in_(requested_ids),
            Character.project_id == project_id,
        )
    )) if requested_ids else []
    found_ids = {c.id for c in characters}
    invalid_char_ids = sorted(set(requested_ids) - found_ids)

    invalid_loc_id: int | None = None
    location_lore: list[LoreEntry] = []
    if location_id is not None:
        try:
            location_lore = _fetch_location_with_ancestors(db, location_id, project_id)
        except InvalidContextError:
            invalid_loc_id = location_id

    if invalid_char_ids or invalid_loc_id is not None:
        raise InvalidContextError(
            invalid_character_ids=invalid_char_ids,
            invalid_location_id=invalid_loc_id,
        )

    # Faction lore from character affiliations
    faction_ids = {fid for c in characters for fid in (c.affiliations or [])}
    faction_lore = list(db.scalars(
        select(LoreEntry).where(
            LoreEntry.id.in_(faction_ids),
            LoreEntry.type == "faction",
            LoreEntry.project_id == project_id,
        )
    )) if faction_ids else []

    # Recent chapter summaries (skip current; skip empty)
    recent = list(db.scalars(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.id != chapter_id,
        ).order_by(Chapter.order_index.desc(), Chapter.id.desc()).limit(recent_chapters)
    ))
    recent_chapter_summaries = [
        ChapterSummary(c.id, c.order_index, c.title, c.summary)
        for c in sorted(recent, key=lambda c: (c.order_index, c.id))
        if c.summary
    ]

    return ContextBundle(
        project=project,
        world_overview=world_overview,
        characters=characters,
        character_states={
            c.id: CharacterStateSnapshot(current_state=c.current_state)
            for c in characters
        },
        relationships=[],  # M3 fills in
        lore_entries=list(location_lore) + list(faction_lore),
        faction_lore=faction_lore,
        location_lore=location_lore,
        plot_lines=[],  # M3 fills in
        recent_chapter_summaries=recent_chapter_summaries,
    )
