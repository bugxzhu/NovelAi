"""M3c-A: relationship_changes branch of _build_pending_rows + extract_chapter."""
import json
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import _build_pending_rows
from app.llm.base import LLMResponse
from app.memory.schema import Character, Chapter, PendingUpdate, Project, Relationship


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )


def _seed_two_characters(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=5, title="第五章", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷", role="protagonist")
    c2 = Character(project_id=p.id, name="韩梅", role="supporting")
    db_session.add_all([c1, c2]); db_session.flush()
    return p, ch, c1, c2


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor relationship_changes tests."""
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
    # cover virtual tables.
    with new_engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            "embedding FLOAT[1024] distance_metric=cosine)"
        ))
        conn.commit()
    with new_session() as s:
        yield s


def test_build_pending_rows_relationship_changes_creates_soft_fact(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="claude-haiku-4-5",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "仇人", "strength": -0.8,
             "description": "李雷决心复仇",
             "change_summary": "韩梅伏击李雷"},
        ],
    )
    rel_rows = [r for r in rows if r.target_table == "relationships"]
    assert len(rel_rows) == 1
    r = rel_rows[0]
    assert r.update_type == "soft_fact"
    assert r.operation == "create"
    assert r.target_id is None
    assert r.auto is False
    pc = r.proposed_change
    assert pc["from_character_id"] == c1.id
    assert pc["from_character_name"] == "李雷"
    assert pc["to_character_id"] == c2.id
    assert pc["to_character_name"] == "韩梅"
    assert pc["type"] == "仇人"
    assert pc["strength"] == -0.8
    assert pc["description"] == "李雷决心复仇"
    assert pc["change_summary"] == "韩梅伏击李雷"
    assert pc["valid_from_chapter"] == ch.id


def test_build_pending_rows_relationship_unknown_endpoint_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "鬼魂",
             "type": "x", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_self_reference_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "李雷",
             "type": "自我", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_empty_type_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "  ", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_strength_clamped_high(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": 1.5},
        ],
    )
    assert rows[0].proposed_change["strength"] == 1.0


def test_build_pending_rows_relationship_strength_clamped_low(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": -2.0},
        ],
    )
    assert rows[0].proposed_change["strength"] == -1.0


def test_build_pending_rows_relationship_invalid_strength_defaults_zero(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": "abc"},
        ],
    )
    assert rows[0].proposed_change["strength"] == 0.0


def test_build_pending_rows_relationship_changes_missing_kwarg_ok(db_session):
    """Not passing relationship_changes kwarg → treated as empty list."""
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
    )
    assert rows == []


def test_build_pending_rows_relationship_reverse_direction_independent(db_session):
    """A→B and B→A in same chapter both produce pendings."""
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "暗恋", "strength": 0.7},
            {"from_character_name": "韩梅", "to_character_name": "李雷",
             "type": "朋友", "strength": 0.3},
        ],
    )
    assert len(rows) == 2
    assert all(r.target_table == "relationships" for r in rows)


def test_extract_chapter_writes_relationship_pending(db_session, monkeypatch):
    """End-to-end: extract_chapter with mock LLM produces relationship pending row."""
    from app.agents.extractor import extract_chapter

    p, ch, c1, c2 = _seed_two_characters(db_session)

    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=_llm_response({
        "summary": "摘要",
        "entities": {"new_characters": [], "updated_characters": [],
                     "new_lore": [], "updated_lore": []},
        "state_changes": [],
        "relationship_changes": [
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "仇人", "strength": -0.8,
             "description": "决心复仇",
             "change_summary": "伏击"},
        ],
    }))
    fake.embed = MagicMock(return_value=[[0.0] * 1024])

    result = extract_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.pending_created == 1

    rows = list(db_session.query(PendingUpdate).filter(
        PendingUpdate.target_table == "relationships"
    ))
    assert len(rows) == 1
    assert rows[0].update_type == "soft_fact"
    assert rows[0].auto is False
    assert rows[0].proposed_change["from_character_id"] == c1.id
    assert rows[0].proposed_change["to_character_id"] == c2.id
