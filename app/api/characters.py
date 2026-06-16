from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character
from app.models.character import CharacterCreate, CharacterRead, CharacterUpdate

router = APIRouter()


@router.post("", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
def create_character(payload: CharacterCreate, db: Session = Depends(get_db)):
    obj = Character(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[CharacterRead])
def list_characters(project_id: int = Query(...), db: Session = Depends(get_db)):
    stmt = select(Character).where(Character.project_id == project_id).order_by(Character.id)
    return list(db.scalars(stmt))


@router.get("/{character_id}", response_model=CharacterRead)
def get_character(character_id: int, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    return obj


@router.patch("/{character_id}", response_model=CharacterRead)
def update_character(character_id: int, payload: CharacterUpdate, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: int, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    db.delete(obj)
    db.commit()
