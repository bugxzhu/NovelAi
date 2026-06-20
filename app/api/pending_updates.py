from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import (
    Chapter,
    Character,
    CharacterState,
    LoreEntry,
    PendingUpdate,
    Relationship,
)
from app.models.pending import (
    AcceptRejectResponse,
    PendingUpdateDetail,
    PendingUpdateRead,
    RejectBody,
)

router = APIRouter()


def _derive_summary_fields(proposed_change: dict, target_table: str) -> dict:
    """Extract entity_name / entity_type / field_name / old_value / proposed_value
    from proposed_change JSON. Returns kwargs for PendingUpdateRead."""
    if target_table == "characters":
        entity_type = ""
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    elif target_table == "lore_entries":
        entity_type = proposed_change.get("type", "")
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    elif target_table == "character_states":
        # M3c-B: state changes (always operation='create', target_id=null)
        entity_type = ""
        entity_name = proposed_change.get("character_name", "")
        field_name = "state_snapshot"
        old_value = ""
        proposed_value = proposed_change.get("state_snapshot", "")
    elif target_table == "relationships":
        from_name = proposed_change.get("from_character_name", "")
        to_name = proposed_change.get("to_character_name", "")
        entity_type = ""
        entity_name = f"{from_name} → {to_name}" if from_name and to_name else ""
        field_name = ""
        old_value = ""
        rtype = proposed_change.get("type", "")
        strength = proposed_change.get("strength", 0.0)
        desc = proposed_change.get("description", "")
        proposed_value = (
            f"{rtype}（强度 {strength}）：{desc}" if desc
            else f"{rtype}（强度 {strength}）"
        )
    else:
        entity_type = ""
        entity_name = ""
        field_name = ""
        old_value = ""
        proposed_value = ""
    return {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "field_name": field_name,
        "old_value": old_value,
        "proposed_value": proposed_value,
    }


def _to_read(p: PendingUpdate) -> PendingUpdateRead:
    return PendingUpdateRead(
        id=p.id,
        project_id=p.project_id,
        chapter_id=p.chapter_id,
        update_type=p.update_type,
        operation=p.operation,
        target_table=p.target_table,
        target_id=p.target_id,
        reason=p.reason,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_derive_summary_fields(p.proposed_change or {}, p.target_table),
    )


def _to_detail(p: PendingUpdate, db: Session) -> PendingUpdateDetail:
    chapter = db.get(Chapter, p.chapter_id)
    chapter_title = chapter.title if chapter else ""
    target_entity_name = None
    if p.target_id is not None:
        if p.target_table == "characters":
            t = db.get(Character, p.target_id)
            target_entity_name = t.name if t else None
        elif p.target_table == "lore_entries":
            t = db.get(LoreEntry, p.target_id)
            target_entity_name = t.name if t else None
    return PendingUpdateDetail(
        id=p.id,
        project_id=p.project_id,
        chapter_id=p.chapter_id,
        update_type=p.update_type,
        operation=p.operation,
        target_table=p.target_table,
        target_id=p.target_id,
        reason=p.reason,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_derive_summary_fields(p.proposed_change or {}, p.target_table),
        proposed_change=p.proposed_change or {},
        decision_note=p.decision_note or "",
        decided_at=p.decided_at,
        extractor_model=p.extractor_model,
        extractor_log_id=p.extractor_log_id,
        chapter_title=chapter_title,
        target_entity_name=target_entity_name,
    )


@router.get("", response_model=list[PendingUpdateRead])
def list_pending(
    project_id: int = Query(...),
    status: str = Query("pending"),
    chapter_id: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if status == "all":
        status_filter = None
    else:
        status_filter = status

    stmt = select(PendingUpdate).where(PendingUpdate.project_id == project_id)
    if status_filter is not None:
        stmt = stmt.where(PendingUpdate.status == status_filter)
    if chapter_id is not None:
        stmt = stmt.where(PendingUpdate.chapter_id == chapter_id)
    stmt = stmt.order_by(PendingUpdate.id.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    return [_to_read(p) for p in rows]


@router.get("/{pending_id}", response_model=PendingUpdateDetail)
def get_pending(pending_id: int, db: Session = Depends(get_db)):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    return _to_detail(p, db)


@router.post("/{pending_id}/accept", response_model=AcceptRejectResponse)
def accept_pending(pending_id: int, db: Session = Depends(get_db)):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    if p.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {p.status}")

    try:
        if p.operation == "create":
            data = p.proposed_change or {}
            if p.target_table == "characters":
                db.add(Character(
                    project_id=p.project_id,
                    name=data.get("name", ""),
                    role=data.get("role", "extra"),
                    background=data.get("description", ""),
                ))
            elif p.target_table == "lore_entries":
                db.add(LoreEntry(
                    project_id=p.project_id,
                    type=data.get("type", "custom"),
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                ))
            elif p.target_table == "character_states":
                # M3c-B: INSERT temporal row + mirror to characters.current_state
                char_id = data.get("character_id")
                if char_id is None:
                    raise HTTPException(
                        status_code=500,
                        detail="character_states pending missing character_id",
                    )
                char = db.get(Character, char_id)
                if char is None:
                    raise HTTPException(
                        status_code=500, detail="target character gone")
                state = CharacterState(
                    character_id=char_id,
                    chapter_id=p.chapter_id,
                    state_snapshot=data.get("state_snapshot", ""),
                    change_summary=data.get("change_summary", ""),
                    extractor_log_id=p.extractor_log_id,
                    pending_update_id=p.id,
                )
                db.add(state)
                db.flush()  # get state.id for audit
                # Mirror strategy B: characters.current_state = latest snapshot
                char.current_state = data.get("state_snapshot", "")
            elif p.target_table == "relationships":
                # M3c-A: version-switch semantics
                data = p.proposed_change or {}
                from_id = data.get("from_character_id")
                to_id = data.get("to_character_id")
                if from_id is None or to_id is None:
                    raise HTTPException(
                        status_code=500,
                        detail="relationships pending missing from/to",
                    )
                # Validate both endpoints still exist
                if db.get(Character, from_id) is None or db.get(Character, to_id) is None:
                    raise HTTPException(
                        status_code=500, detail="target character gone")

                new_from_chapter = data.get("valid_from_chapter", p.chapter_id)

                # ① Soft-close existing current-valid (same direction)
                db.execute(
                    update(Relationship)
                    .where(
                        Relationship.from_char_id == from_id,
                        Relationship.to_char_id == to_id,
                        Relationship.valid_to_chapter.is_(None),
                    )
                    .values(valid_to_chapter=new_from_chapter,
                            updated_at=datetime.now(UTC))
                )

                # ② INSERT new version
                rel = Relationship(
                    project_id=p.project_id,
                    from_char_id=from_id, to_char_id=to_id,
                    type=data.get("type", ""),
                    strength=data.get("strength", 0.0),
                    description=data.get("description", ""),
                    valid_from_chapter=new_from_chapter,
                    valid_to_chapter=None,
                    change_summary=data.get("change_summary", ""),
                    extractor_log_id=p.extractor_log_id,
                    pending_update_id=p.id,
                )
                db.add(rel)
            else:
                raise HTTPException(status_code=500, detail=f"unknown target_table: {p.target_table}")
        elif p.operation == "update":
            data = p.proposed_change or {}
            if p.target_id is None:
                raise HTTPException(status_code=500, detail="update pending without target_id")
            if p.target_table == "characters":
                t = db.get(Character, p.target_id)
                if t is None:
                    raise HTTPException(status_code=500, detail="target character gone")
                field = data.get("field")
                if field:
                    setattr(t, field, data.get("new_value", ""))
            elif p.target_table == "lore_entries":
                t = db.get(LoreEntry, p.target_id)
                if t is None:
                    raise HTTPException(status_code=500, detail="target lore gone")
                field = data.get("field", "description")
                setattr(t, field, data.get("new_value", ""))
            else:
                raise HTTPException(status_code=500, detail=f"unknown target_table: {p.target_table}")
        else:
            raise HTTPException(status_code=500, detail=f"unknown operation: {p.operation}")

        p.status = "accepted"
        p.decided_at = datetime.now(UTC)
        db.commit()
        db.refresh(p)
        return _to_read(p)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="accept failed")


@router.post("/{pending_id}/reject", response_model=AcceptRejectResponse)
def reject_pending(
    pending_id: int,
    body: RejectBody | None = None,
    db: Session = Depends(get_db),
):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    if p.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {p.status}")

    note = body.note if body else ""
    p.status = "rejected"
    p.decision_note = note
    p.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return _to_read(p)
