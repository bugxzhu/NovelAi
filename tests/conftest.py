import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.settings.db_path", db_file)
    # 重新构建 engine 与 SessionLocal 绑定到 tmp_path
    from app.memory import session as session_module
    from app.memory.session import _build_engine
    from sqlalchemy.orm import sessionmaker
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    monkeypatch.setattr("app.api.deps.SessionLocal", new_session)

    from app.main import app
    with TestClient(app) as c:
        yield c
