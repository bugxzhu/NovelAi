"""M4b-1: story_milestones schema tests."""
import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401
from app.memory.schema import Project, StoryMilestone


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "story_milestone_test.db"
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


def test_story_milestone_table_columns(db_session):
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("story_milestones")}
    expected = {
        "id", "project_id", "order_index", "type", "title", "description",
        "chapter_start", "chapter_end", "status",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_story_milestone_indexes_exist(db_session):
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("story_milestones")}
    assert "idx_milestones_project" in index_names


def test_story_milestone_defaults(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    m = StoryMilestone(project_id=p.id, title="第一转折")
    db_session.add(m); db_session.commit()
    assert m.type == "里程碑"
    assert m.status == "planned"
    assert m.order_index == 0
    assert m.description == ""


def test_story_milestone_cascade_delete_with_project(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    m = StoryMilestone(project_id=p.id, title="X")
    db_session.add(m); db_session.commit()
    db_session.delete(p)
    db_session.commit()
    assert list(db_session.scalars(select(StoryMilestone))) == []
