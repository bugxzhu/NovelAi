"""Reviewer Agent: 5-dimension chapter review in 1 merged LLM call.

Flow:
    1. assemble_review_context(db, chapter_id) → rich context bundle.
    2. render reviewer/system.j2 + user.j2.
    3. router.complete(request)  # single call.
    4. Parse JSON → list[Issue] (with tolerance).
    5. INSERT generation_logs (model_task='reviewer').

Race contract:
    review_chapter is NOT safe to run concurrently with accept/reject operations
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
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.retrieval import assemble_review_context
from app.memory.schema import GenerationLog
from app.models.review import Issue

logger = logging.getLogger(__name__)

ALLOWED_SEVERITIES = {"error", "warn", "info"}
ALLOWED_CATEGORIES = {"character", "relationship", "plot", "foreshadow", "worldview"}


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ReviewResult:
    chapter_id: int
    issues: list[Issue]
    log_id: int


def review_chapter(
    db: Session,
    *,
    chapter_id: int,
    router: ModelRouter = default_router,
) -> ReviewResult:
    """Review a chapter across 5 dimensions. Single LLM call, sync.

    Raises:
        ChapterNotFoundError: chapter does not exist.
        ReviewError: LLM returned non-JSON, hit max_tokens, or returned
            issues_by_category that is not a dict.
    """
    bundle = assemble_review_context(db, chapter_id=chapter_id)

    system_prompt = render("reviewer/system.j2")
    user_prompt = render(
        "reviewer/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        chapter=bundle.chapter,
        characters=bundle.characters,
        character_states_history=bundle.character_states_history,
        relationships=bundle.relationships,
        events=bundle.events,
        lore_entries=bundle.lore_entries,
        plot_lines=bundle.plot_lines,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
    )

    request = LLMRequest(
        model_task="reviewer",
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
        temperature=0.1,
    )

    _, model_name = router.resolve_model("reviewer")
    response = router.complete(request)

    if response.stop_reason == "max_tokens":
        raise ReviewError(
            f"LLM hit max_tokens; output likely truncated. response={response.text[:500]}"
        )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ReviewError(
            f"LLM returned non-JSON: {e}; response={response.text[:500]}"
        )

    issues_by_category = parsed.get("issues_by_category")
    if issues_by_category is None:
        # Missing key → treat as empty (5 dimensions may all be clean)
        issues_by_category = {}
    if not isinstance(issues_by_category, dict):
        raise ReviewError(
            f"issues_by_category must be an object, got {type(issues_by_category).__name__}"
        )

    issues: list[Issue] = []
    for cat, raw_issues in issues_by_category.items():
        if cat not in ALLOWED_CATEGORIES:
            logger.info("reviewer: skipping unknown category %r", cat)
            continue
        if not isinstance(raw_issues, list):
            continue
        for raw in raw_issues:
            if not isinstance(raw, dict):
                continue
            severity = raw.get("severity", "info")
            if severity not in ALLOWED_SEVERITIES:
                severity = "info"
            description = (raw.get("description") or "").strip()
            if not description:
                continue  # 没 description 的 Issue 没意义
            issues.append(Issue(
                severity=severity,
                category=cat,  # type: ignore[arg-type]
                location=(raw.get("location") or "").strip(),
                description=description,
                suggestion=(raw.get("suggestion") or "").strip(),
            ))

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=bundle.chapter.project_id,
        beat_text="(review)",
        instruction="",
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
        model_task="reviewer",
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

    return ReviewResult(chapter_id=chapter_id, issues=issues, log_id=log.id)
