from unittest.mock import MagicMock

import pytest

from app.agents.writer import (
    PreparedGeneration,
    prepare_generation,
    stream_generation,
)
from app.llm.streaming import StreamEvent
from app.memory.errors import InvalidContextError


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    from app.memory import session as session_module
    from app.memory.session import _build_engine, init_db
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False,
                                autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
    # M3b: create vec_chunks virtual table (Base.metadata.create_all doesn't)
    with new_engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024] distance_metric=cosine)"
        ))
        conn.commit()
    with new_session() as s:
        yield s


def _seed_full_project(db_session):
    from app.memory.schema import (
        Chapter, Character, LoreEntry, Project, WorldOverview,
    )
    p = Project(title="PN", genre="g", premise="prem",
                main_theme="mt", tone="t")
    db_session.add(p); db_session.flush()
    wo = WorldOverview(project_id=p.id, setting_era="Era1",
                       power_system="PS1")
    db_session.add(wo)
    loc = LoreEntry(project_id=p.id, type="location", name="Loc")
    db_session.add(loc); db_session.flush()
    faction = LoreEntry(project_id=p.id, type="faction", name="F")
    db_session.add(faction); db_session.flush()
    c1 = Character(project_id=p.id, name="C1", role="protagonist",
                   affiliations=[faction.id], known_locations=[loc.id])
    c2 = Character(project_id=p.id, name="C2", role="supporting")
    db_session.add_all([c1, c2])
    ch = Chapter(project_id=p.id, order_index=1, title="CH1")
    db_session.add(ch); db_session.commit()
    return p, [c1, c2], loc, faction, ch


class FakeRouter:
    """Fake ModelRouter that yields a fixed stream."""
    def __init__(self, events):
        self._events = events
    def resolve_model(self, task):
        return ("claude", "claude-sonnet-4-6")
    def stream(self, request):
        for e in self._events:
            yield e
    # M3b: default embed returns 1024-dim vectors; tests override per-case
    def embed(self, texts, model=None):
        return [[0.1] * 1024] * len(texts)


def test_prepare_creates_log_with_streaming_status(db_session):
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([])
    prep = prepare_generation(
        db_session,
        chapter_id=ch.id,
        beat_text="主角遇旧友",
        instruction="压抑",
        involved_character_ids=[chars[0].id, chars[1].id],
        location_id=loc.id,
        model_task="writer_long",
        max_tokens=4096,
        router=fake_router,
    )
    assert isinstance(prep, PreparedGeneration)
    assert prep.log.id > 0
    assert prep.log.status == "streaming"
    assert prep.log.beat_text == "主角遇旧友"
    assert prep.log.instruction == "压抑"
    assert prep.log.project_id == p.id
    assert prep.log.model == "claude-sonnet-4-6"
    assert prep.log.started_at is not None
    assert prep.log.finished_at is None
    # Log has rendered prompts (not template paths)
    assert "PN" in prep.user_prompt
    assert "C1" in prep.user_prompt
    assert "Loc" in prep.user_prompt
    assert "F" in prep.user_prompt


def test_prepare_raises_on_invalid_context(db_session):
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([])
    with pytest.raises(InvalidContextError):
        prepare_generation(
            db_session,
            chapter_id=ch.id,
            beat_text="x",
            instruction="",
            involved_character_ids=[99999],
            location_id=None,
            model_task="writer_long",
            max_tokens=4096,
            router=fake_router,
        )


def test_stream_generation_yields_meta_then_context_then_tokens_then_done(db_session):
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([
        StreamEvent(type="token", text="Hello "),
        StreamEvent(type="token", text="world"),
        StreamEvent(type="done", input_tokens=10, output_tokens=2,
                    stop_reason="end_turn"),
    ])
    prep = prepare_generation(
        db_session,
        chapter_id=ch.id,
        beat_text="x",
        instruction="",
        involved_character_ids=[chars[0].id],
        location_id=None,
        model_task="writer_long",
        max_tokens=4096,
        router=fake_router,
    )
    events = list(stream_generation(db_session, prep, router=fake_router))
    types = [e["type"] for e in events]
    assert types == ["meta", "context", "token", "token", "done"]
    assert events[0]["generation_log_id"] == prep.log.id
    assert events[0]["model"] == "claude-sonnet-4-6"
    assert "C1" in str(events[1]["context_bundle"])
    token_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert token_text == "Hello world"
    done = events[-1]
    assert done["input_tokens"] == 10
    assert done["output_tokens"] == 2
    assert done["stop_reason"] == "end_turn"


def test_stream_generation_persists_log_on_done(db_session):
    from app.memory.schema import GenerationLog
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([
        StreamEvent(type="token", text="AB"),
        StreamEvent(type="done", input_tokens=5, output_tokens=1,
                    stop_reason="end_turn"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[0].id], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    list(stream_generation(db_session, prep, router=fake_router))
    db_session.expire_all()
    log = db_session.get(GenerationLog, prep.log.id)
    assert log.status == "done"
    assert log.generated_text == "AB"
    assert log.input_tokens == 5
    assert log.output_tokens == 1
    assert log.stop_reason == "end_turn"
    assert log.finished_at is not None


def test_stream_generation_persists_log_on_error(db_session):
    from app.memory.schema import GenerationLog
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([
        StreamEvent(type="token", text="partial"),
        StreamEvent(type="error", error_message="API down",
                    error_code="RuntimeError"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[0].id], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    events = list(stream_generation(db_session, prep, router=fake_router))
    types = [e["type"] for e in events]
    assert types == ["meta", "context", "token", "error"]
    err = events[-1]
    assert "API down" in err["message"]
    assert err["code"] == "RuntimeError"
    db_session.expire_all()
    log = db_session.get(GenerationLog, prep.log.id)
    assert log.status == "failed"
    assert log.stop_reason == "RuntimeError"
    assert log.finished_at is not None


def test_finalize_done_writes_back_chapter_defaults(db_session):
    """When generation done, chapter.last_involved_character_ids and last_location_id
    must be updated to the values used in this generation."""
    from app.memory.schema import Chapter
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([
        StreamEvent(type="token", text="hello"),
        StreamEvent(type="done", input_tokens=5, output_tokens=1,
                    stop_reason="end_turn"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[0].id, chars[1].id],
        location_id=loc.id,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    list(stream_generation(db_session, prep, router=fake_router))

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.last_involved_character_ids == [chars[0].id, chars[1].id]
    assert chapter.last_location_id == loc.id


def test_finalize_done_preserves_chapter_on_error(db_session):
    """Error path must NOT overwrite chapter defaults -- keep previous values."""
    from app.memory.schema import Chapter
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    # Pre-set defaults
    ch_ref = db_session.get(Chapter, ch.id)
    ch_ref.last_involved_character_ids = [chars[0].id]
    ch_ref.last_location_id = None
    db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="error", error_message="boom", error_code="X"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[1].id], location_id=loc.id,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    list(stream_generation(db_session, prep, router=fake_router))

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    # Untouched
    assert chapter.last_involved_character_ids == [chars[0].id]
    assert chapter.last_location_id is None


def test_writer_prompt_includes_retrieved_chunks(db_session):
    """When chunks exist in DB, writer prompt should contain '相关场景预览' section."""
    from app.memory.schema import Chapter, Project
    from app.memory.vectors import insert_chunk
    from app.agents.writer import prepare_generation

    # Seed project + 2 chapters
    p = Project(title="P", genre="g", premise="p")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="第一章", content="past chapter content")
    ch2 = Chapter(project_id=p.id, order_index=2, title="第二章", content="current chapter")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # Add a chunk to chapter 1 (the past chapter)
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="past chunk text", char_count=15,
                 embedding=[0.9] * 1024)
    db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="token", text="output"),
        StreamEvent(type="done", input_tokens=10, output_tokens=2, stop_reason="end_turn"),
    ])
    # embed returns a vector close to the chunk's vector
    fake_router.embed = MagicMock(return_value=[[0.9] * 1024])

    prep = prepare_generation(
        db_session, chapter_id=ch2.id, beat_text="test beat",
        instruction="", involved_character_ids=[], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )

    assert "相关场景预览" in prep.user_prompt
    assert "past chunk text" in prep.user_prompt


def test_writer_prompt_omits_section_when_no_chunks(db_session):
    """When no chunks exist, writer prompt should NOT contain '相关场景预览'."""
    from app.memory.schema import Chapter, Project
    from app.agents.writer import prepare_generation

    p = Project(title="P"); db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024])

    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    assert "相关场景预览" not in prep.user_prompt


def test_writer_query_includes_character_names(db_session):
    """The embed query should include character names from involved characters."""
    from app.memory.schema import Chapter, Project, Character
    from app.agents.writer import prepare_generation

    p = Project(title="P"); db_session.add(p); db_session.flush()
    c = Character(project_id=p.id, name="李雷", role="protagonist")
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add_all([c, ch]); db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024])

    prepare_generation(
        db_session, chapter_id=ch.id, beat_text="beat text",
        instruction="", involved_character_ids=[c.id], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )

    # embed should have been called with a query containing the character name
    call_args = fake_router.embed.call_args
    query = call_args[0][0][0]  # first arg = texts list, first text
    assert "李雷" in query
    assert "beat text" in query
