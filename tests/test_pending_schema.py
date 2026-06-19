def test_pending_updates_table_registered():
    import app.memory.schema  # noqa: F401 — registers tables on Base.metadata
    from app.memory.base import Base
    assert "pending_updates" in Base.metadata.tables


def test_extraction_error_is_exception():
    from app.memory.errors import ExtractionError
    err = ExtractionError("bad json")
    assert isinstance(err, Exception)
    assert "bad json" in str(err)
