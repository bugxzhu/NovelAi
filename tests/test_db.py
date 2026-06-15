from sqlalchemy import text
from sqlalchemy.orm import Session

from app.memory.session import SessionLocal, init_db


def test_init_db_creates_file(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    init_db()
    assert db_file.exists()


def test_session_can_query_sqlite_version():
    init_db()
    with SessionLocal() as session:
        version = session.execute(text("SELECT sqlite_version()")).scalar()
        assert version is not None
