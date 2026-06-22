"""Discuss Agent: multi-branch plot exploration in 1 LLM call.

Flow:
    1. assemble_review_context(db, chapter_id) → rich context bundle.
    2. render discuss/system.j2 + user.j2.
    3. router.complete(request)  # single call.
    4. Parse JSON → list[DiscussBranch] (with tolerance, truncate to 3).
    5. INSERT generation_logs (model_task='discuss').

Race contract:
    discuss_chapter is NOT safe to run concurrently with accept/reject operations
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
from app.memory.errors import ChapterNotFoundError, DiscussError
from app.memory.retrieval import assemble_review_context
from app.memory.schema import GenerationLog
from app.models.discuss import DiscussBranch, DiscussResponse

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class DiscussResult:
    question: str
    branches: list[DiscussBranch]
    recommended: str
    reasoning: str
    log_id: int


def discuss_chapter(
    db: Session,
    *,
    chapter_id: int,
    question: str,
    selected_text: str | None = None,
    router: ModelRouter = default_router,
) -> DiscussResult:
    """Discuss a plot hypothetical. Single LLM call, sync.

    If selected_text is provided, the discussion focuses on that specific
    passage rather than the whole chapter.

    Raises:
        ChapterNotFoundError: chapter does not exist.
        DiscussError: LLM returned non-JSON, hit max_tokens, or returned
            branches that is not a list.
    """
    bundle = assemble_review_context(db, chapter_id=chapter_id)

    system_prompt = render("discuss/system.j2")
    user_prompt = render(
        "discuss/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        chapter=bundle.chapter,
        characters=bundle.characters,
        character_states_history=bundle.character_states_history,
        relationships=bundle.relationships,
        events=bundle.events,
        lore_entries=bundle.lore_entries,
        plot_lines=bundle.plot_lines,
        milestones=bundle.milestones,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
        question=question,
        selected_text=selected_text or "",
    )

    request = LLMRequest(
        model_task="discuss",
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
        temperature=0.3,  # slightly more creative than reviewer's 0.1
    )

    _, model_name = router.resolve_model("discuss")
    response = router.complete(request)

    if response.stop_reason == "max_tokens":
        raise DiscussError(
            f"LLM hit max_tokens; response={response.text[:500]}"
        )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise DiscussError(
            f"LLM returned non-JSON: {e}; response={response.text[:500]}"
        )

    raw_branches = parsed.get("branches")
    if not isinstance(raw_branches, list):
        raise DiscussError("branches must be a list")

    branches: list[DiscussBranch] = []
    for raw in raw_branches[:3]:  # truncate to 3 if more
        if not isinstance(raw, dict):
            continue
        branches.append(DiscussBranch(
            label=(raw.get("label") or "").strip(),
            title=(raw.get("title") or "").strip(),
            summary=(raw.get("summary") or "").strip(),
            conflicts=(raw.get("conflicts") or "").strip(),
            opportunities=(raw.get("opportunities") or "").strip(),
            character_impact=(raw.get("character_impact") or "").strip(),
        ))

    recommended = (parsed.get("recommended") or "A").strip()
    reasoning = (parsed.get("reasoning") or "").strip()

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=bundle.chapter.project_id,
        beat_text="(discuss)",
        instruction=question,
        involved_character_ids=[c.id for c in bundle.characters],
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "characters": len(bundle.characters),
            "relationships": len(bundle.relationships),
            "events": len(bundle.events),
            "lore": len(bundle.lore_entries),
            "summaries": len(bundle.recent_chapter_summaries),
        },
        generated_text=response.text,
        model=model_name,
        model_task="discuss",
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

    return DiscussResult(
        question=question, branches=branches,
        recommended=recommended, reasoning=reasoning,
        log_id=log.id,
    )
