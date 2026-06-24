from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api._helpers import get_project_or_404
from app.api.deps import get_db
from app.memory.schema import Chapter
from app.models.chapter import ChapterCreate, ChapterListItem, ChapterRead, ChapterUpdate

router = APIRouter()


@router.post("", response_model=ChapterRead, status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db)):
    get_project_or_404(db, payload.project_id)
    obj = Chapter(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[ChapterListItem])
def list_chapters(project_id: int = Query(...), db: Session = Depends(get_db)):
    stmt = (
        select(
            Chapter.id,
            Chapter.project_id,
            Chapter.order_index,
            Chapter.title,
            Chapter.status,
            Chapter.summary,
            # Chinese char count: strip spaces + newlines, count remaining chars
            func.length(
                func.replace(func.replace(Chapter.content, " ", ""), "\n", "")
            ).label("char_count"),
            Chapter.created_at,
            Chapter.updated_at,
        )
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order_index, Chapter.id)
    )
    rows = db.execute(stmt).all()
    return [
        ChapterListItem(
            id=r.id,
            project_id=r.project_id,
            order_index=r.order_index,
            title=r.title,
            status=r.status,
            summary=r.summary,
            char_count=r.char_count or 0,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/{chapter_id}", response_model=ChapterRead)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    return obj


@router.patch("/{chapter_id}", response_model=ChapterRead)
def update_chapter(chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: int, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    db.delete(obj)
    db.commit()
