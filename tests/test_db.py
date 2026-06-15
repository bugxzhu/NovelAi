from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.memory.session import SessionLocal, init_db


def _rebind_engine(tmp_path, monkeypatch):
    """Rebuild engine/SessionLocal bound to an isolated db file."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    from app.memory import session as session_module
    new_engine = session_module._build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    return db_file, new_session


def test_init_db_creates_file(tmp_path, monkeypatch):
    db_file, _ = _rebind_engine(tmp_path, monkeypatch)
    init_db()
    assert db_file.exists()


def test_session_can_query_sqlite_version(tmp_path, monkeypatch):
    _, new_session = _rebind_engine(tmp_path, monkeypatch)
    init_db()
    with new_session() as session:
        version = session.execute(text("SELECT sqlite_version()")).scalar()
        assert version is not None


def test_pragmas_are_applied(tmp_path, monkeypatch):
    db_file, new_session = _rebind_engine(tmp_path, monkeypatch)
    init_db()
    with new_session() as s:
        assert s.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_init_db_creates_m1_tables(tmp_path, monkeypatch):
    _rebind_engine(tmp_path, monkeypatch)
    init_db()
    from app.memory.base import Base

    expected = {"projects", "world_overview", "lore_entries", "characters", "chapters"}
    actual = set(Base.metadata.tables.keys())
    assert expected.issubset(actual), f"missing tables: {expected - actual}"
