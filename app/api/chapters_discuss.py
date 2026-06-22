"""M4b-2: POST /api/chapters/{id}/discuss — multi-branch exploration."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.discuss import discuss_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, DiscussError
from app.memory.schema import Chapter
from app.models.discuss import DiscussRequest, DiscussResponse

router = APIRouter()


@router.post("/{chapter_id}/discuss", response_model=DiscussResponse)
def discuss(
    chapter_id: int,
    body: DiscussRequest,
    db: Session = Depends(get_db),
):
    ch = db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    try:
        result = discuss_chapter(
            db, chapter_id=chapter_id, question=body.question,
            selected_text=body.selected_text,
            router=default_router,
        )
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except DiscussError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "discuss_failed", "reason": str(e)[:200]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return DiscussResponse(
        question=result.question,
        branches=result.branches,
        recommended=result.recommended,
        reasoning=result.reasoning,
        log_id=result.log_id,
    )
