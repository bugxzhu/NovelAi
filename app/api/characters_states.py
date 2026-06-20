"""M3c-B: GET /api/characters/{id}/states — list a character's state history."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character, CharacterState, Chapter
from app.models.character_state import CharacterStateRead

router = APIRouter()


@router.get("/{character_id}/states", response_model=list[CharacterStateRead])
def list_character_states(
    character_id: int,
    order: str = Query("desc", pattern="^(desc|asc)$"),
    limit: int = Query(20, ge=1),
    db: Session = Depends(get_db),
):
    # Cap silently at 100 to keep responses bounded without 422-ing the client.
    limit = min(limit, 100)

    char = db.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail="character not found")

    stmt = (
        select(CharacterState, Chapter)
        .join(Chapter, Chapter.id == CharacterState.chapter_id)
        .where(CharacterState.character_id == character_id)
    )
    if order == "desc":
        stmt = stmt.order_by(Chapter.order_index.desc(),
                             CharacterState.created_at.desc())
    else:
        stmt = stmt.order_by(Chapter.order_index.asc(),
                             CharacterState.created_at.asc())
    stmt = stmt.limit(limit)

    rows = list(db.execute(stmt))
    return [
        CharacterStateRead(
            id=cs.id,
            character_id=cs.character_id,
            chapter_id=cs.chapter_id,
            chapter_title=ch.title,
            chapter_order=ch.order_index,
            state_snapshot=cs.state_snapshot,
            change_summary=cs.change_summary,
            extractor_log_id=cs.extractor_log_id,
            pending_update_id=cs.pending_update_id,
            created_at=cs.created_at,
            updated_at=cs.updated_at,
        )
        for cs, ch in rows
    ]
