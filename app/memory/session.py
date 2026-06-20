from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.memory.base import Base


def _build_engine(db_path: Path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # M3b: load sqlite-vec extension
            import sqlite_vec
            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)
        finally:
            cursor.close()

    return engine


engine = _build_engine(settings.db_path)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    # 触发所有模型导入，确保 Base.metadata 已注册所有表
    import app.memory.schema  # noqa: F401
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
