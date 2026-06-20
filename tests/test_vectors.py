import struct

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401 register all ORM classes


def _make_vec(values: list[float]) -> bytes:
    """Serialize vector as raw float32 LE bytes (sqlite-vec format)."""
    return struct.pack(f"<{len(values)}f", *values)


@pytest.fixture
def db_session(tmp_path):
    """In-memory-style DB with vec_chunks virtual table created manually."""
    db_file = tmp_path / "vectors_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    # Load sqlite-vec on each connection
    import sqlite_vec
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _load_vec(dbapi_conn, _record):
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    # Create all ORM tables + vec_chunks virtual table.
    # distance_metric=cosine is required (sqlite-vec defaults to L2; see migration).
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            "embedding FLOAT[1024] distance_metric=cosine)"
        ))
        conn.commit()

    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def _seed_chapter(db_session):
    """Minimal chapter row so chunk_meta FK is valid."""
    from app.memory.schema import Chapter, Project
    p = Project(title="P")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch)
    db_session.commit()
    return ch.id


def test_insert_chunk_returns_id(db_session):
    from app.memory.vectors import insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="hello", char_count=5,
        embedding=[0.1] * 1024,
    )
    db_session.commit()
    assert rid > 0


def test_insert_chunk_writes_vec_table(db_session):
    from app.memory.vectors import insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="hello", char_count=5,
        embedding=[0.5] * 1024,
    )
    db_session.commit()
    rows = db_session.execute(
        text("SELECT rowid FROM vec_chunks WHERE rowid = :rid"),
        {"rid": rid},
    ).fetchall()
    assert len(rows) == 1


def test_delete_chapter_chunks_removes_both_tables(db_session):
    from app.memory.vectors import delete_chapter_chunks, insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="x", char_count=1,
        embedding=[0.1] * 1024,
    )
    db_session.commit()
    delete_chapter_chunks(db_session, cid)
    db_session.commit()

    from app.memory.schema import ChunkMeta
    assert db_session.query(ChunkMeta).filter_by(chapter_id=cid).count() == 0
    rows = db_session.execute(
        text("SELECT rowid FROM vec_chunks WHERE rowid = :rid"), {"rid": rid}
    ).fetchall()
    assert len(rows) == 0


def test_delete_chapter_chunks_preserves_other_chapters(db_session):
    from app.memory.schema import Chapter, Project, ChunkMeta
    from app.memory.vectors import delete_chapter_chunks, insert_chunk

    p = Project(title="P")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="C1")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2")
    db_session.add_all([ch1, ch2]); db_session.commit()

    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="a", char_count=1,
                 embedding=[0.1] * 1024)
    insert_chunk(db_session, chapter_id=ch2.id, chunk_index=0,
                 chunk_type="paragraph", text="b", char_count=1,
                 embedding=[0.2] * 1024)
    db_session.commit()

    delete_chapter_chunks(db_session, ch1.id)
    db_session.commit()

    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch1.id).count() == 0
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch2.id).count() == 1


def test_delete_nonexistent_chapter_noop(db_session):
    from app.memory.vectors import delete_chapter_chunks
    delete_chapter_chunks(db_session, 99999)
    db_session.commit()
