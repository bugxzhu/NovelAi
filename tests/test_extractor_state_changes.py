"""M3c-B: state_changes branch of _build_pending_rows + extract_chapter."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import _build_pending_rows, ALLOWED_CHARACTER_FIELDS
from app.llm.base import LLMResponse
from app.memory.schema import Character, Chapter, PendingUpdate, Project


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )


def _seed_existing(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=5, title="第五章", content="x")
    db_session.add(ch); db_session.flush()
    c = Character(project_id=p.id, name="李雷", role="protagonist",
                  current_state="警惕")
    db_session.add(c); db_session.flush()
    return p, ch, c


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor state_changes tests."""
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


def test_current_state_removed_from_allowed_character_fields():
    """M3c-B: current_state changes go through state_changes, not updated_characters."""
    assert "current_state" not in ALLOWED_CHARACTER_FIELDS
    assert "background" in ALLOWED_CHARACTER_FIELDS


def test_build_pending_rows_state_changes_creates_soft_fact(db_session):
    """state_changes produce update_type='soft_fact', target_table='character_states', auto=False."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="claude-haiku-4-5",
        state_changes=[
            {"character_name": "李雷",
             "state_snapshot": "愤怒且受伤",
             "change_summary": "被韩梅伏击"},
        ],
    )
    state_rows = [r for r in rows if r.target_table == "character_states"]
    assert len(state_rows) == 1
    r = state_rows[0]
    assert r.update_type == "soft_fact"
    assert r.operation == "create"
    assert r.target_id is None
    assert r.auto is False
    assert r.proposed_change["character_id"] == c.id
    assert r.proposed_change["character_name"] == "李雷"
    assert r.proposed_change["state_snapshot"] == "愤怒且受伤"
    assert r.proposed_change["change_summary"] == "被韩梅伏击"


def test_build_pending_rows_state_changes_unknown_character_skipped(db_session):
    """character_name not in existing → skip silently."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "鬼魂",  # not in existing
             "state_snapshot": "x", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_empty_snapshot_skipped(db_session):
    """Empty state_snapshot → skip."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "  ", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_empty_name_skipped(db_session):
    """Empty character_name → skip."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "", "state_snapshot": "x", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_missing_change_summary_ok(db_session):
    """Missing change_summary → defaults to empty string."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "x"},
            # change_summary missing
        ],
    )
    assert len(rows) == 1
    assert rows[0].proposed_change["change_summary"] == ""


def test_build_pending_rows_state_changes_missing_field_ok(db_session):
    """Missing state_changes field entirely → treated as empty list, no error."""
    p, ch, c = _seed_existing(db_session)
    # Call WITHOUT passing state_changes kwarg — should default to []
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
    )
    assert rows == []


def test_build_pending_rows_multiple_state_changes_same_character(db_session):
    """Same character, multiple state changes in one chapter → multiple rows (append-only)."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "中段：愤怒",
             "change_summary": "e1"},
            {"character_name": "李雷", "state_snapshot": "结尾：决绝",
             "change_summary": "e2"},
        ],
    )
    assert len(rows) == 2
    assert all(r.target_table == "character_states" for r in rows)


def test_extract_chapter_writes_state_changes_pending(db_session, monkeypatch):
    """End-to-end: extract_chapter with mock LLM produces state_changes pending rows."""
    from app.agents.extractor import extract_chapter

    p, ch, c = _seed_existing(db_session)
    db_session.commit()

    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=_llm_response({
        "summary": "摘要",
        "entities": {"new_characters": [], "updated_characters": [],
                     "new_lore": [], "updated_lore": []},
        "state_changes": [
            {"character_name": "李雷",
             "state_snapshot": "愤怒", "change_summary": "被伏击"},
        ],
    }))
    # M3b: embed() needed for chunking branch
    fake.embed = MagicMock(return_value=[[0.0] * 1024])

    result = extract_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.pending_created == 1

    rows = list(db_session.query(PendingUpdate).filter(
        PendingUpdate.target_table == "character_states"
    ))
    assert len(rows) == 1
    assert rows[0].update_type == "soft_fact"
    assert rows[0].auto is False
    assert rows[0].proposed_change["character_id"] == c.id
