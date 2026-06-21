"""M4a: reviewer agent tests (mock LLM)."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.reviewer import review_chapter, ReviewResult
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.schema import Chapter, Project


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for reviewer tests."""
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


def test_review_chapter_returns_issues(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "issues_by_category": {
            "character": [
                {"severity": "error",
                 "location": "李雷推开门。",
                 "description": "李雷状态突变", "suggestion": "补充心理转变"},
            ],
            "relationship": [],
            "plot": [],
            "foreshadow": [
                {"severity": "info", "location": "",
                 "description": "整章节奏过快", "suggestion": ""},
            ],
            "worldview": [],
        }
    }))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert isinstance(result, ReviewResult)
    assert result.chapter_id == ch.id
    assert len(result.issues) == 2
    categories = {i.category for i in result.issues}
    assert categories == {"character", "foreshadow"}
    char_issue = next(i for i in result.issues if i.category == "character")
    assert char_issue.severity == "error"
    assert char_issue.location == "李雷推开门。"


def test_review_chapter_invalid_json_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("not json")
    with pytest.raises(ReviewError):
        review_chapter(db_session, chapter_id=ch.id, router=fake)


def test_review_chapter_missing_issues_by_category_treated_as_empty(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({"something_else": {}}))
    # issues_by_category defaults to {} which is a dict → empty issues list
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.issues == []


def test_review_chapter_issues_by_category_not_dict_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({"issues_by_category": "not a dict"}))
    with pytest.raises(ReviewError):
        review_chapter(db_session, chapter_id=ch.id, router=fake)


def test_review_chapter_unknown_category_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "issues_by_category": {
            "character": [
                {"severity": "warn", "location": "x", "description": "y", "suggestion": ""},
            ],
            "bogus_category": [
                {"severity": "error", "location": "x", "description": "y", "suggestion": ""},
            ],
        }
    }))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert len(result.issues) == 1
    assert result.issues[0].category == "character"


def test_review_chapter_unknown_severity_defaults_info(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "issues_by_category": {
            "character": [
                {"severity": "critical", "location": "x",
                 "description": "y", "suggestion": ""},
            ],
        }
    }))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.issues[0].severity == "info"


def test_review_chapter_empty_description_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "issues_by_category": {
            "character": [
                {"severity": "warn", "location": "x", "description": "", "suggestion": ""},
            ],
        }
    }))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.issues == []


def test_review_chapter_empty_location_accepted(db_session):
    """Empty location is OK (whole-chapter issue)."""
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({
        "issues_by_category": {
            "plot": [
                {"severity": "info", "location": "",
                 "description": "节奏过快", "suggestion": ""},
            ],
        }
    }))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    assert len(result.issues) == 1
    assert result.issues[0].location == ""


def test_review_chapter_writes_generation_log(db_session):
    from app.memory.schema import GenerationLog
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({"issues_by_category": {}}))
    result = review_chapter(db_session, chapter_id=ch.id, router=fake)
    log = db_session.get(GenerationLog, result.log_id)
    assert log is not None
    assert log.model_task == "reviewer"
    assert log.beat_text == "(review)"
    assert log.status == "done"


def test_review_chapter_max_tokens_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router("{... truncated", stop_reason="max_tokens")
    with pytest.raises(ReviewError):
        review_chapter(db_session, chapter_id=ch.id, router=fake)


def test_review_chapter_not_found(db_session):
    fake = _make_router(json.dumps({"issues_by_category": {}}))
    with pytest.raises(ChapterNotFoundError):
        review_chapter(db_session, chapter_id=99999, router=fake)
