"""Polish agent tests (mock LLM)."""
from unittest.mock import MagicMock

import pytest

from app.agents.polish import PolishResult, polish_chapter
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, PolishError
from app.memory.schema import Chapter, Project


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for polish tests."""
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


def _llm_response(text: str, stop_reason="end_turn"):
    return LLMResponse(
        text=text, input_tokens=10, output_tokens=20, stop_reason=stop_reason,
    )


def _seed_chapter(db_session, content="李雷推开门。"):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content=content)
    db_session.add(ch); db_session.commit()
    return p, ch


def _make_router(text="润色后的文字。", stop_reason="end_turn"):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=_llm_response(text, stop_reason))
    return fake


def test_polish_chapter_returns_text(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("更好的文字。")
    result = polish_chapter(db_session, chapter_id=ch.id, router=fake)
    assert isinstance(result, PolishResult)
    assert result.polished_text == "更好的文字。"
    assert result.is_selection is False
    assert result.log_id > 0


def test_polish_selection(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("更好的段落。")
    result = polish_chapter(
        db_session, chapter_id=ch.id, selected_text="原段落", router=fake,
    )
    assert result.polished_text == "更好的段落。"
    assert result.is_selection is True


def test_polish_empty_response_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("  ")
    with pytest.raises(PolishError):
        polish_chapter(db_session, chapter_id=ch.id, router=fake)


def test_polish_max_tokens_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("截断的文字", stop_reason="max_tokens")
    with pytest.raises(PolishError):
        polish_chapter(db_session, chapter_id=ch.id, router=fake)


def test_polish_not_found(db_session):
    fake = _make_router()
    with pytest.raises(ChapterNotFoundError):
        polish_chapter(db_session, chapter_id=99999, router=fake)


def test_polish_writes_generation_log(db_session):
    from app.memory.schema import GenerationLog
    p, ch = _seed_chapter(db_session)
    fake = _make_router("润色结果。")
    result = polish_chapter(db_session, chapter_id=ch.id, router=fake)
    log = db_session.get(GenerationLog, result.log_id)
    assert log is not None
    assert log.model_task == "polish"
    assert log.beat_text == "(polish)"
    assert log.status == "done"
