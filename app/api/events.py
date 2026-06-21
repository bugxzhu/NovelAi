"""M3c-C: /api/events — CRUD + filter + cascade cleanup."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import (
    Chapter,
    Character,
    Event,
    LoreEntry,
)
from app.models.event import EventCreate, EventRead, EventUpdate

router = APIRouter()


def _validate_involved_characters(db: Session, ids: list[int]) -> None:
    if not ids:
        return
    found = set(db.scalars(select(Character.id).where(Character.id.in_(ids))))
    missing = set(ids) - found
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"unknown character ids: {sorted(missing)}",
        )


def _validate_location(db: Session, location_id: int | None) -> None:
    if location_id is None:
        return
    loc = db.get(LoreEntry, location_id)
    if loc is None:
        raise HTTPException(status_code=422, detail=f"location {location_id} not found")
    if loc.type != "location":
        raise HTTPException(
            status_code=422,
            detail=f"lore {location_id} is not a location (type={loc.type})",
        )


def _validate_foreshadows(
    db: Session, project_id: int, foreshadows: list[int], self_id: int | None = None,
) -> None:
    if not foreshadows:
        return
    if self_id is not None and self_id in foreshadows:
        raise HTTPException(status_code=422, detail="event cannot foreshadow itself")
    found = set(db.scalars(
        select(Event.id).where(
            Event.project_id == project_id,
            Event.id.in_(foreshadows),
        )
    ))
    missing = set(foreshadows) - found
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"unknown event ids in foreshadows: {sorted(missing)}",
        )


def _build_response(
    db: Session,
    e: Event,
    char_by_id: dict[int, Character],
    loc_by_id: dict[int, LoreEntry],
    chapter_by_id: dict[int, Chapter],
    payoff_map: dict[int, list[int]] | None = None,
    event_title_by_id: dict[int, str] | None = None,
) -> EventRead:
    ch = chapter_by_id.get(e.chapter_id)
    involved_names = [char_by_id[i].name for i in (e.involved_characters or [])
                      if i in char_by_id]
    loc = loc_by_id.get(e.location_id) if e.location_id is not None else None

    if payoff_map is not None and event_title_by_id is not None:
        payoff_ids = payoff_map.get(e.id, [])
        payoff_titles = [event_title_by_id.get(pid, "") for pid in payoff_ids]
    else:
        payoff_ids = list(db.scalars(
            select(Event.id).where(
                text(":eid IN (SELECT value FROM json_each(events.foreshadows))")
            ).params(eid=e.id)
        ))
        payoff_titles = []
        for pid in payoff_ids:
            other = db.get(Event, pid)
            if other:
                payoff_titles.append(other.title)

    return EventRead(
        id=e.id,
        project_id=e.project_id,
        chapter_id=e.chapter_id,
        chapter_title=ch.title if ch else "",
        chapter_order=ch.order_index if ch else 0,
        title=e.title,
        description=e.description,
        involved_characters=e.involved_characters or [],
        involved_character_names=involved_names,
        location_id=e.location_id,
        location_name=loc.name if loc else "",
        plot_line_id=e.plot_line_id,
        foreshadows=e.foreshadows or [],
        payoff_of=payoff_ids,
        payoff_of_titles=payoff_titles,
        extractor_log_id=e.extractor_log_id,
        pending_update_id=e.pending_update_id,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


@router.get("", response_model=list[EventRead])
def list_events(
    project_id: int = Query(...),
    chapter_id: int | None = Query(None),
    filter: str = Query("all", pattern="^(all|unpaid|paid)$"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    # Fetch all project events (filter + sort need full set)
    stmt = select(Event).where(Event.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(Event.chapter_id == chapter_id)
    all_rows = list(db.scalars(stmt))

    if not all_rows:
        return []

    # Pre-fetch JOINed entities (avoid N+1)
    char_ids = {i for e in all_rows for i in (e.involved_characters or [])}
    loc_ids = {e.location_id for e in all_rows if e.location_id is not None}
    chapter_ids = {e.chapter_id for e in all_rows}

    char_by_id = {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(char_ids)))} if char_ids else {}
    loc_by_id = {l.id: l for l in db.scalars(select(LoreEntry).where(LoreEntry.id.in_(loc_ids)))} if loc_ids else {}
    chapter_by_id = {c.id: c for c in db.scalars(select(Chapter).where(Chapter.id.in_(chapter_ids)))} if chapter_ids else {}

    # Build payoff map: target_id → list of event ids that foreshadow it
    payoff_map: dict[int, list[int]] = {}
    event_title_by_id = {e.id: e.title for e in all_rows}
    for e in all_rows:
        for target_id in (e.foreshadows or []):
            payoff_map.setdefault(target_id, []).append(e.id)

    def _target_has_external_payoff(src_id: int, target_id: int) -> bool:
        """Target is referenced by some event OTHER than src itself."""
        return any(pid != src_id for pid in payoff_map.get(target_id, []))

    # Apply filter BEFORE pagination
    if filter == "unpaid":
        rows = [
            e for e in all_rows
            if e.foreshadows and any(
                not _target_has_external_payoff(e.id, tid) for tid in e.foreshadows
            )
        ]
    elif filter == "paid":
        rows = [
            e for e in all_rows
            if e.foreshadows and all(
                _target_has_external_payoff(e.id, tid) for tid in e.foreshadows
            )
        ]
    else:
        rows = list(all_rows)

    # Sort by (chapter_order, id) BEFORE pagination
    rows.sort(key=lambda e: (
        chapter_by_id.get(e.chapter_id).order_index
        if chapter_by_id.get(e.chapter_id) else 0,
        e.id,
    ))

    # Paginate LAST (Python slice)
    page = rows[offset:offset + limit]

    return [
        _build_response(db, e, char_by_id, loc_by_id, chapter_by_id,
                        payoff_map, event_title_by_id)
        for e in page
    ]


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.get(Event, event_id)
    if e is None:
        raise HTTPException(status_code=404, detail="event not found")

    char_by_id = {}
    loc_by_id = {}
    chapter_by_id = {e.chapter_id: db.get(Chapter, e.chapter_id)} if e.chapter_id else {}
    return _build_response(db, e, char_by_id, loc_by_id, chapter_by_id)


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    ch = db.get(Chapter, payload.chapter_id)
    if ch is None or ch.project_id != payload.project_id:
        raise HTTPException(status_code=422, detail="chapter not found in project")

    _validate_involved_characters(db, payload.involved_characters)
    _validate_location(db, payload.location_id)
    _validate_foreshadows(db, payload.project_id, payload.foreshadows)

    e = Event(
        project_id=payload.project_id,
        chapter_id=payload.chapter_id,
        title=payload.title,
        description=payload.description,
        involved_characters=payload.involved_characters,
        location_id=payload.location_id,
        foreshadows=payload.foreshadows,
    )
    db.add(e)
    db.commit()
    db.refresh(e)

    char_by_id = {c.id: c for c in db.scalars(
        select(Character).where(Character.id.in_(e.involved_characters or []))
    )} if e.involved_characters else {}
    loc_by_id = {e.location_id: db.get(LoreEntry, e.location_id)} if e.location_id else {}
    chapter_by_id = {e.chapter_id: ch}
    return _build_response(db, e, char_by_id, loc_by_id, chapter_by_id)


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
):
    e = db.get(Event, event_id)
    if e is None:
        raise HTTPException(status_code=404, detail="event not found")

    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        e.title = data["title"]
    if "description" in data:
        e.description = data["description"]
    if "involved_characters" in data:
        _validate_involved_characters(db, data["involved_characters"])
        e.involved_characters = data["involved_characters"]
    if "location_id" in data:
        _validate_location(db, data["location_id"])
        e.location_id = data["location_id"]
    if "foreshadows" in data:
        _validate_foreshadows(db, e.project_id, data["foreshadows"], self_id=e.id)
        e.foreshadows = data["foreshadows"]

    db.commit()
    db.refresh(e)

    char_by_id = {c.id: c for c in db.scalars(
        select(Character).where(Character.id.in_(e.involved_characters or []))
    )} if e.involved_characters else {}
    loc_by_id = {e.location_id: db.get(LoreEntry, e.location_id)} if e.location_id else {}
    chapter_by_id = {e.chapter_id: db.get(Chapter, e.chapter_id)}
    return _build_response(db, e, char_by_id, loc_by_id, chapter_by_id)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    e = db.get(Event, event_id)
    if e is None:
        raise HTTPException(status_code=404, detail="event not found")

    # Cascade cleanup: remove this event's id from all other events' foreshadows
    referencing = list(db.scalars(
        select(Event).where(
            Event.project_id == e.project_id,
            text(":eid IN (SELECT value FROM json_each(events.foreshadows))")
        ).params(eid=event_id)
    ))
    for r in referencing:
        r.foreshadows = [i for i in (r.foreshadows or []) if i != event_id]

    db.delete(e)
    db.commit()
