def test_chunk_meta_table_registered():
    import app.memory.schema  # noqa: F401
    from app.memory.base import Base
    assert "chunk_meta" in Base.metadata.tables


def test_chunk_meta_unique_constraint():
    """The (chapter_id, chunk_index) unique constraint should be present."""
    import app.memory.schema  # noqa: F401
    from app.memory.base import Base
    table = Base.metadata.tables["chunk_meta"]
    constraint_names = {c.name for c in table.constraints}
    assert "uq_chunk_chapter_index" in constraint_names
