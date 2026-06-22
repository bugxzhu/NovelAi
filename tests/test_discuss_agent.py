"""M4b-2: discuss agent tests (mock LLM)."""
import json
from unittest.mock import MagicMock

import pytest

from app.agents.discuss import discuss_chapter, DiscussResult
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, DiscussError
from app.memory.schema import Chapter, Project


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for discuss tests."""
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


def _llm_response(text: str, stop_reason: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        text=text, input_tokens=10, output_tokens=20, stop_reason=stop_reason,
    )


def _seed_chapter(db_session, content="李雷推开门。"):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content=content)
    db_session.add(ch); db_session.commit()
    return p, ch


def _make_router(response_text: str, stop_reason: str = "end_turn"):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=_llm_response(response_text, stop_reason))
    return fake


def test_discuss_chapter_returns_branches(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "branches": [
            {"label": "A", "title": "和解", "summary": "两人和解",
             "conflicts": "无", "opportunities": "联手",
             "character_impact": "成长"},
            {"label": "B", "title": "决裂", "summary": "彻底决裂",
             "conflicts": "与蓝图冲突", "opportunities": "反派登场",
             "character_impact": "黑化"},
            {"label": "C", "title": "搁置", "summary": "暂时搁置",
             "conflicts": "情绪积压", "opportunities": "延后爆发",
             "character_impact": "隐忍"},
        ],
        "recommended": "A",
        "reasoning": "A 最符合主题",
    }))
    result = discuss_chapter(db_session, chapter_id=ch.id,
                             question="如果让李雷和韩梅和解？", router=fake)
    assert isinstance(result, DiscussResult)
    assert result.question == "如果让李雷和韩梅和解？"
    assert len(result.branches) == 3
    assert result.branches[0].label == "A"
    assert result.branches[0].title == "和解"
    assert result.branches[1].label == "B"
    assert result.branches[2].label == "C"
    assert result.recommended == "A"
    assert result.reasoning == "A 最符合主题"


def test_discuss_invalid_json_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("not json")
    with pytest.raises(DiscussError):
        discuss_chapter(db_session, chapter_id=ch.id, question="如果？", router=fake)


def test_discuss_truncates_extra_branches(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "branches": [
            {"label": "A", "title": "A", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "B", "title": "B", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "C", "title": "C", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "D", "title": "D", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
        ],
        "recommended": "B",
        "reasoning": "r",
    }))
    result = discuss_chapter(db_session, chapter_id=ch.id,
                             question="如果？", router=fake)
    assert len(result.branches) == 3
    labels = {b.label for b in result.branches}
    assert labels == {"A", "B", "C"}


def test_discuss_missing_recommended_defaults_a(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "branches": [
            {"label": "A", "title": "A", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "B", "title": "B", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "C", "title": "C", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
        ],
        "reasoning": "r",
    }))
    result = discuss_chapter(db_session, chapter_id=ch.id,
                             question="如果？", router=fake)
    assert result.recommended == "A"


def test_discuss_writes_generation_log(db_session):
    from app.memory.schema import GenerationLog
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "branches": [
            {"label": "A", "title": "A", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "B", "title": "B", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
            {"label": "C", "title": "C", "summary": "s", "conflicts": "c",
             "opportunities": "o", "character_impact": "i"},
        ],
        "recommended": "A",
        "reasoning": "r",
    }))
    result = discuss_chapter(db_session, chapter_id=ch.id,
                             question="如果？", router=fake)
    log = db_session.get(GenerationLog, result.log_id)
    assert log is not None
    assert log.model_task == "discuss"
    assert log.beat_text == "(discuss)"
    assert log.instruction == "如果？"
    assert log.status == "done"


def test_discuss_max_tokens_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("{... truncated", stop_reason="max_tokens")
    with pytest.raises(DiscussError):
        discuss_chapter(db_session, chapter_id=ch.id, question="如果？", router=fake)


def test_discuss_not_found(db_session):
    fake = _make_router(json.dumps({"branches": [], "recommended": "A"}))
    with pytest.raises(ChapterNotFoundError):
        discuss_chapter(db_session, chapter_id=99999,
                        question="如果？", router=fake)
