import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import ExtractionResult, extract_chapter
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.memory.schema import Chapter, PendingUpdate, Project


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor tests."""
    from sqlalchemy import text

    from app.memory import session as session_module
    from app.memory.session import _build_engine, init_db
    from sqlalchemy.orm import sessionmaker

    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
    # M3b: create vec_chunks virtual table. Base.metadata.create_all doesn't
    # cover virtual tables; cosine metric matches the migration (Task 7 finding:
    # sqlite-vec defaults to L2, so the metric must be declared explicitly).
    with new_engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            "embedding FLOAT[1024] distance_metric=cosine)"
        ))
        conn.commit()
    with new_session() as s:
        yield s


def _seed_chapter(db_session, content="夜色压在屋脊上。李雷推开残月酒馆的门。"):
    p = Project(title="夜行记", genre="奇幻", premise="复仇")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="第二章", content=content)
    db_session.add(ch)
    db_session.commit()
    return p, ch


def _fake_router(response_text: str):
    """Build a fake router that returns a fixed LLMResponse + embeddings."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(
        return_value=LLMResponse(
            text=response_text,
            input_tokens=100,
            output_tokens=200,
            stop_reason="end_turn",
        )
    )
    # M3b: default embed returns 1 vector per call (1024-dim to match vec_chunks).
    # Per-test overrides take precedence for multi-chunk cases.
    fake.embed = MagicMock(return_value=[[0.1] * 1024])
    return fake


def test_extract_creates_summary_and_pending(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "李雷进入酒馆。",
        "entities": {
            "new_characters": [
                {"name": "韩梅", "role": "supporting", "description": "酒馆老板娘"}
            ],
            "updated_characters": [],
            "new_lore": [
                {"type": "location", "name": "残月酒馆", "description": "青石城南门"}
            ],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert isinstance(result, ExtractionResult)
    assert result.chapter_id == ch.id
    assert result.pending_created == 2  # 1 char + 1 lore
    assert result.log_id > 0

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == "李雷进入酒馆。"
    assert chapter.status == "final"
    assert chapter.content_hash  # sha256 of content

    pendings = list(db_session.query(PendingUpdate).filter_by(chapter_id=ch.id))
    assert len(pendings) == 2
    ops = {(p.operation, p.target_table) for p in pendings}
    assert ("create", "characters") in ops
    assert ("create", "lore_entries") in ops


def test_extract_no_entities(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "无变化。",
        "entities": {
            "new_characters": [],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0
    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == "无变化。"
    assert chapter.status == "final"


def test_extract_invalid_json_rolls_back(db_session):
    p, ch = _seed_chapter(db_session)
    # Set chapter to a known initial state
    ch.summary = "old"
    ch.status = "draft"
    db_session.commit()

    fake_router = _fake_router("not json {{")
    with pytest.raises(ExtractionError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    # Untouched
    assert chapter.summary == "old"
    assert chapter.status == "draft"
    # No pending rows
    assert db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).count() == 0


def test_extract_missing_summary_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({"entities": {}}))  # no summary
    with pytest.raises(ExtractionError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)


def test_extract_unknown_role_defaults_extra(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [
                {"name": "X", "role": "主角", "description": "y"}
            ],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    pending = db_session.query(PendingUpdate).filter_by(
        chapter_id=ch.id, target_table="characters"
    ).one()
    assert pending.proposed_change["role"] == "extra"


def test_extract_unknown_lore_type_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [],
            "new_lore": [
                {"type": "dynasty", "name": "X", "description": "y"},
                {"type": "location", "name": "Z", "description": "w"}
            ],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 1  # dynasty skipped, Z kept


def test_extract_empty_name_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [
                {"name": "", "role": "extra", "description": "y"}
            ],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0


def test_extract_update_existing_resolves_target_id(db_session):
    from app.memory.schema import Character
    p, ch = _seed_chapter(db_session)
    char = Character(project_id=p.id, name="李雷", role="protagonist", background="old bg")
    db_session.add(char)
    db_session.commit()

    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [
                {"name": "李雷", "field": "background", "new_value": "new bg"}
            ],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    pending = db_session.query(PendingUpdate).filter_by(
        chapter_id=ch.id, target_table="characters"
    ).one()
    assert pending.operation == "update"
    assert pending.target_id == char.id
    assert pending.proposed_change["old_value"] == "old bg"
    assert pending.proposed_change["new_value"] == "new bg"


def test_extract_update_unknown_name_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [
                {"name": "不存在的人", "field": "background", "new_value": "x"}
            ],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0


def test_extract_rerun_deletes_old_pending(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router_1 = _fake_router(json.dumps({
        "summary": "first",
        "entities": {
            "new_characters": [{"name": "A", "role": "extra", "description": "x"}],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router_1)
    # Simulate user accepting one
    pending_a = db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).one()
    pending_a.status = "accepted"
    db_session.commit()

    # Rerun
    fake_router_2 = _fake_router(json.dumps({
        "summary": "second",
        "entities": {
            "new_characters": [{"name": "B", "role": "extra", "description": "y"}],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router_2)

    pendings = list(db_session.query(PendingUpdate).filter_by(chapter_id=ch.id))
    # accepted A stays + new pending B
    statuses = {p.proposed_change["name"]: p.status for p in pendings}
    assert statuses == {"A": "accepted", "B": "pending"}


def test_extract_writes_generation_log(db_session):
    from app.memory.schema import GenerationLog
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x", "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    log = db_session.get(GenerationLog, result.log_id)
    assert log is not None
    assert log.model_task == "extractor"
    assert log.beat_text == "(extraction)"
    assert log.generated_text  # the JSON


def test_extract_chapter_not_found(db_session):
    fake_router = _fake_router("{}")
    with pytest.raises(ChapterNotFoundError):
        extract_chapter(db_session, chapter_id=99999, router=fake_router)


# ============================================================
# M3b: chunking + embedding integration
# ============================================================


def test_extract_creates_chunks(db_session):
    """After extract_chapter, chunk_meta should have rows for the chapter."""
    from app.memory.schema import ChunkMeta

    p, ch = _seed_chapter(db_session, content="第一段。\n\n第二段。\n\n第三段。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    # embed returns 3 vectors (one per chunk)
    fake_router.embed = MagicMock(return_value=[[0.1] * 1024] * 3)

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    chunks = db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).all()
    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_extract_writes_embeddings(db_session):
    """After extract_chapter, vec_chunks should have rows for each chunk."""
    from sqlalchemy import text

    p, ch = _seed_chapter(db_session, content="段落一。\n\n段落二。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024, [0.6] * 1024])

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    rows = db_session.execute(text("SELECT count() FROM vec_chunks")).scalar()
    assert rows == 2


def test_extract_rerun_overwrites_chunks(db_session):
    """Re-finalize should delete old chunks and write new ones."""
    from app.memory.schema import ChunkMeta

    p, ch = _seed_chapter(db_session, content="段落一。\n\n段落二。")
    fake_router = _fake_router(json.dumps({
        "summary": "first",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock(return_value=[[0.1] * 1024] * 2)
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 2

    # Re-run with different content (4 paragraphs)
    ch.content = "新内容。\n\n段落二。\n\n段落三。\n\n段落四。"
    db_session.commit()
    fake_router.embed = MagicMock(return_value=[[0.2] * 1024] * 4)
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "second",
            "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    # 4 new chunks (2 old deleted + 4 new written)
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 4


def test_extract_no_content_no_chunks(db_session):
    """Empty chapter content → 0 chunks, no embedding call."""
    from app.memory.schema import ChunkMeta

    p, ch = _seed_chapter(db_session, content="")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock()

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 0
    fake_router.embed.assert_not_called()


def test_extract_embedding_failure_rolls_back(db_session):
    """If embed() raises, the entire finalize should roll back."""
    from app.memory.schema import ChunkMeta, PendingUpdate

    p, ch = _seed_chapter(db_session, content="段落内容。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [{"name": "X", "role": "extra", "description": "y"}],
            "updated_characters": [], "new_lore": [], "updated_lore": [],
        }
    }))
    fake_router.embed = MagicMock(side_effect=RuntimeError("embedding API down"))

    with pytest.raises(RuntimeError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    # Nothing should be committed
    db_session.expire_all()
    assert db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).count() == 0
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 0
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == ""  # not set
    assert chapter.status != "final"


def test_extract_batch_split_for_long_chapter(db_session):
    """Chapter with > 50 paragraphs → embed() called multiple times (batch=50)."""
    from app.memory.schema import ChunkMeta

    # 60 paragraphs
    content = "\n\n".join(f"段落 {i}。" for i in range(60))
    p, ch = _seed_chapter(db_session, content=content)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    # First batch returns 50 vectors, second batch returns 10.
    fake_router.embed = MagicMock(
        side_effect=[[ [0.1] * 1024 ] * 50, [ [0.2] * 1024 ] * 10]
    )

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert fake_router.embed.call_count == 2
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 60
