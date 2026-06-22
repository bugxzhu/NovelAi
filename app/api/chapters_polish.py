"""POST /api/chapters/{id}/polish — refine existing text."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.polish import polish_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, PolishError
from app.memory.schema import Chapter
from app.models.polish import PolishRequest, PolishResponse

router = APIRouter()


@router.post("/{chapter_id}/polish", response_model=PolishResponse)
def polish(
    chapter_id: int,
    body: PolishRequest,
    db: Session = Depends(get_db),
):
    ch = db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    try:
        result = polish_chapter(
            db, chapter_id=chapter_id,
            selected_text=body.selected_text,
            direction=body.direction,
            router=default_router,
        )
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except PolishError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "polish_failed", "reason": str(e)[:200]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return PolishResponse(
        polished_texts=result.polished_texts,
        is_selection=result.is_selection,
        direction=result.direction,
        log_id=result.log_id,
    )
