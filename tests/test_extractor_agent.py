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
    """Build a fake router that returns a fixed LLMResponse."""
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
