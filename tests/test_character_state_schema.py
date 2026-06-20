"""Schema-level tests for CharacterState ORM (M3c-B)."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "char_state_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        # Match production (_build_engine): SQLite needs this pragma for
        # ForeignKey ondelete=CASCADE to actually fire.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def test_character_state_table_columns(db_session):
    """Verify the character_states table has the expected columns."""
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("character_states")}
    expected = {
        "id", "character_id", "chapter_id",
        "state_snapshot", "change_summary",
        "extractor_log_id", "pending_update_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_character_state_indexes_exist(db_session):
    """Verify indexes were created."""
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("character_states")}
    assert "idx_char_state_char_chapter" in index_names
    assert "idx_char_state_chapter" in index_names


def test_character_state_insert_and_query(db_session):
    """Round-trip: insert a row and read it back."""
    from app.memory.schema import Character, CharacterState, Chapter, Project
    p = Project(title="T", genre="", premise="")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch)
    db_session.flush()
    c = Character(project_id=p.id, name="李雷")
    db_session.add(c)
    db_session.flush()

    s = CharacterState(
        character_id=c.id, chapter_id=ch.id,
        state_snapshot="愤怒", change_summary="被背叛",
    )
    db_session.add(s)
    db_session.commit()

    rows = list(db_session.scalars(
        select(CharacterState).where(CharacterState.character_id == c.id)
    ))
    assert len(rows) == 1
    assert rows[0].state_snapshot == "愤怒"
    assert rows[0].change_summary == "被背叛"
    assert rows[0].extractor_log_id is None
    assert rows[0].pending_update_id is None


def test_character_state_cascade_delete_with_character(db_session):
    """Deleting a character cascades to their states."""
    from app.memory.schema import Character, CharacterState, Chapter, Project
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c = Character(project_id=p.id, name="李雷")
    db_session.add(c); db_session.flush()
    s = CharacterState(
        character_id=c.id, chapter_id=ch.id,
        state_snapshot="x", change_summary="",
    )
    db_session.add(s); db_session.commit()

    db_session.delete(c)
    db_session.commit()

    rows = list(db_session.scalars(select(CharacterState)))
    assert rows == []
