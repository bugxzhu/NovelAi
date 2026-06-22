from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.agents.retrieval import assemble_retrieval_context
from app.memory.retrieval import ContextBundle, assemble_context
from app.memory.schema import Chapter, GenerationLog


def _now() -> datetime:
    return datetime.now(UTC)


def _serialize_context_summary(bundle: ContextBundle) -> dict:
    """Structured summary for storage/diff (smaller than full bundle)."""
    return {
        "project_id": bundle.project.id,
        "project_title": bundle.project.title,
        "world_overview_present": bundle.world_overview is not None,
        "characters": [
            {"id": c.id, "name": c.name, "role": c.role}
            for c in bundle.characters
        ],
        "relationships": [
            {"from": r.from_name, "to": r.to_name, "type": r.type}
            for r in bundle.relationships
        ],
        "faction_lore": [{"id": f.id, "name": f.name} for f in bundle.faction_lore],
        "location_lore": [{"id": l.id, "name": l.name} for l in bundle.location_lore],
        "recent_chapter_summaries": [
            {"chapter_id": s.chapter_id, "title": s.title}
            for s in bundle.recent_chapter_summaries
        ],
    }


def _serialize_context_bundle(bundle: ContextBundle) -> dict:
    """Full serialization for the SSE context event."""
    return {
        "project": {
            "id": bundle.project.id,
            "title": bundle.project.title,
            "genre": bundle.project.genre,
            "main_theme": bundle.project.main_theme,
            "tone": bundle.project.tone,
            "premise": bundle.project.premise,
        },
        "world_overview": {
            "setting_era": bundle.world_overview.setting_era,
            "geography_summary": bundle.world_overview.geography_summary,
            "history_summary": bundle.world_overview.history_summary,
            "culture_summary": bundle.world_overview.culture_summary,
            "power_system": bundle.world_overview.power_system,
            "rules_and_taboos": bundle.world_overview.rules_and_taboos,
        } if bundle.world_overview else None,
        "characters": [
            {
                "id": c.id, "name": c.name, "role": c.role,
                "current_state": bundle.character_states[c.id].current_state,
            }
            for c in bundle.characters
        ],
        "relationships": [
            {"from": r.from_name, "to": r.to_name, "type": r.type,
             "strength": r.strength, "description": r.description}
            for r in bundle.relationships
        ],
        "faction_lore": [{"id": f.id, "name": f.name, "description": f.description}
                         for f in bundle.faction_lore],
        "location_lore": [{"id": l.id, "name": l.name, "description": l.description}
                          for l in bundle.location_lore],
        "recent_chapter_summaries": [
            {"chapter_id": s.chapter_id, "order_index": s.order_index,
             "title": s.title, "summary": s.summary}
            for s in bundle.recent_chapter_summaries
        ],
        "retrieved_chunks": [
            {
                "chunk_id": rc.chunk_id,
                "chapter_id": rc.chapter_id,
                "chapter_title": rc.chapter_title,
                "chunk_type": rc.chunk_type,
                "text": rc.text,
                "score": round(rc.score, 4),
            }
            for rc in bundle.retrieved_chunks
        ],
    }


@dataclass
class PreparedGeneration:
    log: GenerationLog
    context_bundle: ContextBundle
    system_prompt: str
    user_prompt: str
    llm_request: LLMRequest
    model_name: str


def prepare_generation(
    db: Session,
    *,
    chapter_id: int,
    beat_text: str,
    instruction: str,
    involved_character_ids: list[int],
    location_id: int | None,
    model_task: str,
    max_tokens: int,
    router: ModelRouter = default_router,
) -> PreparedGeneration:
    """Pre-stream phase. May raise ChapterNotFoundError / InvalidContextError."""
    bundle = assemble_context(
        db,
        chapter_id=chapter_id,
        beat_text=beat_text,
        involved_character_ids=involved_character_ids,
        location_id=location_id,
    )

    # M3b: vector retrieval layer
    character_names = [c.name for c in bundle.characters]
    query_text = beat_text
    if character_names:
        query_text = beat_text + " " + " ".join(character_names)

    retrieved = assemble_retrieval_context(
        db,
        current_chapter_id=chapter_id,
        query_text=query_text,
        router=router,
    )
    bundle.retrieved_chunks = retrieved

    system_prompt = render("writer/system.j2")
    user_prompt = render(
        "writer/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        characters=bundle.characters,
        character_states=bundle.character_states,
        relationships=bundle.relationships,
        faction_lore=bundle.faction_lore,
        location_lore=bundle.location_lore,
        plot_lines=bundle.plot_lines,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
        beat_text=beat_text,
        instruction=instruction,
        retrieved_chunks=retrieved,  # M3b new
        milestones=bundle.milestones,  # M4b-1 new
    )

    _, model_name = router.resolve_model(model_task)

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=bundle.project.id,
        beat_text=beat_text,
        instruction=instruction,
        involved_character_ids=list(involved_character_ids),
        location_id=location_id,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary=_serialize_context_summary(bundle),
        model=model_name,
        model_task=model_task,
        status="streaming",
        started_at=_now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return PreparedGeneration(
        log=log,
        context_bundle=bundle,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        llm_request=LLMRequest(
            model_task=model_task,
            system=system_prompt,
            user=user_prompt,
            max_tokens=max_tokens,
        ),
        model_name=model_name,
    )


def stream_generation(
    db: Session,
    prep: PreparedGeneration,
    *,
    router: ModelRouter = default_router,
) -> Iterator[dict]:
    """Yields meta → context → token* → done|error dicts. Updates log on terminal."""
    yield {
        "type": "meta",
        "generation_log_id": prep.log.id,
        "model": prep.model_name,
        "model_task": prep.log.model_task,
        "chapter_id": prep.log.chapter_id,
        "started_at": prep.log.started_at.isoformat(),
    }
    yield {
        "type": "context",
        "context_bundle": _serialize_context_bundle(prep.context_bundle),
    }

    generated_parts: list[str] = []
    for event in router.stream(prep.llm_request):
        if event.type == "token":
            generated_parts.append(event.text)
            yield {"type": "token", "text": event.text}
        elif event.type == "done":
            full_text = "".join(generated_parts)
            _finalize_done(db, prep.log.id, full_text, event)
            yield {
                "type": "done",
                "generation_log_id": prep.log.id,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "stop_reason": event.stop_reason,
            }
            return
        elif event.type == "error":
            _finalize_error(db, prep.log.id, event)
            yield {
                "type": "error",
                "message": event.error_message,
                "code": event.error_code,
            }
            return


def _finalize_done(db: Session, log_id: int, text: str, event) -> None:
    log = db.get(GenerationLog, log_id)
    if log is None:
        return
    log.generated_text = text
    log.input_tokens = event.input_tokens
    log.output_tokens = event.output_tokens
    log.stop_reason = event.stop_reason
    log.status = "done"
    log.finished_at = _now()

    # M2b: write back chapter default set
    chapter = db.get(Chapter, log.chapter_id)
    if chapter is not None:
        chapter.last_involved_character_ids = list(log.involved_character_ids)
        chapter.last_location_id = log.location_id

    db.commit()


def _finalize_error(db: Session, log_id: int, event) -> None:
    log = db.get(GenerationLog, log_id)
    if log is None:
        return
    log.stop_reason = event.error_code
    log.status = "failed"
    log.finished_at = _now()
    db.commit()
