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
    Relationship,
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
    milestones: list[Any] = field(default_factory=list)  # M4b-1: list[StoryMilestone]


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

    # M3c-A: relationships between involved characters (current valid only)
    char_id_set = {c.id for c in characters}
    relationships: list[RelationshipView] = []
    if len(char_id_set) >= 2:
        rels = list(db.scalars(
            select(Relationship).where(
                Relationship.project_id == project_id,
                Relationship.from_char_id.in_(char_id_set),
                Relationship.to_char_id.in_(char_id_set),
                Relationship.valid_to_chapter.is_(None),
            )
        ))
        char_by_id = {c.id: c for c in characters}
        for r in rels:
            from_c = char_by_id.get(r.from_char_id)
            to_c = char_by_id.get(r.to_char_id)
            if from_c and to_c:
                relationships.append(RelationshipView(
                    from_char_id=r.from_char_id, to_char_id=r.to_char_id,
                    from_name=from_c.name, to_name=to_c.name,
                    type=r.type, strength=r.strength, description=r.description,
                ))

    # M3c-D: inject active plot lines
    from app.memory.schema import PlotLine
    active_plot_lines = list(db.scalars(
        select(PlotLine).where(
            PlotLine.project_id == project_id,
            PlotLine.status == "active",
        )
    ))

    # M4b-1: inject ALL milestones (full story blueprint)
    from app.memory.schema import StoryMilestone
    all_milestones = list(db.scalars(
        select(StoryMilestone).where(
            StoryMilestone.project_id == project_id,
        ).order_by(StoryMilestone.order_index)
    ))

    return ContextBundle(
        project=project,
        world_overview=world_overview,
        characters=characters,
        character_states={
            c.id: CharacterStateSnapshot(current_state=c.current_state)
            for c in characters
        },
        relationships=relationships,
        lore_entries=list(location_lore) + list(faction_lore),
        faction_lore=faction_lore,
        location_lore=location_lore,
        plot_lines=active_plot_lines,
        recent_chapter_summaries=recent_chapter_summaries,
        milestones=all_milestones,
    )


@dataclass
class ReviewContextBundle:
    """Richer context for review: includes history (state/relationship/events)
    that writing doesn't need."""
    project: Project
    world_overview: WorldOverview | None
    chapter: Chapter
    characters: list[Character]
    character_states_history: dict[int, list[CharacterStateSnapshot]]
    relationships: list[RelationshipView]
    events: list[Any]  # list[EventRead]; use Any to avoid circular import
    lore_entries: list[LoreEntry]
    plot_lines: list[Any]  # M3c-D: list[PlotLine]; use Any to avoid circular import
    recent_chapter_summaries: list[ChapterSummary]
    milestones: list[Any] = field(default_factory=list)  # M4b-1: list[StoryMilestone]


def _target_has_external_payoff(
    payoff_map: dict[int, list[int]], src_id: int, target_id: int
) -> bool:
    """Target is referenced by some event OTHER than src itself.

    Mirrors app/api/events.py logic. Duplicated (not imported) to avoid
    Reviewer depending on events API internals.
    """
    return any(pid != src_id for pid in payoff_map.get(target_id, []))


def assemble_review_context(
    db: Session,
    *,
    chapter_id: int,
    state_history_limit: int = 5,
) -> ReviewContextBundle:
    """Assemble rich context for chapter review.

    Unlike assemble_context (writing-focused, minimal tokens), this pulls:
    - last N character_states per character (for arc analysis)
    - all current relationships (not just involved-pair)
    - all events with derived payoff_of + is_unpaid (for foreshadow integrity)
    - all lore entries (for worldview consistency)
    - all chapter summaries (for plot continuity)

    Raises:
        ChapterNotFoundError: chapter does not exist.
    """
    from app.memory.schema import CharacterState, Event, Relationship
    from app.models.event import EventRead

    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)
    project_id = chapter.project_id

    project = db.get(Project, project_id)
    world_overview = db.scalar(
        select(WorldOverview).where(WorldOverview.project_id == project_id)
    )

    # Resolve involved characters from chapter.last_involved_character_ids
    involved_ids = chapter.last_involved_character_ids or []
    if involved_ids:
        characters = list(db.scalars(
            select(Character).where(Character.id.in_(involved_ids))
        ))
    else:
        characters = list(db.scalars(
            select(Character).where(Character.project_id == project_id)
        ))

    # All project characters (for name resolution in relationships/events)
    all_chars = list(db.scalars(
        select(Character).where(Character.project_id == project_id)
    ))
    all_char_by_id = {c.id: c for c in all_chars}

    # Per-character state history (last N, newest first)
    char_states: dict[int, list[CharacterStateSnapshot]] = {}
    for c in characters:
        states = list(db.scalars(
            select(CharacterState)
            .where(CharacterState.character_id == c.id)
            .join(Chapter, Chapter.id == CharacterState.chapter_id)
            .order_by(Chapter.order_index.desc(), CharacterState.id.desc())
            .limit(state_history_limit)
        ))
        char_states[c.id] = [
            CharacterStateSnapshot(
                current_state=s.state_snapshot,
                change_summary=s.change_summary,
            )
            for s in states
        ]

    # All current-valid relationships in project
    relationships: list[RelationshipView] = []
    rels = list(db.scalars(
        select(Relationship).where(
            Relationship.project_id == project_id,
            Relationship.valid_to_chapter.is_(None),
        )
    ))
    for r in rels:
        from_c = all_char_by_id.get(r.from_char_id)
        to_c = all_char_by_id.get(r.to_char_id)
        if from_c and to_c:
            relationships.append(RelationshipView(
                from_char_id=r.from_char_id, to_char_id=r.to_char_id,
                from_name=from_c.name, to_name=to_c.name,
                type=r.type, strength=r.strength, description=r.description,
            ))

    # All events with derived fields
    all_events_orm = list(db.scalars(
        select(Event).where(Event.project_id == project_id)
    ))
    payoff_map: dict[int, list[int]] = {}
    event_title_by_id = {e.id: e.title for e in all_events_orm}
    for e in all_events_orm:
        for target_id in (e.foreshadows or []):
            payoff_map.setdefault(target_id, []).append(e.id)

    chapters_in_project = list(db.scalars(
        select(Chapter).where(Chapter.project_id == project_id)
    ))
    chapter_by_id = {c.id: c for c in chapters_in_project}

    events_view: list[EventRead] = []
    for e in all_events_orm:
        ch = chapter_by_id.get(e.chapter_id)
        involved_names = [
            all_char_by_id[i].name for i in (e.involved_characters or [])
            if i in all_char_by_id
        ]
        loc = db.get(LoreEntry, e.location_id) if e.location_id else None
        is_unpaid = bool(e.foreshadows) and any(
            not _target_has_external_payoff(payoff_map, e.id, tid)
            for tid in (e.foreshadows or [])
        )
        events_view.append(EventRead(
            id=e.id, project_id=e.project_id, chapter_id=e.chapter_id,
            chapter_title=ch.title if ch else "",
            chapter_order=ch.order_index if ch else 0,
            title=e.title, description=e.description,
            involved_characters=e.involved_characters or [],
            involved_character_names=involved_names,
            location_id=e.location_id,
            location_name=loc.name if loc else "",
            plot_line_id=e.plot_line_id,
            foreshadows=e.foreshadows or [],
            payoff_of=payoff_map.get(e.id, []),
            payoff_of_titles=[
                event_title_by_id.get(pid, "") for pid in payoff_map.get(e.id, [])
            ],
            is_unpaid=is_unpaid,
            extractor_log_id=e.extractor_log_id,
            pending_update_id=e.pending_update_id,
            created_at=e.created_at, updated_at=e.updated_at,
        ))

    # All lore entries
    lore_entries = list(db.scalars(
        select(LoreEntry).where(LoreEntry.project_id == project_id)
    ))

    # M3c-D: inject active plot lines
    from app.memory.schema import PlotLine
    active_plot_lines = list(db.scalars(
        select(PlotLine).where(
            PlotLine.project_id == project_id,
            PlotLine.status == "active",
        )
    ))

    # M4b-1: inject ALL milestones (full story blueprint)
    from app.memory.schema import StoryMilestone
    all_milestones = list(db.scalars(
        select(StoryMilestone).where(
            StoryMilestone.project_id == project_id,
        ).order_by(StoryMilestone.order_index)
    ))

    # All chapter summaries except current
    recent_chapter_summaries = [
        ChapterSummary(c.id, c.order_index, c.title, c.summary)
        for c in chapters_in_project
        if c.id != chapter_id and c.summary
    ]

    return ReviewContextBundle(
        project=project, world_overview=world_overview, chapter=chapter,
        characters=characters, character_states_history=char_states,
        relationships=relationships, events=events_view, lore_entries=lore_entries,
        plot_lines=active_plot_lines,
        recent_chapter_summaries=recent_chapter_summaries,
        milestones=all_milestones,
    )
