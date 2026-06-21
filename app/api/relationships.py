"""M3c-A: /api/relationships — CRUD + history + soft-close."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character, Chapter, Relationship
from app.models.relationship import (
    RelationshipCreate,
    RelationshipHistoryItem,
    RelationshipRead,
    RelationshipSoftCloseBody,
    RelationshipUpdate,
)

router = APIRouter()


def _clamp_strength(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _to_read(
    r: Relationship,
    db: Session | None = None,
    char_by_id: dict[int, Character] | None = None,
) -> RelationshipRead:
    """Build RelationshipRead. Either pass char_by_id (pre-fetched dict, no N+1)
    or db (will db.get per call — use only for single-row endpoints)."""
    if char_by_id is not None:
        from_c = char_by_id.get(r.from_char_id)
        to_c = char_by_id.get(r.to_char_id)
    else:
        from_c = db.get(Character, r.from_char_id) if db else None
        to_c = db.get(Character, r.to_char_id) if db else None
    return RelationshipRead(
        id=r.id,
        project_id=r.project_id,
        from_char_id=r.from_char_id,
        from_char_name=from_c.name if from_c else "",
        to_char_id=r.to_char_id,
        to_char_name=to_c.name if to_c else "",
        type=r.type,
        strength=r.strength,
        description=r.description,
        valid_from_chapter=r.valid_from_chapter,
        valid_to_chapter=r.valid_to_chapter,
        change_summary=r.change_summary,
        extractor_log_id=r.extractor_log_id,
        pending_update_id=r.pending_update_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=list[RelationshipRead])
def list_relationships(
    project_id: int = Query(...),
    include_history: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Relationship).where(Relationship.project_id == project_id)
    if not include_history:
        stmt = stmt.where(Relationship.valid_to_chapter.is_(None))
    stmt = stmt.order_by(Relationship.from_char_id, Relationship.to_char_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = list(db.scalars(stmt))

    # Pre-fetch all characters for this project once (avoids N+1 in _to_read).
    project_chars = list(db.scalars(
        select(Character).where(Character.project_id == project_id)
    ))
    char_by_id = {c.id: c for c in project_chars}
    return [_to_read(r, char_by_id=char_by_id) for r in rows]


@router.get("/history", response_model=list[RelationshipHistoryItem])
def relationship_history(
    from_char_id: int = Query(...),
    to_char_id: int = Query(...),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(
        select(Relationship).where(
            Relationship.from_char_id == from_char_id,
            Relationship.to_char_id == to_char_id,
        ).order_by(Relationship.valid_from_chapter.desc(),
                    Relationship.created_at.desc())
    ))
    return [
        RelationshipHistoryItem(
            version_id=r.id,
            valid_from_chapter=r.valid_from_chapter,
            valid_to_chapter=r.valid_to_chapter,
            type=r.type,
            strength=r.strength,
            description=r.description,
            change_summary=r.change_summary,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", response_model=RelationshipRead,
             status_code=status.HTTP_201_CREATED)
def create_relationship(payload: RelationshipCreate, db: Session = Depends(get_db)):
    if payload.from_char_id == payload.to_char_id:
        raise HTTPException(status_code=422, detail="from and to cannot be the same character")
    if db.get(Character, payload.from_char_id) is None:
        raise HTTPException(status_code=404, detail="from_char not found")
    if db.get(Character, payload.to_char_id) is None:
        raise HTTPException(status_code=404, detail="to_char not found")

    rel = Relationship(
        project_id=payload.project_id,
        from_char_id=payload.from_char_id,
        to_char_id=payload.to_char_id,
        type=payload.type,
        strength=_clamp_strength(payload.strength),
        description=payload.description,
        valid_from_chapter=payload.valid_from_chapter,
        valid_to_chapter=None,
        change_summary=payload.change_summary,
    )
    db.add(rel)
    try:
        db.commit()
    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="a current-valid relationship already exists for this direction",
        )
    db.refresh(rel)
    return _to_read(rel, db)


@router.get("/{relationship_id}", response_model=RelationshipRead)
def get_relationship(relationship_id: int, db: Session = Depends(get_db)):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    return _to_read(r, db)


@router.patch("/{relationship_id}", response_model=RelationshipRead)
def update_relationship(
    relationship_id: int,
    payload: RelationshipUpdate,
    db: Session = Depends(get_db),
):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    data = payload.model_dump(exclude_unset=True)
    if "type" in data:
        r.type = data["type"]
    if "strength" in data:
        r.strength = _clamp_strength(data["strength"])
    if "description" in data:
        r.description = data["description"]
    db.commit()
    db.refresh(r)
    return _to_read(r, db)


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(relationship_id: int, db: Session = Depends(get_db)):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    if r.valid_to_chapter is None:
        raise HTTPException(
            status_code=409,
            detail="cannot delete current-valid relationship; use soft-close instead",
        )
    db.delete(r)
    db.commit()


@router.post("/{relationship_id}/soft-close", response_model=RelationshipRead)
def soft_close_relationship(
    relationship_id: int,
    body: RelationshipSoftCloseBody,
    db: Session = Depends(get_db),
):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    if r.valid_to_chapter is not None:
        raise HTTPException(
            status_code=409,
            detail="relationship already soft-closed",
        )
    r.valid_to_chapter = body.valid_to_chapter
    r.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(r)
    return _to_read(r, db)
