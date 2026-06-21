"""M3c-C: events branch of _build_pending_rows + extract_chapter."""
import json
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import _build_pending_rows
from app.llm.base import LLMResponse
from app.memory.schema import (
    Character, Chapter, Event, LoreEntry, PendingUpdate, Project,
)


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )


def _seed(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=5, title="第五章", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷", role="protagonist")
    c2 = Character(project_id=p.id, name="韩梅", role="supporting")
    loc = LoreEntry(project_id=p.id, type="location", name="残月酒馆", description="")
    db_session.add_all([c1, c2, loc]); db_session.flush()
    return p, ch, c1, c2, loc


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor events tests."""
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


def test_build_pending_rows_events_creates_hard_fact(db_session):
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="claude-haiku-4-5",
        events=[
            {"title": "残月伏击", "description": "韩梅伏击李雷",
             "involved_character_names": ["李雷", "韩梅"],
             "location_name": "残月酒馆"},
        ],
    )
    event_rows = [r for r in rows if r.target_table == "events"]
    assert len(event_rows) == 1
    r = event_rows[0]
    assert r.update_type == "hard_fact"
    assert r.operation == "create"
    assert r.target_id is None
    assert r.auto is True  # hard fact
    pc = r.proposed_change
    assert pc["title"] == "残月伏击"
    assert pc["description"] == "韩梅伏击李雷"
    assert pc["involved_character_ids"] == [c1.id, c2.id]
    assert pc["involved_character_names"] == ["李雷", "韩梅"]
    assert pc["location_id"] == loc.id
    assert pc["location_name"] == "残月酒馆"


def test_build_pending_rows_events_unknown_character_skipped(db_session):
    """Unknown name in involved_character_names is skipped, but event still generated."""
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
        events=[
            {"title": "x", "description": "y",
             "involved_character_names": ["李雷", "鬼魂"]},
        ],
    )
    event_rows = [r for r in rows if r.target_table == "events"]
    assert len(event_rows) == 1
    assert event_rows[0].proposed_change["involved_character_ids"] == [c1.id]


def test_build_pending_rows_events_unknown_location_skipped(db_session):
    """Unknown location_name → location_id=None, event still generated."""
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
        events=[
            {"title": "x", "description": "y",
             "location_name": "不存在的地方"},
        ],
    )
    event_rows = [r for r in rows if r.target_table == "events"]
    assert len(event_rows) == 1
    assert event_rows[0].proposed_change["location_id"] is None
    assert event_rows[0].proposed_change["location_name"] == ""


def test_build_pending_rows_events_empty_title_skipped(db_session):
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
        events=[{"title": "  ", "description": "y"}],
    )
    assert rows == []


def test_build_pending_rows_events_empty_description_skipped(db_session):
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
        events=[{"title": "x", "description": ""}],
    )
    assert rows == []


def test_build_pending_rows_events_missing_kwarg_ok(db_session):
    """Not passing events kwarg → treated as empty list."""
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
    )
    assert rows == []


def test_build_pending_rows_multiple_events_per_chapter(db_session):
    """Multiple events in same chapter → multiple pendings (append-only)."""
    p, ch, c1, c2, loc = _seed(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[loc],
        model_name="m",
        events=[
            {"title": "事件A", "description": "a"},
            {"title": "事件B", "description": "b"},
            {"title": "事件C", "description": "c"},
        ],
    )
    assert len(rows) == 3
    assert all(r.target_table == "events" for r in rows)


def test_extract_chapter_writes_events_pending(db_session):
    """End-to-end: extract_chapter with mock LLM produces events pending row."""
    from app.agents.extractor import extract_chapter

    p, ch, c1, c2, loc = _seed(db_session)

    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=_llm_response({
        "summary": "摘要",
        "entities": {"new_characters": [], "updated_characters": [],
                     "new_lore": [], "updated_lore": []},
        "state_changes": [],
        "relationship_changes": [],
        "events": [
            {"title": "残月伏击", "description": "韩梅伏击李雷",
             "involved_character_names": ["李雷"],
             "location_name": "残月酒馆"},
        ],
    }))
    fake.embed = MagicMock(return_value=[[0.0] * 1024])

    result = extract_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.pending_created == 1

    rows = list(db_session.query(PendingUpdate).filter(
        PendingUpdate.target_table == "events"
    ))
    assert len(rows) == 1
    assert rows[0].update_type == "hard_fact"
    assert rows[0].auto is True
    assert rows[0].proposed_change["title"] == "残月伏击"
    assert rows[0].proposed_change["location_id"] == loc.id
