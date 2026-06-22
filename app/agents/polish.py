"""Polish Agent: refine existing text quality.

Flow:
    1. Resolve chapter → fetch chapter.content + last_involved_character_ids.
    2. assemble_context(db, chapter_id, ...) → lighter writing context bundle.
    3. render polish/system.j2 + user.j2.
    4. router.complete(request)  # single call.
    5. Validate plain-text response (non-empty, not truncated by max_tokens).
    6. INSERT generation_logs (model_task='polish').

Race contract:
    polish_chapter is NOT safe to run concurrently with accept/reject operations
    on the same chapter. The DB transaction only guarantees atomicity on its own
    writes (generation_logs INSERT), not isolation from concurrent mutations to
    related rows.
"""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.memory.errors import ChapterNotFoundError, PolishError
from app.memory.retrieval import assemble_context
from app.memory.schema import Chapter, GenerationLog

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class PolishResult:
    polished_text: str
    is_selection: bool
    log_id: int


def polish_chapter(
    db: Session,
    *,
    chapter_id: int,
    selected_text: str | None = None,
    router: ModelRouter = default_router,
) -> PolishResult:
    """Polish existing text. If selected_text is provided, polish that passage;
    otherwise polish the entire chapter content.

    Returns plain polished text (not JSON).

    Raises:
        ChapterNotFoundError: chapter does not exist.
        PolishError: LLM returned empty response or hit max_tokens.
    """
    # assemble_context does not return chapter; fetch directly so we can pass
    # chapter.content to the prompt. Also resolve involved characters from the
    # chapter's last_involved_character_ids so the LLM gets character context.
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)

    involved_ids = list(chapter.last_involved_character_ids or [])

    bundle = assemble_context(
        db,
        chapter_id=chapter_id,
        beat_text="(polish)",
        involved_character_ids=involved_ids,
    )

    system_prompt = render("polish/system.j2")
    user_prompt = render(
        "polish/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        characters=bundle.characters,
        character_states=bundle.character_states,
        relationships=bundle.relationships,
        plot_lines=bundle.plot_lines,
        milestones=bundle.milestones,
        selected_text=selected_text or "",
        chapter_content=chapter.content or "",
    )

    request = LLMRequest(
        model_task="writer_long",
        system=system_prompt,
        user=user_prompt,
        max_tokens=8192,
        temperature=0.4,
    )

    _, model_name = router.resolve_model("writer_long")
    response = router.complete(request)

    polished = (response.text or "").strip()
    if not polished:
        raise PolishError("LLM returned empty response")
    if response.stop_reason == "max_tokens":
        raise PolishError("LLM hit max_tokens; output likely truncated")

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=chapter.project_id,
        beat_text="(polish)",
        instruction=selected_text or "(whole chapter)",
        involved_character_ids=involved_ids,
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "is_selection": selected_text is not None,
            "characters": len(bundle.characters),
            "relationships": len(bundle.relationships),
        },
        generated_text=response.text,
        model=model_name,
        model_task="polish",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        stop_reason=response.stop_reason,
        status="done",
        started_at=_now(),
        finished_at=_now(),
    )

    try:
        db.add(log)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    return PolishResult(
        polished_text=polished,
        is_selection=selected_text is not None,
        log_id=log.id,
    )
