"""Schema-level tests for Event ORM (M3c-C)."""
import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401
from app.memory.schema import (
    Chapter, Character, Event, LoreEntry, Project,
)


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "event_test.db"
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


def _seed_project_chapter(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    return p, ch


def test_event_table_columns(db_session):
    """Verify the events table has the expected columns."""
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("events")}
    expected = {
        "id", "project_id", "chapter_id",
        "title", "description",
        "involved_characters", "location_id", "plot_line_id",
        "foreshadows",
        "extractor_log_id", "pending_update_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_event_indexes_exist(db_session):
    """Verify indexes were created."""
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("events")}
    assert "idx_events_project" in index_names
    assert "idx_events_chapter" in index_names


def test_event_defaults_empty_arrays(db_session):
    """involved_characters and foreshadows default to empty arrays."""
    p, ch = _seed_project_chapter(db_session)
    e = Event(
        project_id=p.id, chapter_id=ch.id,
        title="测试", description="x",
    )
    db_session.add(e); db_session.commit()
    assert e.involved_characters == []
    assert e.foreshadows == []


def test_event_insert_and_query(db_session):
    """Round-trip with involved_characters + foreshadows JSON arrays."""
    p, ch = _seed_project_chapter(db_session)
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()

    e1 = Event(
        project_id=p.id, chapter_id=ch.id,
        title="伏击", description="x",
        involved_characters=[c1.id, c2.id],
    )
    e2 = Event(
        project_id=p.id, chapter_id=ch.id,
        title="复仇", description="y",
        foreshadows=[],
    )
    db_session.add_all([e1, e2]); db_session.flush()
    e2.foreshadows = [e1.id]
    db_session.commit()

    rows = list(db_session.scalars(select(Event).order_by(Event.id)))
    assert len(rows) == 2
    assert rows[0].involved_characters == [c1.id, c2.id]
    assert rows[1].foreshadows == [e1.id]


def test_event_cascade_delete_with_chapter(db_session):
    """Deleting a chapter cascades to its events."""
    p, ch = _seed_project_chapter(db_session)
    e = Event(project_id=p.id, chapter_id=ch.id, title="x", description="y")
    db_session.add(e); db_session.commit()

    db_session.delete(ch)
    db_session.commit()

    rows = list(db_session.scalars(select(Event)))
    assert rows == []


def test_event_cascade_delete_with_project(db_session):
    """Deleting a project cascades to its events."""
    p, ch = _seed_project_chapter(db_session)
    e = Event(project_id=p.id, chapter_id=ch.id, title="x", description="y")
    db_session.add(e); db_session.commit()

    db_session.delete(p)
    db_session.commit()

    rows = list(db_session.scalars(select(Event)))
    assert rows == []
