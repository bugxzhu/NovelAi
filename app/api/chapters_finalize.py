from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.extractor import extract_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.models.pending import FinalizeResponse

router = APIRouter()


@router.post("/{chapter_id}/finalize", response_model=FinalizeResponse)
def finalize(
    chapter_id: int,
    db: Session = Depends(get_db),
) -> FinalizeResponse:
    try:
        result = extract_chapter(db, chapter_id=chapter_id, router=default_router)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except ExtractionError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "extraction_failed",
                "reason": "invalid JSON or missing fields",
                "raw": str(e)[:500],
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    return FinalizeResponse(
        chapter_id=result.chapter_id,
        summary=result.summary,
        pending_created=result.pending_created,
        log_id=result.log_id,
    )
