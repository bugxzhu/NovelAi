from datetime import UTC, datetime

from app.models.generation import (
    GenerateRequest,
    GenerationLogDetail,
    GenerationLogRead,
)


def test_generation_log_table_registered():
    import app.memory.schema  # noqa: F401  ensure ORM models are registered
    from app.memory.base import Base
    assert "generation_logs" in Base.metadata.tables


def test_generate_request_defaults():
    req = GenerateRequest(beat_text="x", involved_character_ids=[1])
    assert req.instruction == ""
    assert req.location_id is None
    assert req.model_task == "writer_long"
    assert req.max_tokens == 4096


def test_generate_request_dedups_character_ids():
    req = GenerateRequest(
        beat_text="x",
        involved_character_ids=[3, 1, 3, 2, 1],
    )
    assert req.involved_character_ids == [3, 1, 2]


def test_generate_request_rejects_too_many_chars():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GenerateRequest(
            beat_text="x",
            involved_character_ids=list(range(21)),
        )


def test_generate_request_rejects_empty_beat():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GenerateRequest(beat_text="", involved_character_ids=[1])


def test_generation_log_read_minimal():
    now = datetime.now(UTC)
    log = GenerationLogRead(
        id=1, chapter_id=1, project_id=1,
        beat_text="x", model="claude-sonnet-4-6",
        status="done", input_tokens=10, output_tokens=5,
        started_at=now, finished_at=now,
        created_at=now, updated_at=now,
    )
    assert log.id == 1


def test_generation_log_detail_has_prompts():
    now = datetime.now(UTC)
    log = GenerationLogDetail(
        id=1, chapter_id=1, project_id=1,
        beat_text="x", model="claude-sonnet-4-6",
        status="done", input_tokens=10, output_tokens=5,
        started_at=now, finished_at=now,
        created_at=now, updated_at=now,
        instruction="", involved_character_ids=[1],
        location_id=None, system_prompt="S", user_prompt="U",
        context_summary={}, generated_text="T",
        model_task="writer_long", stop_reason="end_turn",
    )
    assert log.system_prompt == "S"
    assert log.generated_text == "T"
