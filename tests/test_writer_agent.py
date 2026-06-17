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
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False,
                                autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
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
