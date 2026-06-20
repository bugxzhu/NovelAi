"""Schema-level tests for Relationship ORM (M3c-A)."""
import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401
from app.memory.schema import (
    Chapter, Character, Project, Relationship,
)


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "rel_test.db"
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


def _seed_project_and_two_characters(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    return p, c1, c2


def test_relationship_table_columns(db_session):
    """Verify the relationships table has the expected columns."""
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("relationships")}
    expected = {
        "id", "project_id", "from_char_id", "to_char_id",
        "type", "strength", "description",
        "valid_from_chapter", "valid_to_chapter",
        "change_summary", "extractor_log_id", "pending_update_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_relationship_indexes_exist(db_session):
    """Verify indexes (including partial unique) were created."""
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("relationships")}
    assert "idx_rel_from_to_current" in index_names
    assert "idx_rel_project" in index_names
    assert "uq_rel_current" in index_names


def test_relationship_partial_unique_blocks_second_current(db_session):
    """Same from→to direction cannot have two valid_to=NULL rows."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()

    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5, description="",
        valid_from_chapter=ch.id,
    ))
    db_session.commit()

    # Second current-valid for same direction should fail
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.5, description="",
        valid_from_chapter=ch.id,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_relationship_partial_unique_allows_history(db_session):
    """Same direction can have multiple rows if older ones have valid_to set."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch1 = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2", content="x")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # Old version (soft-closed)
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5,
        valid_from_chapter=ch1.id, valid_to_chapter=ch2.id,
    ))
    # New current version
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.5,
        valid_from_chapter=ch2.id,
    ))
    db_session.commit()  # should not raise

    rows = list(db_session.scalars(
        select(Relationship).where(
            Relationship.from_char_id == c1.id,
            Relationship.to_char_id == c2.id,
        )
    ))
    assert len(rows) == 2


def test_relationship_reverse_direction_independent(db_session):
    """A→B and B→A are independent records (both can be current-valid)."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()

    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="暗恋", strength=0.7,
        valid_from_chapter=ch.id,
    ))
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c2.id, to_char_id=c1.id,
        type="朋友", strength=0.3,
        valid_from_chapter=ch.id,
    ))
    db_session.commit()  # should NOT raise — opposite directions


def test_relationship_cascade_delete_with_character(db_session):
    """Deleting a character cascades to all their relationships."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5,
        valid_from_chapter=ch.id,
    ))
    db_session.commit()

    db_session.delete(c1)
    db_session.commit()

    rows = list(db_session.scalars(select(Relationship)))
    assert rows == []
