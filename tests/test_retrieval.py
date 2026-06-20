import struct

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "retrieval_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    import sqlite_vec

    @event.listens_for(engine, "connect")
    def _load_vec(dbapi_conn, _record):
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        # distance_metric=cosine: sqlite-vec defaults to L2 (Euclidean); the M3b
        # design spec is based on cosine similarity, so we must declare cosine
        # explicitly. With L2 default, "score = 1.0 - distance" would produce
        # meaningless similarity values for non-normalized embeddings.
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            "embedding FLOAT[1024] distance_metric=cosine)"
        ))
        conn.commit()

    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def _seed_two_chapters_with_chunks(db_session):
    """Seed 2 chapters; chapter 1 has 2 chunks, chapter 2 has 1 chunk."""
    from app.memory.schema import Chapter, Project
    from app.memory.vectors import insert_chunk

    p = Project(title="P")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="第一章")
    ch2 = Chapter(project_id=p.id, order_index=2, title="第二章")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # chapter 1 chunk A: vector close to query (cosine ~ 0.9)
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="chapter1 chunk A", char_count=15,
                 embedding=[0.9] * 1024)
    # chapter 1 chunk B: vector orthogonal to query
    orthogonal = [0.0] * 1024
    orthogonal[0] = 1.0
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=1,
                 chunk_type="paragraph", text="chapter1 chunk B", char_count=15,
                 embedding=orthogonal)
    # chapter 2 chunk: similar to query too
    insert_chunk(db_session, chapter_id=ch2.id, chunk_index=0,
                 chunk_type="paragraph", text="chapter2 chunk", char_count=14,
                 embedding=[0.85] * 1024)
    db_session.commit()
    return ch1.id, ch2.id


def _fake_router_returning(query_vec):
    """Build a router whose embed() returns the given query vector."""
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.embed.return_value = [query_vec]
    return fake


def test_retrieval_returns_relevant_chunks(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    # query vector close to chunk A and chapter2 chunk
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999,  # exclude nothing
        query_text="anything", router=fake_router,
    )
    texts = [r.text for r in results]
    assert "chapter1 chunk A" in texts
    assert "chapter2 chunk" in texts
    # chunk B is orthogonal (cosine ~ 0); filtered by threshold 0.4
    assert "chapter1 chunk B" not in texts


def test_retrieval_threshold_filters_low_score(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    # Query vector that is orthogonal to ALL seeded chunks:
    #   chunk A = [0.9]*1024  → dot at index 1 is 0.9, but query[1] = 0 → cosine ≈ 0.03
    #   chunk B = [1,0,...,0] → dot at index 0 is 0 (query[0]=0) and index 1 is 0 → cosine = 0
    #   chunk C = [0.85]*1024 → same as A → cosine ≈ 0.03
    # All scores well below the 0.4 threshold.
    orthogonal = [0.0] * 1024
    orthogonal[1] = 1.0
    fake_router = _fake_router_returning(orthogonal)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    # All chunks orthogonal to query → filtered by threshold 0.4
    assert len(results) == 0


def test_retrieval_excludes_current_chapter(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=ch1, query_text="x", router=fake_router,
    )
    chapter_ids = {r.chapter_id for r in results}
    assert ch1 not in chapter_ids
    assert ch2 in chapter_ids


def test_retrieval_top_k_limits_count(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
        top_k=1,
    )
    assert len(results) == 1


def test_retrieval_empty_when_no_chunks(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    fake_router = _fake_router_returning([0.5] * 1024)
    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    assert results == []


def test_retrieval_sorts_by_score_desc(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    if len(results) >= 2:
        assert results[0].score >= results[1].score


def test_retrieval_joins_chapter_title(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    titles = {r.chapter_title for r in results}
    assert "第一章" in titles or "第二章" in titles
