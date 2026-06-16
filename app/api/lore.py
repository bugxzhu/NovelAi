from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import LoreEntry
from app.models.lore import LoreEntryCreate, LoreEntryRead, LoreEntryUpdate

router = APIRouter()


@router.post("", response_model=LoreEntryRead, status_code=status.HTTP_201_CREATED)
def create_lore(payload: LoreEntryCreate, db: Session = Depends(get_db)):
    obj = LoreEntry(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[LoreEntryRead])
def list_lore(
    project_id: int = Query(...),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(LoreEntry).where(LoreEntry.project_id == project_id)
    if type is not None:
        stmt = stmt.where(LoreEntry.type == type)
    stmt = stmt.order_by(LoreEntry.id)
    return list(db.scalars(stmt))


@router.get("/{lore_id}", response_model=LoreEntryRead)
def get_lore(lore_id: int, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    return obj


@router.patch("/{lore_id}", response_model=LoreEntryRead)
def update_lore(lore_id: int, payload: LoreEntryUpdate, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{lore_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lore(lore_id: int, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    db.delete(obj)
    db.commit()
