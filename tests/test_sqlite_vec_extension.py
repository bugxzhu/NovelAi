def test_extension_loads_via_session(tmp_path, monkeypatch):
    """The session engine should auto-load vec0 on connect."""
    from sqlalchemy import create_engine, text

    from app.memory import session as session_module
    from app.memory.session import _build_engine

    db_file = tmp_path / "ext_test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    monkeypatch.setattr(session_module, "engine", new_engine)

    with new_engine.connect() as conn:
        version = conn.execute(text("SELECT vec_version()")).scalar()
    assert version is not None
    assert len(version) > 0
