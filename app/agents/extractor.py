"""Extractor Agent: extract summary + entity deltas from a chapter.

Flow:
    1. Load chapter + project + existing entities (characters + lore_entries).
    2. Render extractor prompt with existing entities as context.
    3. Call router.complete(request) (synchronous).
    4. Parse JSON response (raise ExtractionError on bad JSON or missing summary).
    5. Build pending rows from entities dict (with tolerance for unknown enums /
       names).
    6. Atomic transaction: write generation_log row, DELETE old status='pending'
       rows for this chapter, INSERT new pending rows, UPDATE chapter.summary /
       content_hash / status='final'. Any failure rolls back the entire txn.
    7. Return ExtractionResult.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.memory.schema import (
    Chapter,
    Character,
    GenerationLog,
    LoreEntry,
    PendingUpdate,
    Project,
)

# Tolerance constants — invalid values are coerced/skipped rather than raising.
ALLOWED_ROLES = {"protagonist", "supporting", "antagonist", "extra"}
ALLOWED_CHARACTER_FIELDS = {"background", "motivation", "appearance", "current_state"}
ALLOWED_LORE_TYPES = {"location", "faction", "item", "organization", "concept"}
# update field for lore_entries is always "description" in M3a


@dataclass
class ExtractionResult:
    chapter_id: int
    summary: str
    pending_created: int
    log_id: int


def _now() -> datetime:
    return datetime.now(UTC)


def _build_pending_rows(
    entities: dict,
    *,
    project_id: int,
    chapter_id: int,
    existing_characters: list[Character],
    existing_lore: list[LoreEntry],
    model_name: str,
) -> list[PendingUpdate]:
    """Convert LLM entities dict to PendingUpdate rows.

    Tolerance rules:
        - new_characters / new_lore: empty/duplicate name → skip
        - new_characters: unknown role → "extra"
        - new_lore: unknown type → skip
        - updated_characters: name not in existing → skip; unknown field → skip;
          empty new_value → skip
        - updated_lore: name not in existing → skip; field != "description" → skip;
          empty new_value → skip
    """
    rows: list[PendingUpdate] = []
    char_by_name = {c.name: c for c in existing_characters}
    lore_by_name = {l.name: l for l in existing_lore}

    # new_characters
    for c in entities.get("new_characters", []) or []:
        name = (c.get("name") or "").strip()
        if not name or name in char_by_name:
            continue
        role = c.get("role", "extra")
        if role not in ALLOWED_ROLES:
            role = "extra"
        description = (c.get("description") or "").strip()
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="create",
            target_table="characters", target_id=None,
            proposed_change={"name": name, "role": role, "description": description},
            reason=c.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # updated_characters
    for c in entities.get("updated_characters", []) or []:
        name = (c.get("name") or "").strip()
        if not name or name not in char_by_name:
            continue
        field = c.get("field", "")
        if field not in ALLOWED_CHARACTER_FIELDS:
            continue
        new_value = (c.get("new_value") or "").strip()
        if not new_value:
            continue
        existing = char_by_name[name]
        old_value = str(getattr(existing, field, "") or "")
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="update",
            target_table="characters", target_id=existing.id,
            proposed_change={
                "name": name, "field": field,
                "old_value": old_value, "new_value": new_value,
            },
            reason=c.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # new_lore
    for l in entities.get("new_lore", []) or []:
        name = (l.get("name") or "").strip()
        if not name or name in lore_by_name:
            continue
        ltype = l.get("type", "")
        if ltype not in ALLOWED_LORE_TYPES:
            continue
        description = (l.get("description") or "").strip()
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="create",
            target_table="lore_entries", target_id=None,
            proposed_change={"type": ltype, "name": name, "description": description},
            reason=l.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # updated_lore
    for l in entities.get("updated_lore", []) or []:
        name = (l.get("name") or "").strip()
        if not name or name not in lore_by_name:
            continue
        field = l.get("field", "description")
        if field != "description":
            continue  # M3a only updates description
        new_value = (l.get("new_value") or "").strip()
        if not new_value:
            continue
        existing = lore_by_name[name]
        old_value = str(existing.description or "")
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="update",
            target_table="lore_entries", target_id=existing.id,
            proposed_change={
                "name": name, "field": "description",
                "old_value": old_value, "new_value": new_value,
            },
            reason=l.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    return rows


def extract_chapter(
    db: Session,
    *,
    chapter_id: int,
    router: ModelRouter = default_router,
) -> ExtractionResult:
    """Extract summary + entity changes from a chapter. Atomic transaction.

    Raises:
        ChapterNotFoundError: chapter does not exist.
        ExtractionError: LLM returned non-JSON or is missing the summary field.
    """
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)

    project = db.get(Project, chapter.project_id)
    existing_characters = list(db.scalars(
        select(Character).where(Character.project_id == chapter.project_id)
    ))
    existing_lore = list(db.scalars(
        select(LoreEntry).where(LoreEntry.project_id == chapter.project_id)
    ))

    system_prompt = render("extractor/system.j2")
    user_prompt = render(
        "extractor/user.j2",
        project=project,
        chapter=chapter,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
    )

    request = LLMRequest(
        model_task="extractor",
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
        temperature=0.1,
    )

    _, model_name = router.resolve_model("extractor")
    response = router.complete(request)

    # Parse JSON
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ExtractionError(
            f"LLM returned non-JSON: {e}; response={response.text[:500]}"
        )

    summary = (parsed.get("summary") or "").strip()
    if not summary:
        raise ExtractionError("LLM response missing 'summary' field")

    # Build pending rows (no DB write yet)
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}) or {},
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
    )

    new_hash = hashlib.sha256((chapter.content or "").encode()).hexdigest()

    # Audit log row
    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=chapter.project_id,
        beat_text="(extraction)",
        instruction="",
        involved_character_ids=[],
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "existing_chars": len(existing_characters),
            "existing_lore": len(existing_lore),
        },
        generated_text=response.text,
        model=model_name,
        model_task="extractor",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        stop_reason=response.stop_reason,
        status="done",
        started_at=_now(),
        finished_at=_now(),
    )

    try:
        db.add(log)
        db.flush()  # get log.id
        for p in pending_rows:
            p.extractor_log_id = log.id

        # Delete old pending rows for this chapter (only status='pending').
        # Accepted / rejected rows are preserved across re-extraction.
        db.execute(delete(PendingUpdate).where(
            PendingUpdate.chapter_id == chapter_id,
            PendingUpdate.status == "pending",
        ))

        # Insert new
        for p in pending_rows:
            db.add(p)

        # Update chapter
        chapter.summary = summary
        chapter.content_hash = new_hash
        chapter.status = "final"

        db.commit()
    except Exception:
        db.rollback()
        raise

    return ExtractionResult(
        chapter_id=chapter_id,
        summary=summary,
        pending_created=len(pending_rows),
        log_id=log.id,
    )
