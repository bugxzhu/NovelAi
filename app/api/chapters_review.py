"""M4a: POST /api/chapters/{id}/review — sync review across 5 dimensions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.reviewer import review_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.schema import Chapter
from app.models.review import ReviewResponse

router = APIRouter()


@router.post("/{chapter_id}/review", response_model=ReviewResponse)
def review(chapter_id: int, db: Session = Depends(get_db)):
    ch = db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    try:
        result = review_chapter(db, chapter_id=chapter_id, router=default_router)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except ReviewError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "review_failed", "reason": str(e)[:200]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return ReviewResponse(
        chapter_id=result.chapter_id,
        issues=result.issues,
        log_id=result.log_id,
    )
