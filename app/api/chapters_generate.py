import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.writer import prepare_generation, stream_generation
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.models.generation import GenerateRequest

router = APIRouter()


def _format_sse(event_type: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/{chapter_id}/generate")
def generate(
    chapter_id: int,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        prep = prepare_generation(
            db,
            chapter_id=chapter_id,
            beat_text=payload.beat_text,
            instruction=payload.instruction,
            involved_character_ids=payload.involved_character_ids,
            location_id=payload.location_id,
            model_task=payload.model_task,
            max_tokens=payload.max_tokens,
            router=default_router,
        )
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except InvalidContextError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_context",
                "invalid_character_ids": e.invalid_character_ids,
                "invalid_location_id": e.invalid_location_id,
            },
        )

    def event_stream():
        try:
            for event_dict in stream_generation(db, prep, router=default_router):
                event_type = event_dict["type"]
                data = {k: v for k, v in event_dict.items() if k != "type"}
                yield _format_sse(event_type, data)
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
