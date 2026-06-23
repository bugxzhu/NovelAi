"""Polish Agent: refine existing text quality.

Flow:
    1. Resolve chapter → fetch chapter.content + last_involved_character_ids.
    2. assemble_context(db, chapter_id, ...) → lighter writing context bundle.
    3. render polish/system.j2 + user.j2. The prompts get:
       - selected_text ("" for whole-chapter polish)
       - chapter_content (ALWAYS sent; acts as style context for selection mode
         AND as the polish target for whole-chapter mode)
       - direction (user-provided polish direction; "" = none)
       - is_selection (drives JSON output format: 2 versions vs 1 version)
    4. router.complete(request)  # single call.
    5. Parse JSON {"versions": [...]} with tolerance (fall back to treating
       response.text as single version if JSON parse fails).
    6. INSERT generation_logs (model_task='polish').

Race contract:
    polish_chapter is NOT safe to run concurrently with accept/reject operations
    on the same chapter. The DB transaction only guarantees atomicity on its own
    writes (generation_logs INSERT), not isolation from concurrent mutations to
    related rows.
"""
import json
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
    polished_texts: list[str]
    is_selection: bool
    direction: str
    log_id: int


def polish_chapter(
    db: Session,
    *,
    chapter_id: int,
    selected_text: str | None = None,
    direction: str = "",
    router: ModelRouter = default_router,
) -> PolishResult:
    """Polish existing text. Returns 2 versions for selection, 1 for whole chapter.

    For selection mode (selected_text provided & non-empty):
        - LLM is shown BOTH chapter_content (style context) AND selected_text
          (the passage to actually rewrite).
        - Output is JSON {"versions": ["v1", "v2"]} (2 distinct versions).

    For whole-chapter mode (no selected_text):
        - LLM polishes the entire chapter_content.
        - Output is JSON {"versions": ["v1"]} (1 version).

    JSON parse is tolerant: if the LLM does not return valid JSON, the raw
    response is wrapped into a single-element list as fallback.

    Raises:
        ChapterNotFoundError: chapter does not exist.
        PolishError: LLM returned empty response or hit max_tokens.
    """
    is_selection = selected_text is not None and selected_text.strip() != ""

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

    from app.memory.context_budget import trim_review_context
    bundle, budget_info = trim_review_context(bundle)
    if budget_info["actions"]:
        logger.info("ContextBudget actions: %s", budget_info["actions"])

    from app.config.genre_templates import get_genre_template
    genre_template = get_genre_template(bundle.project.genre)

    system_prompt = render(
        "polish/system.j2",
        direction=direction,
        is_selection=is_selection,
    )
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
        direction=direction,
        is_selection=is_selection,
        genre_template=genre_template,
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

    if response.stop_reason == "max_tokens":
        raise PolishError("LLM hit max_tokens; output likely truncated")

    raw = (response.text or "").strip()
    if not raw:
        raise PolishError("LLM returned empty response")

    # Try JSON parse first ({"versions": ["...", "..."]}).
    polished_texts: list[str] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            versions = parsed.get("versions") or parsed.get("polished_texts") or []
            if isinstance(versions, list):
                polished_texts = [
                    v.strip() for v in versions
                    if isinstance(v, str) and v.strip()
                ]
    except json.JSONDecodeError:
        pass

    # Fallback: treat entire response as single version.
    if not polished_texts:
        polished_texts = [raw]

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=chapter.project_id,
        beat_text="(polish)",
        instruction=direction or selected_text or "(whole chapter)",
        involved_character_ids=involved_ids,
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "is_selection": is_selection,
            "direction": direction,
            "num_versions": len(polished_texts),
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
        polished_texts=polished_texts,
        is_selection=is_selection,
        direction=direction,
        log_id=log.id,
    )
