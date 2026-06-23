"""Full-text search across project content."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Chapter, Character, Event, LoreEntry

router = APIRouter()


@router.get("")
def search(
    project_id: int = Query(...),
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Search across chapters, characters, lore, and events."""
    results: dict[str, list] = {"chapters": [], "characters": [], "lore": [], "events": []}
    pattern = f"%{q}%"

    # Chapters: search title + content + summary
    chapters = list(db.scalars(
        select(Chapter).where(
            Chapter.project_id == project_id,
            or_(
                Chapter.title.ilike(pattern),
                Chapter.content.ilike(pattern),
                Chapter.summary.ilike(pattern),
            ),
        ).order_by(Chapter.order_index)
    ))
    results["chapters"] = [
        {
            "id": ch.id,
            "title": ch.title,
            "order_index": ch.order_index,
            "match_type": (
                "title" if q in (ch.title or "")
                else ("summary" if q in (ch.summary or "") else "content")
            ),
            "snippet": (
                _snippet(ch.content, q)
                if q in (ch.content or "")
                else ((ch.summary or "")[:100])
            ),
        }
        for ch in chapters
    ]

    # Characters: search name + background + motivation + current_state
    characters = list(db.scalars(
        select(Character).where(
            Character.project_id == project_id,
            or_(
                Character.name.ilike(pattern),
                Character.background.ilike(pattern),
                Character.motivation.ilike(pattern),
                Character.current_state.ilike(pattern),
            ),
        )
    ))
    results["characters"] = [
        {"id": c.id, "name": c.name, "role": c.role}
        for c in characters
    ]

    # Lore: search name + description
    lore = list(db.scalars(
        select(LoreEntry).where(
            LoreEntry.project_id == project_id,
            or_(
                LoreEntry.name.ilike(pattern),
                LoreEntry.description.ilike(pattern),
            ),
        )
    ))
    results["lore"] = [
        {"id": l.id, "name": l.name, "type": l.type}
        for l in lore
    ]

    # Events: search title + description
    events = list(db.scalars(
        select(Event).where(
            Event.project_id == project_id,
            or_(
                Event.title.ilike(pattern),
                Event.description.ilike(pattern),
            ),
        )
    ))
    results["events"] = [
        {"id": e.id, "name": e.title, "description": (e.description or "")[:80]}
        for e in events
    ]

    return results


def _snippet(text: str, query: str, context: int = 50) -> str:
    """Extract a snippet around the first match."""
    if not text:
        return ""
    idx = text.lower().find(query.lower())
    if idx < 0:
        return text[:100]
    start = max(0, idx - context)
    end = min(len(text), idx + len(query) + context)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix
