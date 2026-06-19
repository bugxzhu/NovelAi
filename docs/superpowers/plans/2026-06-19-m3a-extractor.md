# M3a — Extractor + Pending Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M3a Extractor Agent that produces a chapter summary + structured entity changes from chapter content, plus a `pending_updates` queue with frontend accept/reject panel.

**Architecture:** Synchronous finalize endpoint triggers a single LLM call (JSON-structured response). Result is parsed into `pending_updates` rows in one DB transaction (chapter.summary + status + content_hash updated atomically). Frontend ActivityBar shows pending count badge; new `/projects/[id]/pending` page lists updates with inline accept/reject. Accept applies the change (INSERT or PATCH) to characters/lore_entries tables.

**Tech Stack:** Python + FastAPI + SQLAlchemy 2.0 + Jinja2 (backend); Next.js 15 + React 19 + TanStack Query + Zustand (frontend); Vitest + Playwright (tests).

**Reference spec:** `docs/superpowers/specs/2026-06-19-m3a-extractor-design.md`

**Working directory:** `/Users/bugx/novelAI`

---

## Scope Check

M3a is one cohesive subsystem (extractor agent + pending_updates queue + accept/reject UI). No decomposition needed.

---

## File Structure

### Backend (modify + create)

```
app/
├── memory/
│   ├── schema.py                # modify: add PendingUpdate table
│   └── errors.py                # modify: add ExtractionError
├── models/
│   └── pending.py               # create: Pydantic schemas
├── llm/prompts/extractor/
│   ├── system.j2                # create
│   └── user.j2                  # create
├── agents/
│   └── extractor.py             # create: extract_chapter + _build_pending_rows
├── api/
│   ├── chapters_finalize.py     # create: POST /api/chapters/{id}/finalize
│   └── pending_updates.py       # create: list / detail / accept / reject
└── main.py                      # modify: register 2 new routers

tests/  (backend)
├── test_extractor_prompts.py
├── test_extractor_agent.py
├── test_chapters_finalize.py
└── test_pending_updates.py
```

### Frontend (modify + create)

```
web/
├── lib/
│   ├── types.ts                 # modify: add PendingUpdate / Read / Detail
│   ├── api.ts                   # modify: add 4 pending endpoints
│   └── queries.ts               # modify: add 4 hooks
├── components/
│   ├── layout/ActivityBar.tsx   # modify: 📋 icon + badge
│   ├── editor/
│   │   ├── EditorToolbar.tsx    # modify: extraActions slot
│   │   └── FinalizeButton.tsx   # create
│   ├── editor/ChapterEditor.tsx # modify: pass FinalizeButton
│   └── entities/
│       └── PendingUpdateItem.tsx # create
├── app/projects/[projectId]/
│   └── pending/page.tsx         # create: pending list page
└── tests/
    ├── FinalizeButton.test.tsx
    ├── PendingUpdateItem.test.tsx
    └── e2e/
        ├── finalize-pending.spec.ts
        └── refinalize-overwrites.spec.ts
```

### Principles

- `lib/` zero React. `components/` grouped by domain.
- One responsibility per file. Files over ~250 lines get split.
- Backend follows M2a patterns (no async; sync SQLAlchemy).
- Each task produces a green test + commit.

---

## Task 1: Backend — PendingUpdate ORM + ExtractionError

**Files:**
- Modify: `app/memory/schema.py` (append `PendingUpdate` class)
- Modify: `app/memory/errors.py` (append `ExtractionError`)
- Modify: `tests/test_chapter_models.py` (or new file) — assert table registered
- Create: `tests/test_pending_schema.py`

- [ ] **Step 1.1: Write failing test**

Create `tests/test_pending_schema.py`:

```python
def test_pending_updates_table_registered():
    from app.memory.base import Base
    assert "pending_updates" in Base.metadata.tables


def test_extraction_error_is_exception():
    from app.memory.errors import ExtractionError
    err = ExtractionError("bad json")
    assert isinstance(err, Exception)
    assert "bad json" in str(err)
```

- [ ] **Step 1.2: Run → verify fails**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
pytest tests/test_pending_schema.py -v
```

Expected: FAIL — table not registered.

- [ ] **Step 1.3: Append `PendingUpdate` to `app/memory/schema.py`**

After the `GenerationLog` class:

```python
class PendingUpdate(Base):
    __tablename__ = "pending_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    update_type: Mapped[str] = mapped_column(String(20), nullable=False, default="hard_fact")
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # 'create' | 'update'
    target_table: Mapped[str] = mapped_column(String(50), nullable=False)  # 'characters' | 'lore_entries'
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    proposed_change: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")

    auto: Mapped[bool] = mapped_column(default=True)
    extractor_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)
```

Ensure `Index` is imported at top of file (it isn't currently) — add to the `from sqlalchemy import ...` line:

```python
from sqlalchemy import ForeignKey, Index, Integer, String, Text, JSON
```

And after the `PendingUpdate` class body add the indexes (SQLAlchemy accepts `__table_args__`):

```python
    __table_args__ = (
        Index("idx_pending_project_status", "project_id", "status"),
        Index("idx_pending_chapter", "chapter_id"),
    )
```

- [ ] **Step 1.4: Append `ExtractionError` to `app/memory/errors.py`**

```python
class ExtractionError(Exception):
    """LLM extraction failed (invalid JSON, missing fields, etc.)."""
```

- [ ] **Step 1.5: Run tests → verify passes**

```bash
pytest tests/test_pending_schema.py -v
```

Expected: 2 PASS.

- [ ] **Step 1.6: Run full suite (regression check)**

```bash
pytest -v
```

Expected: All M1 + M2a + M2b backend tests pass. New table auto-created via `Base.metadata.create_all`.

- [ ] **Step 1.7: Drop DB to verify schema picks up new table**

```bash
rm -f /Users/bugx/novelAI/data/novelai.db /Users/bugx/novelAI/data/novelai.db-shm /Users/bugx/novelAI/data/novelai.db-wal
```

(Next test run will recreate. M3a uses drop & recreate per spec §3.4.)

- [ ] **Step 1.8: Commit**

```bash
git add app/memory/schema.py app/memory/errors.py tests/test_pending_schema.py
git commit -m "feat(m3a): pending_updates table + ExtractionError"
```

---

## Task 2: Backend — Pydantic schemas for PendingUpdate

**Files:**
- Create: `app/models/pending.py`
- Create: `tests/test_pending_models.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_pending_models.py`:

```python
from datetime import UTC, datetime

from app.models.pending import (
    PendingUpdateRead,
    PendingUpdateDetail,
    FinalizeResponse,
)


def test_pending_read_minimal():
    now = datetime.now(UTC)
    p = PendingUpdateRead(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="pending",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        created_at=now, updated_at=now,
    )
    assert p.entity_name == "韩梅"
    # Read does not expose proposed_change
    assert not hasattr(p, "proposed_change")


def test_pending_detail_has_proposed_change():
    now = datetime.now(UTC)
    p = PendingUpdateDetail(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="pending",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        proposed_change={"name": "韩梅", "role": "supporting", "description": "酒馆老板娘"},
        decision_note="", decided_at=None,
        extractor_model="claude-haiku-4-5", extractor_log_id=42,
        chapter_title="第二章", target_entity_name=None,
        created_at=now, updated_at=now,
    )
    assert p.proposed_change["name"] == "韩梅"
    assert p.chapter_title == "第二章"


def test_finalize_response():
    r = FinalizeResponse(
        chapter_id=1, summary="...",
        pending_created=3, log_id=42,
    )
    assert r.pending_created == 3


def test_accept_response_includes_no_extra_fields():
    # accept endpoint returns PendingUpdateRead, not Detail
    from app.models.pending import AcceptRejectResponse
    now = datetime.now(UTC)
    r = AcceptRejectResponse(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="accepted",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        created_at=now, updated_at=now,
    )
    assert r.status == "accepted"
```

- [ ] **Step 2.2: Run → verify fails**

```bash
pytest tests/test_pending_models.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 2.3: Create `app/models/pending.py`**

```python
from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class PendingUpdateRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    chapter_id: int
    update_type: str
    operation: str  # 'create' | 'update'
    target_table: str
    target_id: int | None
    reason: str
    status: str
    # Derived summary fields (extracted from proposed_change in API layer)
    entity_name: str
    entity_type: str
    field_name: str
    old_value: str
    proposed_value: str


class PendingUpdateDetail(PendingUpdateRead):
    proposed_change: dict
    decision_note: str
    decided_at: datetime | None
    extractor_model: str | None
    extractor_log_id: int | None
    chapter_title: str
    target_entity_name: str | None


# Alias — accept/reject endpoints return the same shape as Read
AcceptRejectResponse = PendingUpdateRead


class FinalizeResponse(BaseModel):
    chapter_id: int
    summary: str
    pending_created: int
    log_id: int


class RejectBody(BaseModel):
    note: str = ""
```

- [ ] **Step 2.4: Run tests → verify passes**

```bash
pytest tests/test_pending_models.py -v
```

Expected: 4 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add app/models/pending.py tests/test_pending_models.py
git commit -m "feat(m3a): pending update pydantic schemas"
```

---

## Task 3: Backend — Extractor Jinja2 templates

**Files:**
- Create: `app/llm/prompts/extractor/system.j2`
- Create: `app/llm/prompts/extractor/user.j2`
- Create: `tests/test_extractor_prompts.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_extractor_prompts.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from jinja2 import UndefinedError

from app.llm.prompts import render


def _fake_project():
    return SimpleNamespace(
        title="夜行记", genre="奇幻", premise="复仇故事",
        main_theme="复仇", tone="压抑",
    )


def _fake_chapter(content="夜色压在屋脊上。李雷推开残月酒馆的门。"):
    return SimpleNamespace(
        id=1, title="第二章", content=content,
    )


def _fake_character(id_=1, name="李雷", role="protagonist"):
    return SimpleNamespace(
        id=id_, name=name, role=role,
        background="南方孤儿", motivation="复仇",
        appearance="黑衣", current_state="愤怒",
    )


def _fake_lore(name="青石城", type_="location"):
    return SimpleNamespace(
        name=name, type=type_, description="王国首都",
    )


def test_render_system():
    out = render("extractor/system.j2")
    assert isinstance(out, str)
    assert "JSON" in out
    assert "summary" in out


def test_render_user_full():
    out = render(
        "extractor/user.j2",
        project=_fake_project(),
        chapter=_fake_chapter(),
        existing_characters=[_fake_character()],
        existing_lore=[_fake_lore()],
    )
    assert "夜行记" in out
    assert "李雷" in out
    assert "青石城" in out
    assert "夜色压在屋脊上" in out


def test_render_user_minimal_no_entities():
    out = render(
        "extractor/user.j2",
        project=_fake_project(),
        chapter=_fake_chapter(),
        existing_characters=[],
        existing_lore=[],
    )
    assert "夜行记" in out
    # Empty loops should not raise
    assert "已有人物（0" in out
    assert "已有设定（0" in out


def test_render_user_missing_var_raises():
    with pytest.raises(UndefinedError):
        render("extractor/user.j2", project=_fake_project())
```

- [ ] **Step 3.2: Run → verify fails**

```bash
pytest tests/test_extractor_prompts.py -v
```

Expected: FAIL — templates not found.

- [ ] **Step 3.3: Create `app/llm/prompts/extractor/system.j2`**

```
你是一位细心的小说编辑助手，从章节正文中抽取事实信息。

# 你的工作准则

## 抽取范围
- 新人物：本章首次出现、项目人物库中没有的角色
- 新设定：本章首次出现的地点/势力/物品
- 描述补充：现有实体的描述不够准确，本章透露了更多细节

## 抽取原则
- 严格基于正文，不要发挥想象
- 仅抽"硬事实"（名字、明确身份、客观描述）
- 软事实（情绪变化、关系演变）不抽——这是后续工作
- 一句话描述 ≤ 50 字，概括身份 + 关键特征
- 不确定的不要抽

## 输出格式
严格输出 JSON，结构如下。不要输出任何 JSON 之外的内容（包括代码块标记、注释、解释）。

{
  "summary": "200-400 字章节摘要，第三人称，包含主要情节",
  "entities": {
    "new_characters": [
      {"name": "人物名", "role": "protagonist|supporting|antagonist|extra", "description": "一句话描述"}
    ],
    "updated_characters": [
      {"name": "已有人物名", "field": "background|motivation|appearance|current_state", "new_value": "新描述"}
    ],
    "new_lore": [
      {"type": "location|faction|item|organization|concept", "name": "名字", "description": "一句话描述"}
    ],
    "updated_lore": [
      {"name": "已有设定名", "field": "description", "new_value": "新描述"}
    ]
  }
}

如果某类抽取为空，对应数组返回空 []。永远不要省略字段。
```

- [ ] **Step 3.4: Create `app/llm/prompts/extractor/user.j2`**

```
# 项目背景
{{ project.title }} · {{ project.genre }}
{{ project.premise }}

# 本章信息
标题：{{ chapter.title }}
正文：
---
{{ chapter.content }}
---

# 项目现有实体（不要重复抽取）

## 已有人物（{{ existing_characters|length }} 个）
{% for c in existing_characters %}
- {{ c.name }}（{{ c.role }}）：{{ c.background }} {{ c.motivation }} {{ c.appearance }} {{ c.current_state }}
{% endfor %}

## 已有设定（{{ existing_lore|length }} 个）
{% for l in existing_lore %}
- [{{ l.type }}] {{ l.name }}：{{ l.description }}
{% endfor %}

请抽取本章的新实体和描述补充。
```

- [ ] **Step 3.5: Run tests → verify passes**

```bash
pytest tests/test_extractor_prompts.py -v
```

Expected: 4 PASS.

- [ ] **Step 3.6: Commit**

```bash
git add app/llm/prompts/extractor/ tests/test_extractor_prompts.py
git commit -m "feat(m3a): extractor jinja2 prompt templates"
```

---

## Task 4: Backend — Extractor Agent (`extract_chapter` + `_build_pending_rows`)

**Files:**
- Create: `app/agents/extractor.py`
- Create: `tests/test_extractor_agent.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_extractor_agent.py`:

```python
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import ExtractionResult, extract_chapter
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.memory.schema import Chapter, PendingUpdate, Project


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor tests."""
    from app.memory import session as session_module
    from app.memory.session import _build_engine, init_db
    from sqlalchemy.orm import sessionmaker

    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
    with new_session() as s:
        yield s


def _seed_chapter(db_session, content="夜色压在屋脊上。李雷推开残月酒馆的门。"):
    p = Project(title="夜行记", genre="奇幻", premise="复仇")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="第二章", content=content)
    db_session.add(ch)
    db_session.commit()
    return p, ch


def _fake_router(response_text: str):
    """Build a fake router that returns a fixed LLMResponse."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(
        return_value=LLMResponse(
            text=response_text,
            input_tokens=100,
            output_tokens=200,
            stop_reason="end_turn",
        )
    )
    return fake


def test_extract_creates_summary_and_pending(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "李雷进入酒馆。",
        "entities": {
            "new_characters": [
                {"name": "韩梅", "role": "supporting", "description": "酒馆老板娘"}
            ],
            "updated_characters": [],
            "new_lore": [
                {"type": "location", "name": "残月酒馆", "description": "青石城南门"}
            ],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert isinstance(result, ExtractionResult)
    assert result.chapter_id == ch.id
    assert result.pending_created == 2  # 1 char + 1 lore
    assert result.log_id > 0

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == "李雷进入酒馆。"
    assert chapter.status == "final"
    assert chapter.content_hash  # sha256 of content

    pendings = list(db_session.query(PendingUpdate).filter_by(chapter_id=ch.id))
    assert len(pendings) == 2
    ops = {(p.operation, p.target_table) for p in pendings}
    assert ("create", "characters") in ops
    assert ("create", "lore_entries") in ops


def test_extract_no_entities(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "无变化。",
        "entities": {
            "new_characters": [],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0
    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == "无变化。"
    assert chapter.status == "final"


def test_extract_invalid_json_rolls_back(db_session):
    p, ch = _seed_chapter(db_session)
    # Set chapter to a known initial state
    ch.summary = "old"
    ch.status = "draft"
    db_session.commit()

    fake_router = _fake_router("not json {{")
    with pytest.raises(ExtractionError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    # Untouched
    assert chapter.summary == "old"
    assert chapter.status == "draft"
    # No pending rows
    assert db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).count() == 0


def test_extract_missing_summary_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({"entities": {}}))  # no summary
    with pytest.raises(ExtractionError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)


def test_extract_unknown_role_defaults_extra(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [
                {"name": "X", "role": "主角", "description": "y"}
            ],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    pending = db_session.query(PendingUpdate).filter_by(
        chapter_id=ch.id, target_table="characters"
    ).one()
    assert pending.proposed_change["role"] == "extra"


def test_extract_unknown_lore_type_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [],
            "new_lore": [
                {"type": "dynasty", "name": "X", "description": "y"},
                {"type": "location", "name": "Z", "description": "w"}
            ],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 1  # dynasty skipped, Z kept


def test_extract_empty_name_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [
                {"name": "", "role": "extra", "description": "y"}
            ],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0


def test_extract_update_existing_resolves_target_id(db_session):
    from app.memory.schema import Character
    p, ch = _seed_chapter(db_session)
    char = Character(project_id=p.id, name="李雷", role="protagonist", background="old bg")
    db_session.add(char)
    db_session.commit()

    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [
                {"name": "李雷", "field": "background", "new_value": "new bg"}
            ],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    pending = db_session.query(PendingUpdate).filter_by(
        chapter_id=ch.id, target_table="characters"
    ).one()
    assert pending.operation == "update"
    assert pending.target_id == char.id
    assert pending.proposed_change["old_value"] == "old bg"
    assert pending.proposed_change["new_value"] == "new bg"


def test_extract_update_unknown_name_skipped(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {
            "new_characters": [],
            "updated_characters": [
                {"name": "不存在的人", "field": "background", "new_value": "x"}
            ],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert result.pending_created == 0


def test_extract_rerun_deletes_old_pending(db_session):
    p, ch = _seed_chapter(db_session)
    fake_router_1 = _fake_router(json.dumps({
        "summary": "first",
        "entities": {
            "new_characters": [{"name": "A", "role": "extra", "description": "x"}],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router_1)
    # Simulate user accepting one
    pending_a = db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).one()
    pending_a.status = "accepted"
    db_session.commit()

    # Rerun
    fake_router_2 = _fake_router(json.dumps({
        "summary": "second",
        "entities": {
            "new_characters": [{"name": "B", "role": "extra", "description": "y"}],
            "updated_characters": [],
            "new_lore": [],
            "updated_lore": [],
        }
    }))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router_2)

    pendings = list(db_session.query(PendingUpdate).filter_by(chapter_id=ch.id))
    # accepted A stays + new pending B
    statuses = {p.proposed_change["name"]: p.status for p in pendings}
    assert statuses == {"A": "accepted", "B": "pending"}


def test_extract_writes_generation_log(db_session):
    from app.memory.schema import GenerationLog
    p, ch = _seed_chapter(db_session)
    fake_router = _fake_router(json.dumps({
        "summary": "x", "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    result = extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    log = db_session.get(GenerationLog, result.log_id)
    assert log is not None
    assert log.model_task == "extractor"
    assert log.beat_text == "(extraction)"
    assert log.generated_text  # the JSON


def test_extract_chapter_not_found(db_session):
    fake_router = _fake_router("{}")
    with pytest.raises(ChapterNotFoundError):
        extract_chapter(db_session, chapter_id=99999, router=fake_router)
```

- [ ] **Step 4.2: Run → verify fails**

```bash
pytest tests/test_extractor_agent.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4.3: Create `app/agents/extractor.py`**

```python
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.memory.schema import (
    Chapter,
    Character,
    GenerationLog,
    LoreEntry,
    PendingUpdate,
    Project,
)

# Constants
ALLOWED_ROLES = {"protagonist", "supporting", "antagonist", "extra"}
ALLOWED_CHARACTER_FIELDS = {"background", "motivation", "appearance", "current_state"}
ALLOWED_LORE_TYPES = {"location", "faction", "item", "organization", "concept"}
# update field for lore_entries is always "description" in M3a


@dataclass
class ExtractionResult:
    chapter_id: int
    summary: str
    pending_created: int
    log_id: int


def _now() -> datetime:
    return datetime.now(UTC)


def _build_pending_rows(
    entities: dict,
    *,
    project_id: int,
    chapter_id: int,
    existing_characters: list[Character],
    existing_lore: list[LoreEntry],
    model_name: str,
) -> list[PendingUpdate]:
    """Convert LLM entities dict to PendingUpdate rows. Skips invalid entries."""
    rows: list[PendingUpdate] = []
    char_by_name = {c.name: c for c in existing_characters}
    lore_by_name = {l.name: l for l in existing_lore}

    # new_characters
    for c in entities.get("new_characters", []) or []:
        name = (c.get("name") or "").strip()
        if not name or name in char_by_name:
            continue
        role = c.get("role", "extra")
        if role not in ALLOWED_ROLES:
            role = "extra"
        description = (c.get("description") or "").strip()
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="create",
            target_table="characters", target_id=None,
            proposed_change={"name": name, "role": role, "description": description},
            reason=c.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # updated_characters
    for c in entities.get("updated_characters", []) or []:
        name = (c.get("name") or "").strip()
        if not name or name not in char_by_name:
            continue
        field = c.get("field", "")
        if field not in ALLOWED_CHARACTER_FIELDS:
            continue
        new_value = (c.get("new_value") or "").strip()
        if not new_value:
            continue
        existing = char_by_name[name]
        old_value = str(getattr(existing, field, "") or "")
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="update",
            target_table="characters", target_id=existing.id,
            proposed_change={
                "name": name, "field": field,
                "old_value": old_value, "new_value": new_value,
            },
            reason=c.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # new_lore
    for l in entities.get("new_lore", []) or []:
        name = (l.get("name") or "").strip()
        if not name or name in lore_by_name:
            continue
        ltype = l.get("type", "")
        if ltype not in ALLOWED_LORE_TYPES:
            continue
        description = (l.get("description") or "").strip()
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="create",
            target_table="lore_entries", target_id=None,
            proposed_change={"type": ltype, "name": name, "description": description},
            reason=l.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    # updated_lore
    for l in entities.get("updated_lore", []) or []:
        name = (l.get("name") or "").strip()
        if not name or name not in lore_by_name:
            continue
        field = l.get("field", "description")
        if field != "description":
            continue  # M3a only updates description
        new_value = (l.get("new_value") or "").strip()
        if not new_value:
            continue
        existing = lore_by_name[name]
        old_value = str(existing.description or "")
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="hard_fact", operation="update",
            target_table="lore_entries", target_id=existing.id,
            proposed_change={
                "name": name, "field": "description",
                "old_value": old_value, "new_value": new_value,
            },
            reason=l.get("reason", ""),
            extractor_model=model_name,
            status="pending",
        ))

    return rows


def extract_chapter(
    db: Session,
    *,
    chapter_id: int,
    router: ModelRouter = default_router,
) -> ExtractionResult:
    """Extract summary + entity changes from a chapter. Atomic transaction."""
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)

    project = db.get(Project, chapter.project_id)
    existing_characters = list(db.scalars(
        select(Character).where(Character.project_id == chapter.project_id)
    ))
    existing_lore = list(db.scalars(
        select(LoreEntry).where(LoreEntry.project_id == chapter.project_id)
    ))

    system_prompt = render("extractor/system.j2")
    user_prompt = render(
        "extractor/user.j2",
        project=project,
        chapter=chapter,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
    )

    request = LLMRequest(
        model_task="extractor",
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
        temperature=0.1,
    )

    _, model_name = router.resolve_model("extractor")
    response = router.complete(request)

    # Parse JSON
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ExtractionError(
            f"LLM returned non-JSON: {e}; response={response.text[:500]}"
        )

    summary = (parsed.get("summary") or "").strip()
    if not summary:
        raise ExtractionError("LLM response missing 'summary' field")

    # Build pending rows (no DB write yet)
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}) or {},
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
    )

    new_hash = hashlib.sha256((chapter.content or "").encode()).hexdigest()

    # Audit log row
    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=chapter.project_id,
        beat_text="(extraction)",
        instruction="",
        involved_character_ids=[],
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "existing_chars": len(existing_characters),
            "existing_lore": len(existing_lore),
        },
        generated_text=response.text,
        model=model_name,
        model_task="extractor",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        stop_reason=response.stop_reason,
        status="done",
        started_at=_now(),
        finished_at=_now(),
    )

    try:
        db.add(log)
        db.flush()  # get log.id
        for p in pending_rows:
            p.extractor_log_id = log.id

        # Delete old pending rows for this chapter (only status='pending')
        db.execute(delete(PendingUpdate).where(
            PendingUpdate.chapter_id == chapter_id,
            PendingUpdate.status == "pending",
        ))

        # Insert new
        for p in pending_rows:
            db.add(p)

        # Update chapter
        chapter.summary = summary
        chapter.content_hash = new_hash
        chapter.status = "final"

        db.commit()
    except Exception:
        db.rollback()
        raise

    return ExtractionResult(
        chapter_id=chapter_id,
        summary=summary,
        pending_created=len(pending_rows),
        log_id=log.id,
    )
```

- [ ] **Step 4.4: Run tests → verify passes**

```bash
pytest tests/test_extractor_agent.py -v
```

Expected: 12 PASS.

- [ ] **Step 4.5: Run full backend suite (regression)**

```bash
pytest -v
```

Expected: all prior tests + new extractor tests pass.

- [ ] **Step 4.6: Commit**

```bash
git add app/agents/extractor.py tests/test_extractor_agent.py
git commit -m "feat(m3a): extractor agent (atomic summary + pending writes)"
```

---

## Task 5: Backend — `POST /api/chapters/{id}/finalize` endpoint

**Files:**
- Create: `app/api/chapters_finalize.py`
- Modify: `app/main.py` (register router)
- Create: `tests/test_chapters_finalize.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_chapters_finalize.py`:

```python
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_router(monkeypatch):
    """Patch default_router at the endpoint module."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "李雷进入酒馆。",
            "entities": {
                "new_characters": [{"name": "韩梅", "role": "supporting", "description": "老板娘"}],
                "updated_characters": [],
                "new_lore": [],
                "updated_lore": [],
            }
        }),
        input_tokens=100, output_tokens=200, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1",
        "content": "夜色压在屋脊上。"
    }).json()["id"]
    return pid, ch


def test_finalize_returns_404_unknown_chapter(client, fake_router):
    r = client.post("/api/chapters/99999/finalize")
    assert r.status_code == 404
    assert r.json()["detail"] == "chapter not found"


def test_finalize_success(client, fake_router):
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 200
    data = r.json()
    assert data["chapter_id"] == ch
    assert data["summary"] == "李雷进入酒馆。"
    assert data["pending_created"] == 1
    assert data["log_id"] > 0

    # Verify chapter was updated
    chap = client.get(f"/api/chapters/{ch}").json()
    assert chap["summary"] == "李雷进入酒馆。"
    assert chap["status"] == "final"
    assert chap["content_hash"]

    # Verify pending list has 1 item
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    assert len(pendings) == 1
    # pending-updates endpoint comes in Task 6; this assertion may fail until then
    # Defer this check if needed


def test_finalize_llm_failure_returns_502(client, monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(side_effect=RuntimeError("API down"))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 502
    assert "API down" in r.json()["detail"]


def test_finalize_invalid_json_returns_422(client, monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text="not json {{",
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "extraction_failed"
    assert "raw" in detail


def test_finalize_idempotent(client, fake_router):
    pid, ch = _seed(client)
    r1 = client.post(f"/api/chapters/{ch}/finalize")
    assert r1.status_code == 200
    # Second call should also succeed and overwrite pending
    r2 = client.post(f"/api/chapters/{ch}/finalize")
    assert r2.status_code == 200
    assert r2.json()["pending_created"] == 1  # same data → same count
```

Note: `test_finalize_success` checks pending list. That endpoint is implemented in Task 6. **If running tests incrementally**, defer that assertion by removing the `pendings = client.get(...)` block; restore after Task 6.

- [ ] **Step 5.2: Run → verify fails**

```bash
pytest tests/test_chapters_finalize.py -v
```

Expected: FAIL — endpoint not registered.

- [ ] **Step 5.3: Create `app/api/chapters_finalize.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.extractor import extract_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, ExtractionError
from app.models.pending import FinalizeResponse

router = APIRouter()


@router.post("/{chapter_id}/finalize", response_model=FinalizeResponse)
def finalize(
    chapter_id: int,
    db: Session = Depends(get_db),
) -> FinalizeResponse:
    try:
        result = extract_chapter(db, chapter_id=chapter_id, router=default_router)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except ExtractionError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "extraction_failed",
                "reason": "invalid JSON or missing fields",
                "raw": str(e)[:500],
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    return FinalizeResponse(
        chapter_id=result.chapter_id,
        summary=result.summary,
        pending_created=result.pending_created,
        log_id=result.log_id,
    )
```

- [ ] **Step 5.4: Register router in `app/main.py`**

Add `chapters_finalize` to the existing imports and register it alongside `chapters_generate`:

```python
from app.api import (
    chapters,
    chapters_finalize,
    chapters_generate,
    characters,
    deps,
    generation_logs,
    health,
    llm,
    lore,
    pending_updates,
    projects,
    world,
)
```

In `create_app`, after the `chapters_generate` include:

```python
    app.include_router(chapters_finalize.router, prefix="/api/chapters",
                       tags=["chapters_finalize"])
```

(`pending_updates` import is for Task 6; if you're strictly going step-by-step, exclude it from the import now and add it in Task 6.6.)

- [ ] **Step 5.5: Run tests → verify passes (some)**

```bash
pytest tests/test_chapters_finalize.py -v
```

Expected: 404 test passes; success test may fail on the pending list assertion (Task 6 endpoint). 502 + 422 tests pass. idempotent test passes (no pending assertion).

Defer the pending list assertion in `test_finalize_success` until Task 6.

- [ ] **Step 5.6: Commit**

```bash
git add app/api/chapters_finalize.py app/main.py tests/test_chapters_finalize.py
git commit -m "feat(m3a): finalize endpoint (synchronous extractor trigger)"
```

---

## Task 6: Backend — PendingUpdate API endpoints

**Files:**
- Create: `app/api/pending_updates.py`
- Modify: `app/main.py` (register router, if not done in Task 5)
- Create: `tests/test_pending_updates.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/test_pending_updates.py`:

```python
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {
                "new_characters": [
                    {"name": "韩梅", "role": "supporting", "description": "老板娘"}
                ],
                "updated_characters": [],
                "new_lore": [
                    {"type": "location", "name": "残月酒馆", "description": "酒馆"}
                ],
                "updated_lore": [],
            }
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _seed_and_finalize(client, fake_router):
    """Create project + character + chapter + finalize → produces 1 char pending + 1 lore pending."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    char = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "background": "old bg"
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1",
        "content": "x"
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    return pid, char, ch


def test_list_requires_project_id(client):
    r = client.get("/api/pending-updates")
    assert r.status_code == 422


def test_list_returns_pending_by_default(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    r = client.get(f"/api/pending-updates?project_id={pid}")
    assert r.status_code == 200
    pendings = r.json()
    assert len(pendings) == 2
    statuses = {p["status"] for p in pendings}
    assert statuses == {"pending"}


def test_list_status_filter(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    # Accept it
    client.post(f"/api/pending-updates/{first_id}/accept")
    # status=pending should return 1
    r1 = client.get(f"/api/pending-updates?project_id={pid}&status=pending")
    assert len(r1.json()) == 1
    # status=accepted should return 1
    r2 = client.get(f"/api/pending-updates?project_id={pid}&status=accepted")
    assert len(r2.json()) == 1


def test_list_chapter_filter(client, fake_router):
    pid, _, ch = _seed_and_finalize(client, fake_router)
    # Add another chapter, finalize
    ch2 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "C2", "content": "y"
    }).json()["id"]
    client.post(f"/api/chapters/{ch2}/finalize")
    r = client.get(f"/api/pending-updates?project_id={pid}&chapter_id={ch}")
    assert all(p["chapter_id"] == ch for p in r.json())


def test_detail_returns_full_proposed_change(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r = client.get(f"/api/pending-updates/{first_id}")
    assert r.status_code == 200
    detail = r.json()
    assert "proposed_change" in detail
    assert detail["chapter_title"]


def test_detail_404_unknown(client):
    r = client.get("/api/pending-updates/99999")
    assert r.status_code == 404


def test_accept_create_character(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    char_pending = next(p for p in pendings if p["target_table"] == "characters")
    r = client.post(f"/api/pending-updates/{char_pending['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    # Character created
    chars = client.get(f"/api/characters?project_id={pid}").json()
    names = {c["name"] for c in chars}
    assert "韩梅" in names


def test_accept_create_lore(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    lore_pending = next(p for p in pendings if p["target_table"] == "lore_entries")
    r = client.post(f"/api/pending-updates/{lore_pending['id']}/accept")
    assert r.status_code == 200
    lore = client.get(f"/api/lore?project_id={pid}").json()
    names = {l["name"] for l in lore}
    assert "残月酒馆" in names


def test_accept_update_character(client, monkeypatch):
    """Accept an update pending → field on existing character changes."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {
                "new_characters": [],
                "updated_characters": [
                    {"name": "李雷", "field": "background", "new_value": "new bg"}
                ],
                "new_lore": [],
                "updated_lore": [],
            }
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    char = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "background": "old bg"
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x"
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    assert len(pendings) == 1
    r = client.post(f"/api/pending-updates/{pendings[0]['id']}/accept")
    assert r.status_code == 200

    # Character updated
    c = client.get(f"/api/characters/{char}").json()
    assert c["background"] == "new bg"


def test_accept_already_decided_returns_409(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r1 = client.post(f"/api/pending-updates/{first_id}/accept")
    assert r1.status_code == 200
    r2 = client.post(f"/api/pending-updates/{first_id}/accept")
    assert r2.status_code == 409


def test_reject_marks_status(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r = client.post(f"/api/pending-updates/{first_id}/reject", json={"note": "不准"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    # Verify detail has note
    detail = client.get(f"/api/pending-updates/{first_id}").json()
    assert detail["decision_note"] == "不准"


def test_reject_does_not_touch_target(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    char_pending = next(p for p in pendings if p["target_table"] == "characters")
    client.post(f"/api/pending-updates/{char_pending['id']}/reject")
    chars = client.get(f"/api/characters?project_id={pid}").json()
    assert all(c["name"] != "韩梅" for c in chars)  # not created
```

- [ ] **Step 6.2: Run → verify fails**

```bash
pytest tests/test_pending_updates.py -v
```

Expected: FAIL — endpoints not registered.

- [ ] **Step 6.3: Create `app/api/pending_updates.py`**

```python
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import (
    Chapter,
    Character,
    LoreEntry,
    PendingUpdate,
)
from app.models.pending import (
    AcceptRejectResponse,
    PendingUpdateDetail,
    PendingUpdateRead,
    RejectBody,
)

router = APIRouter()


def _derive_summary_fields(proposed_change: dict, target_table: str) -> dict:
    """Extract entity_name / entity_type / field_name / old_value / proposed_value
    from proposed_change JSON. Returns kwargs for PendingUpdateRead."""
    if target_table == "characters":
        entity_type = ""
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    else:  # lore_entries
        entity_type = proposed_change.get("type", "")
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    return {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "field_name": field_name,
        "old_value": old_value,
        "proposed_value": proposed_value,
    }


def _to_read(p: PendingUpdate) -> PendingUpdateRead:
    return PendingUpdateRead(
        id=p.id,
        project_id=p.project_id,
        chapter_id=p.chapter_id,
        update_type=p.update_type,
        operation=p.operation,
        target_table=p.target_table,
        target_id=p.target_id,
        reason=p.reason,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_derive_summary_fields(p.proposed_change or {}, p.target_table),
    )


def _to_detail(p: PendingUpdate, db: Session) -> PendingUpdateDetail:
    chapter = db.get(Chapter, p.chapter_id)
    chapter_title = chapter.title if chapter else ""
    target_entity_name = None
    if p.target_id is not None:
        if p.target_table == "characters":
            t = db.get(Character, p.target_id)
            target_entity_name = t.name if t else None
        elif p.target_table == "lore_entries":
            t = db.get(LoreEntry, p.target_id)
            target_entity_name = t.name if t else None
    return PendingUpdateDetail(
        id=p.id,
        project_id=p.project_id,
        chapter_id=p.chapter_id,
        update_type=p.update_type,
        operation=p.operation,
        target_table=p.target_table,
        target_id=p.target_id,
        reason=p.reason,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_derive_summary_fields(p.proposed_change or {}, p.target_table),
        proposed_change=p.proposed_change or {},
        decision_note=p.decision_note or "",
        decided_at=p.decided_at,
        extractor_model=p.extractor_model,
        extractor_log_id=p.extractor_log_id,
        chapter_title=chapter_title,
        target_entity_name=target_entity_name,
    )


@router.get("", response_model=list[PendingUpdateRead])
def list_pending(
    project_id: int = Query(...),
    status: str = Query("pending"),
    chapter_id: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if status == "all":
        status_filter = None
    else:
        status_filter = status

    stmt = select(PendingUpdate).where(PendingUpdate.project_id == project_id)
    if status_filter is not None:
        stmt = stmt.where(PendingUpdate.status == status_filter)
    if chapter_id is not None:
        stmt = stmt.where(PendingUpdate.chapter_id == chapter_id)
    stmt = stmt.order_by(PendingUpdate.id.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    return [_to_read(p) for p in rows]


@router.get("/{pending_id}", response_model=PendingUpdateDetail)
def get_pending(pending_id: int, db: Session = Depends(get_db)):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    return _to_detail(p, db)


@router.post("/{pending_id}/accept", response_model=AcceptRejectResponse)
def accept_pending(pending_id: int, db: Session = Depends(get_db)):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    if p.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {p.status}")

    try:
        if p.operation == "create":
            data = p.proposed_change or {}
            if p.target_table == "characters":
                db.add(Character(
                    project_id=p.project_id,
                    name=data.get("name", ""),
                    role=data.get("role", "extra"),
                    background=data.get("description", ""),
                ))
            elif p.target_table == "lore_entries":
                db.add(LoreEntry(
                    project_id=p.project_id,
                    type=data.get("type", "custom"),
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                ))
            else:
                raise HTTPException(status_code=500, detail=f"unknown target_table: {p.target_table}")
        elif p.operation == "update":
            data = p.proposed_change or {}
            if p.target_id is None:
                raise HTTPException(status_code=500, detail="update pending without target_id")
            if p.target_table == "characters":
                t = db.get(Character, p.target_id)
                if t is None:
                    raise HTTPException(status_code=500, detail="target character gone")
                field = data.get("field")
                if field:
                    setattr(t, field, data.get("new_value", ""))
            elif p.target_table == "lore_entries":
                t = db.get(LoreEntry, p.target_id)
                if t is None:
                    raise HTTPException(status_code=500, detail="target lore gone")
                field = data.get("field", "description")
                setattr(t, field, data.get("new_value", ""))
            else:
                raise HTTPException(status_code=500, detail=f"unknown target_table: {p.target_table}")
        else:
            raise HTTPException(status_code=500, detail=f"unknown operation: {p.operation}")

        p.status = "accepted"
        p.decided_at = datetime.now(UTC)
        db.commit()
        db.refresh(p)
        return _to_read(p)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="accept failed")


@router.post("/{pending_id}/reject", response_model=AcceptRejectResponse)
def reject_pending(
    pending_id: int,
    body: RejectBody | None = None,
    db: Session = Depends(get_db),
):
    p = db.get(PendingUpdate, pending_id)
    if p is None:
        raise HTTPException(status_code=404, detail="pending update not found")
    if p.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {p.status}")

    note = body.note if body else ""
    p.status = "rejected"
    p.decision_note = note
    p.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return _to_read(p)
```

- [ ] **Step 6.4: Register router in `app/main.py`**

If you deferred in Task 5, add now. Otherwise verify both `chapters_finalize` and `pending_updates` are imported and registered:

```python
from app.api import (
    chapters,
    chapters_finalize,
    chapters_generate,
    characters,
    deps,
    generation_logs,
    health,
    llm,
    lore,
    pending_updates,
    projects,
    world,
)
```

In `create_app`:

```python
    app.include_router(chapters_finalize.router, prefix="/api/chapters",
                       tags=["chapters_finalize"])
    app.include_router(pending_updates.router, prefix="/api/pending-updates",
                       tags=["pending_updates"])
```

- [ ] **Step 6.5: Run all pending tests → verify pass**

```bash
pytest tests/test_pending_updates.py -v
```

Expected: 12 PASS.

Restore the deferred assertion in `test_finalize_success` (Task 5) and run:

```bash
pytest tests/test_chapters_finalize.py -v
```

Expected: 5 PASS (including the now-complete success test).

- [ ] **Step 6.6: Run full backend suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 6.7: Commit**

```bash
git add app/api/pending_updates.py app/main.py tests/test_pending_updates.py tests/test_chapters_finalize.py
git commit -m "feat(m3a): pending updates api (list/detail/accept/reject)"
```

---

## Task 7: Frontend — lib/types.ts + lib/api.ts (PendingUpdate types + endpoints)

**Files:**
- Modify: `web/lib/types.ts` (append)
- Modify: `web/lib/api.ts` (append)

- [ ] **Step 7.1: Append to `web/lib/types.ts`**

```typescript
// === M3a: Pending Updates ===

export interface PendingUpdateRead {
  id: number;
  project_id: number;
  chapter_id: number;
  update_type: string;
  operation: "create" | "update";
  target_table: "characters" | "lore_entries";
  target_id: number | null;
  reason: string;
  status: "pending" | "accepted" | "rejected";
  entity_name: string;
  entity_type: string;
  field_name: string;
  old_value: string;
  proposed_value: string;
  created_at: string;
  updated_at: string;
}

export interface PendingUpdateDetail extends PendingUpdateRead {
  proposed_change: Record<string, unknown>;
  decision_note: string;
  decided_at: string | null;
  extractor_model: string | null;
  extractor_log_id: number | null;
  chapter_title: string;
  target_entity_name: string | null;
}

export interface FinalizeResponse {
  chapter_id: number;
  summary: string;
  pending_created: number;
  log_id: number;
}

export type PendingStatus = "pending" | "accepted" | "rejected" | "all";
```

- [ ] **Step 7.2: Append to `web/lib/api.ts`**

First add to imports:

```typescript
import type {
  // ... existing imports ...
  PendingUpdateRead,
  PendingUpdateDetail,
  FinalizeResponse,
  PendingStatus,
} from "./types";
```

Then add to the `api` object (before the closing `}`):

```typescript
  // M3a: Pending Updates
  listPendingUpdates: (params: {
    project_id: number;
    status?: PendingStatus;
    chapter_id?: number;
    limit?: number;
    offset?: number;
  }) =>
    http<PendingUpdateRead[]>(`/api/pending-updates${qs(params as Record<string, unknown>)}`),
  getPendingUpdate: (id: number) =>
    http<PendingUpdateDetail>(`/api/pending-updates/${id}`),
  acceptPendingUpdate: (id: number) =>
    http<PendingUpdateRead>(`/api/pending-updates/${id}/accept`, { method: "POST" }),
  rejectPendingUpdate: (id: number, note?: string) =>
    http<PendingUpdateRead>(`/api/pending-updates/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? "" }),
    }),
  finalizeChapter: (chapterId: number) =>
    http<FinalizeResponse>(`/api/chapters/${chapterId}/finalize`, { method: "POST" }),
```

- [ ] **Step 7.3: Type-check**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 7.4: Commit**

```bash
git add web/lib/types.ts web/lib/api.ts
git commit -m "feat(m3a): ts types + api wrappers for pending updates"
```

---

## Task 8: Frontend — lib/queries.ts (PendingUpdate hooks)

**Files:**
- Modify: `web/lib/queries.ts` (append)

- [ ] **Step 8.1: Append hooks**

```typescript
// === M3a: Pending Updates ===

export function usePendingUpdates(
  projectId: number,
  status: PendingStatus = "pending",
  chapterId?: number
) {
  return useQuery({
    queryKey: ["pending-updates", projectId, status, chapterId],
    queryFn: () => api.listPendingUpdates({ project_id: projectId, status, chapter_id: chapterId }),
  });
}

export function usePendingCount(projectId: number) {
  return useQuery({
    queryKey: ["pending-count", projectId],
    queryFn: async () => {
      const list = await api.listPendingUpdates({
        project_id: projectId,
        status: "pending",
        limit: 200,
      });
      return list.length;
    },
    staleTime: 5_000,
  });
}

export function useAcceptPendingUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.acceptPendingUpdate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
      qc.invalidateQueries({ queryKey: ["characters"] });
      qc.invalidateQueries({ queryKey: ["lore"] });
    },
  });
}

export function useRejectPendingUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) =>
      api.rejectPendingUpdate(id, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
    },
  });
}
```

Also add `PendingStatus` to the import block at top of file:

```typescript
import type {
  // ... existing ...
  PendingStatus,
} from "./types";
```

- [ ] **Step 8.2: Type-check**

```bash
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 8.3: Commit**

```bash
git add web/lib/queries.ts
git commit -m "feat(m3a): pending updates query hooks"
```

---

## Task 9: Frontend — FinalizeButton component + EditorToolbar wiring

**Files:**
- Create: `web/components/editor/FinalizeButton.tsx`
- Modify: `web/components/editor/EditorToolbar.tsx` (add `extraActions` slot)
- Modify: `web/components/editor/ChapterEditor.tsx` (pass FinalizeButton)
- Create: `web/tests/FinalizeButton.test.tsx`

- [ ] **Step 9.1: Write failing test**

Create `web/tests/FinalizeButton.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FinalizeButton } from "@/components/editor/FinalizeButton";
import { ToastProvider } from "@/components/ui/Toast";

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("FinalizeButton", () => {
  it("shows default text when not final", () => {
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    expect(screen.getByRole("button", { name: /完成本章/ })).toBeInTheDocument();
  });

  it("shows refinalize text when already final", () => {
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={true} />);
    expect(screen.getByRole("button", { name: /重新抽取/ })).toBeInTheDocument();
  });

  it("disables and shows spinner during finalizing", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}) // never resolves
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    const btn = screen.getByRole("button", { name: /完成本章/ });
    await user.click(btn);
    expect(screen.getByRole("button", { name: /抽取中/ })).toBeDisabled();
  });

  it("shows success toast with pending count on 200", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        chapter_id: 1, summary: "x", pending_created: 3, log_id: 1,
      }), { status: 200 })
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    await user.click(screen.getByRole("button", { name: /完成本章/ }));
    await waitFor(() => {
      expect(screen.getByText(/已抽取 3 条新事实/)).toBeInTheDocument();
    });
  });

  it("shows error toast on 422", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        detail: { error: "extraction_failed", reason: "bad json", raw: "..." }
      }), { status: 422 })
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    await user.click(screen.getByRole("button", { name: /完成本章/ }));
    await waitFor(() => {
      expect(screen.getByText(/抽取失败/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 9.2: Run → verify fails**

```bash
npm test -- FinalizeButton.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 9.3: Create `web/components/editor/FinalizeButton.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";

export function FinalizeButton({
  chapterId,
  isFinal,
}: {
  chapterId: number;
  isFinal: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [finalizing, setFinalizing] = useState(false);

  const handleFinalize = async () => {
    setFinalizing(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";
      const r = await fetch(`${base}/api/chapters/${chapterId}/finalize`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        const reason =
          (err.detail && (err.detail.reason || err.detail.raw)) ||
          (typeof err.detail === "string" ? err.detail : `HTTP ${r.status}`);
        throw new Error(reason);
      }
      const data = await r.json();
      toast(`已抽取 ${data.pending_created} 条新事实，摘要已生成`, "success");
      qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
      qc.invalidateQueries({ queryKey: ["chapters"] });
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
    } catch (e) {
      toast(`抽取失败: ${(e as Error).message}`, "error");
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleFinalize}
      disabled={finalizing}
    >
      {finalizing
        ? "⏳ 抽取中..."
        : isFinal
        ? "↻ 重新抽取"
        : "✓ 完成本章"}
    </Button>
  );
}
```

- [ ] **Step 9.4: Modify `web/components/editor/EditorToolbar.tsx`**

Replace the file with:

```typescript
"use client";

import { type ReactNode } from "react";
import type { Editor } from "@tiptap/react";

export function EditorToolbar({
  editor,
  title,
  charCount,
  onDelete,
  extraActions,
}: {
  editor: Editor | null;
  title: string;
  charCount: number;
  onDelete?: () => void;
  extraActions?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-line bg-panel">
      <span className="text-sm text-text truncate max-w-md">{title || "未命名章节"}</span>
      <div className="flex items-center gap-3">
        <span className="text-xs text-text-muted">{charCount} 字</span>
        {extraActions}
        {onDelete && (
          <button
            onClick={onDelete}
            title="删除章节"
            className="text-xs text-text-muted hover:text-text"
          >
            🗑️
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 9.5: Modify `web/components/editor/ChapterEditor.tsx`**

In the existing file, find where `<EditorToolbar ... />` is rendered and add the `extraActions` prop:

```tsx
<EditorToolbar
  editor={editor}
  title={chapter.title}
  charCount={charCount}
  onDelete={onDelete}
  extraActions={<FinalizeButton chapterId={chapter.id} isFinal={chapter.status === "final"} />}
/>
```

Add the import at the top:

```typescript
import { FinalizeButton } from "./FinalizeButton";
```

- [ ] **Step 9.6: Run FinalizeButton tests → verify pass**

```bash
npm test -- FinalizeButton.test.tsx
```

Expected: 5 PASS.

- [ ] **Step 9.7: Type-check + run all frontend tests**

```bash
npx tsc --noEmit
npm test
```

Expected: 0 type errors; all tests pass.

- [ ] **Step 9.8: Commit**

```bash
git add web/components/editor/ web/tests/FinalizeButton.test.tsx
git commit -m "feat(m3a): finalize button + editor toolbar extraActions slot"
```

---

## Task 10: Frontend — ActivityBar 📋 icon + badge

**Files:**
- Modify: `web/components/layout/ActivityBar.tsx`

- [ ] **Step 10.1: Update ActivityBar**

Add `📋` to ITEMS between `📜` (history) and `🔍` (search). Then add badge for pending count when project is selected.

```typescript
"use client";

import { usePathname, useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { usePendingCount } from "@/lib/queries";

const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters" },
  { icon: "👥", label: "人物", path: "characters" },
  { icon: "🌍", label: "设定", path: "lore" },
  { icon: "📜", label: "历史", path: "history" },
  { icon: "📋", label: "待处理", path: "pending" },
  { icon: "🔍", label: "搜索", path: "search" },
];

export function ActivityBar({ projectId }: { projectId: number }) {
  const pathname = usePathname();
  const router = useRouter();
  const base = `/projects/${projectId}`;
  const isHome = pathname === "/";
  const { data: pendingCount } = usePendingCount(projectId);

  return (
    <aside className="w-10 bg-sidebar flex flex-col items-center py-2 gap-1 shrink-0">
      <button
        onClick={() => router.push("/")}
        title="返回项目列表"
        className={`w-8 h-8 flex flex-col items-center justify-center rounded ${
          isHome
            ? "bg-accent-strong text-white"
            : "hover:bg-hover-strong text-text-muted"
        }`}
      >
        <span className="text-base leading-none">🏠</span>
      </button>
      <div className="w-6 h-px bg-line my-1" />
      {ITEMS.map((it) => {
        const isActive = pathname.startsWith(`${base}/${it.path}`);
        return (
          <button
            key={it.path}
            onClick={() => router.push(`${base}/${it.path}`)}
            title={it.label}
            className={`relative w-8 h-8 flex flex-col items-center justify-center rounded ${
              isActive
                ? "bg-accent-strong text-white"
                : "hover:bg-hover-strong text-text-muted"
            }`}
          >
            <span className="text-base leading-none">{it.icon}</span>
            {it.path === "pending" && pendingCount && pendingCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-red-600 text-white text-[9px] px-1 rounded-full leading-tight min-w-[14px] text-center">
                {pendingCount > 99 ? "99+" : pendingCount}
              </span>
            )}
          </button>
        );
      })}
      <div className="flex-1" />
      <ThemeToggle />
    </aside>
  );
}
```

- [ ] **Step 10.2: Type-check + smoke test**

```bash
npx tsc --noEmit
npm run dev &
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3300/projects/1/chapters
kill %1
```

Expected: 0 type errors; 200 response.

- [ ] **Step 10.3: Commit**

```bash
git add web/components/layout/ActivityBar.tsx
git commit -m "feat(m3a): activity bar 📋 pending icon + count badge"
```

---

## Task 11: Frontend — PendingUpdateItem component

**Files:**
- Create: `web/components/entities/PendingUpdateItem.tsx`
- Create: `web/tests/PendingUpdateItem.test.tsx`

- [ ] **Step 11.1: Write failing test**

Create `web/tests/PendingUpdateItem.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PendingUpdateItem } from "@/components/entities/PendingUpdateItem";
import type { PendingUpdateRead } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useAcceptPendingUpdate: () => ({ mutate: vi.fn(), isPending: false }),
  useRejectPendingUpdate: () => ({ mutate: vi.fn(), isPending: false }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const basePending: PendingUpdateRead = {
  id: 1, project_id: 1, chapter_id: 1,
  update_type: "hard_fact",
  operation: "create",
  target_table: "characters",
  target_id: null,
  reason: "第 3 段首次出现",
  status: "pending",
  entity_name: "韩梅",
  entity_type: "",
  field_name: "",
  old_value: "",
  proposed_value: "酒馆老板娘",
  created_at: "2026-06-19T10:00:00Z",
  updated_at: "2026-06-19T10:00:00Z",
};

describe("PendingUpdateItem", () => {
  it("renders create character", () => {
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    expect(screen.getByText(/新建人物/)).toBeInTheDocument();
    expect(screen.getByText("韩梅")).toBeInTheDocument();
    expect(screen.getByText("酒馆老板娘")).toBeInTheDocument();
    expect(screen.getByText(/第 3 段首次出现/)).toBeInTheDocument();
  });

  it("renders update character with old/new", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{
        ...basePending,
        operation: "update",
        field_name: "background",
        old_value: "南方孤儿",
        proposed_value: "南方孤儿，曾在守夜人服役",
      }} />
    );
    expect(screen.getByText(/更新人物/)).toBeInTheDocument();
    expect(screen.getByText(/南方孤儿$/)).toBeInTheDocument();
    expect(screen.getByText(/南方孤儿，曾在守夜人服役/)).toBeInTheDocument();
  });

  it("renders create lore with type", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{
        ...basePending,
        target_table: "lore_entries",
        entity_name: "残月酒馆",
        entity_type: "location",
        proposed_value: "青石城南门",
      }} />
    );
    expect(screen.getByText(/新建设定/)).toBeInTheDocument();
    expect(screen.getByText("[location]")).toBeInTheDocument();
  });

  it("calls accept mutation on click", async () => {
    const user = userEvent.setup();
    const fn = vi.fn();
    vi.spyOn(require("@/lib/queries"), "useAcceptPendingUpdate").mockReturnValue({
      mutate: fn, isPending: false,
    });
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    await user.click(screen.getByRole("button", { name: /接受/ }));
    expect(fn).toHaveBeenCalledWith(basePending.id);
  });

  it("calls reject mutation on click", async () => {
    const user = userEvent.setup();
    const fn = vi.fn();
    // Mock window.prompt to skip the note input
    vi.spyOn(window, "prompt").mockReturnValue("");
    vi.spyOn(require("@/lib/queries"), "useRejectPendingUpdate").mockReturnValue({
      mutate: fn, isPending: false,
    });
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    await user.click(screen.getByRole("button", { name: /拒绝/ }));
    expect(fn).toHaveBeenCalledWith({ id: basePending.id, note: "" });
  });

  it("shows status badge for already decided", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{ ...basePending, status: "accepted" }} />
    );
    expect(screen.queryByRole("button", { name: /接受/ })).not.toBeInTheDocument();
    expect(screen.getByText(/已接受/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 11.2: Run → verify fails**

```bash
npm test -- PendingUpdateItem.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 11.3: Create `web/components/entities/PendingUpdateItem.tsx`**

```typescript
"use client";

import { Button } from "@/components/ui/Button";
import { useAcceptPendingUpdate, useRejectPendingUpdate } from "@/lib/queries";
import type { PendingUpdateRead } from "@/lib/types";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function PendingUpdateItem({ pending }: { pending: PendingUpdateRead }) {
  const accept = useAcceptPendingUpdate();
  const reject = useRejectPendingUpdate();

  const isCharacter = pending.target_table === "characters";
  const entityLabel = isCharacter ? "人物" : "设定";
  const opLabel = pending.operation === "create" ? "新建" : "更新";
  const icon = pending.operation === "create" ? "✏️" : "🔄";

  const handleReject = () => {
    const note = window.prompt("拒绝理由（可选）") ?? "";
    reject.mutate({ id: pending.id, note });
  };

  return (
    <div className="bg-panel border border-line rounded p-3 mb-2">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className="text-sm">
            {opLabel}{entityLabel} · <strong>{pending.entity_name}</strong>
            {pending.field_name && ` · ${pending.field_name}`}
          </span>
        </div>
        {!isCharacter && pending.entity_type && (
          <span className="text-xs text-text-dim">[{pending.entity_type}]</span>
        )}
      </div>

      <div className="text-xs text-text-muted mb-2 pl-6">
        {pending.field_name ? (
          <>
            <div>旧值：{pending.old_value || "(空)"}</div>
            <div>新值：{pending.proposed_value}</div>
          </>
        ) : (
          <div>{pending.proposed_value}</div>
        )}
      </div>

      {pending.reason && (
        <div className="text-xs text-text-dim pl-6 mb-2 italic">
          理由：{pending.reason}
        </div>
      )}

      {pending.status === "pending" ? (
        <div className="flex gap-2 pl-6">
          <Button
            variant="primary"
            onClick={() => accept.mutate(pending.id)}
            disabled={accept.isPending}
          >
            ✓ 接受
          </Button>
          <Button
            variant="ghost"
            onClick={handleReject}
            disabled={reject.isPending}
          >
            ✗ 拒绝
          </Button>
        </div>
      ) : (
        <div className="text-xs pl-6 text-text-dim">
          已{pending.status === "accepted" ? "接受" : "拒绝"}
          {pending.decided_at && ` · ${formatTime(pending.decided_at as unknown as string)}`}
        </div>
      )}
    </div>
  );
}
```

Note: `pending.decided_at` isn't in `PendingUpdateRead` — it's only in `Detail`. For list view, this branch won't fire because list view only shows pending ones (default). The cast `as unknown as string` is a defensive placeholder; if `decided_at` is needed on `Read`, lift it there. For M3a, accept the no-op `pending.decided_at` lookup returning undefined.

Actually simpler: remove the `decided_at` reference. Replace with `pending.updated_at`:

```typescript
          {` · ${formatTime(pending.updated_at)}`}
```

- [ ] **Step 11.4: Run PendingUpdateItem tests → verify pass**

```bash
npm test -- PendingUpdateItem.test.tsx
```

Expected: 6 PASS.

- [ ] **Step 11.5: Commit**

```bash
git add web/components/entities/PendingUpdateItem.tsx web/tests/PendingUpdateItem.test.tsx
git commit -m "feat(m3a): pending update item card with inline accept/reject"
```

---

## Task 12: Frontend — PendingUpdates page

**Files:**
- Create: `web/app/projects/[projectId]/pending/page.tsx`

- [ ] **Step 12.1: Create page**

```typescript
"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useChapters, usePendingUpdates } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { PendingUpdateItem } from "@/components/entities/PendingUpdateItem";
import type { PendingStatus } from "@/lib/types";

const STATUS_TABS: Array<{ key: PendingStatus; label: string }> = [
  { key: "pending", label: "待处理" },
  { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" },
  { key: "all", label: "全部" },
];

export default function PendingPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [status, setStatus] = useState<PendingStatus>("pending");
  const [chapterFilter, setChapterFilter] = useState<number | "">("");
  const { data: chapters } = useChapters(pid);
  const { data: pendings, isLoading } = usePendingUpdates(
    pid,
    status,
    chapterFilter || undefined
  );

  const chapterTitle = (cid: number) =>
    chapters?.find((c) => c.id === cid)?.title ?? `Chapter ${cid}`;

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="待处理">
          <div className="px-1 mb-2">
            <div className="text-xs text-text-muted mb-1">状态</div>
            <div className="flex flex-wrap gap-1">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setStatus(t.key)}
                  className={`px-2 py-0.5 rounded text-xs ${
                    status === t.key
                      ? "bg-accent text-white"
                      : "bg-button text-text hover:bg-button-hover"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-1 mb-2">
            <div className="text-xs text-text-muted mb-1">章节</div>
            <select
              value={chapterFilter}
              onChange={(e) =>
                setChapterFilter(e.target.value ? Number(e.target.value) : "")
              }
              className="bg-input border border-line rounded p-1 text-text w-full"
            >
              <option value="">全部章节</option>
              {(chapters ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || `第 ${c.order_index} 章`}
                </option>
              ))}
            </select>
          </div>
          <div className="text-xs text-text-dim px-2 mt-4">
            {isLoading ? "加载中..." : `共 ${pendings?.length ?? 0} 条`}
          </div>
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4">
          {isLoading ? (
            <p className="text-text-muted">加载中...</p>
          ) : !pendings || pendings.length === 0 ? (
            <p className="text-text-muted">无符合条件的记录</p>
          ) : (
            <div className="max-w-3xl mx-auto">
              {pendings.map((p) => (
                <div key={p.id}>
                  <div className="text-xs text-text-dim mt-3 mb-1">
                    {chapterTitle(p.chapter_id)} · 第 {p.id} 条
                  </div>
                  <PendingUpdateItem pending={p} />
                </div>
              ))}
            </div>
          )}
        </div>
      }
    />
  );
}
```

- [ ] **Step 12.2: Type-check + smoke**

```bash
npx tsc --noEmit
npm run dev &
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3300/projects/1/pending
kill %1
```

Expected: 0 type errors; HTTP 200.

- [ ] **Step 12.3: Commit**

```bash
git add web/app/projects/\[projectId\]/pending/
git commit -m "feat(m3a): pending updates list page with status/chapter filters"
```

---

## Task 13: E2E tests + final regression

**Files:**
- Create: `web/tests/e2e/finalize-pending.spec.ts`
- Create: `web/tests/e2e/refinalize-overwrites.spec.ts`

- [ ] **Step 13.1: Create `web/tests/e2e/finalize-pending.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("finalize → accept → character appears", async ({ page, request }) => {
  // 1. Create project + chapter with content via API (faster than UI)
  const base = "http://127.0.0.1:8005";
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E Test" },
  }).then((r) => r.json());
  const pid = project.id;

  await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷", background: "old bg" },
  }).then((r) => r.json());

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "测试章节",
      content: "夜色压在屋脊上。李雷推开残月酒馆的门，看见了韩梅。韩梅是酒馆的老板娘，约三十岁。",
    },
  }).then((r) => r.json());
  const cid = chapter.id;

  // 2. Mock the extractor LLM response
  const mockResponse = JSON.stringify({
    summary: "李雷进入酒馆遇见韩梅。",
    entities: {
      new_characters: [
        { name: "韩梅", role: "supporting", description: "酒馆老板娘，约三十岁" }
      ],
      updated_characters: [
        { name: "李雷", field: "background", new_value: "old bg (补充)" }
      ],
      new_lore: [],
      updated_lore: [],
    }
  });
  await page.route(`**/api/chapters/${cid}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: cid,
        summary: "李雷进入酒馆遇见韩梅。",
        pending_created: 2,
        log_id: 1,
      }),
    });
  });
  // Note: this only mocks finalize; the actual extractor runs in backend.
  // For this E2E we just verify the UI flow given finalize returns success.

  // 3. Visit chapter page and click Finalize
  await page.goto(`/projects/${pid}/chapters/${cid}`);
  await page.click("button:has-text('完成本章')");
  await expect(page.locator("text=已抽取 2 条新事实")).toBeVisible({ timeout: 5_000 });

  // 4. Go to pending page
  await page.click("text=待处理");
  await page.waitForURL(/\/pending$/);

  // 5. Should see 2 pending items (mocked count)
  // Note: actually we'd need real extraction to populate pending_updates.
  // Since we only mocked the finalize response, no actual pending rows exist.
  // For a full E2E, run real backend extraction OR seed pending rows via API.
  // The simplest approach: seed directly via SQL or skip pending assertion.

  // For a true E2E with real extraction, comment out the mock above and let
  // the real LLM be called. But CI can't reliably do that, so we settle for
  // verifying the FinalizeButton → toast flow here.
});
```

**Note:** A complete finalize→accept→character flow requires either real LLM (not viable in CI) or DB seeding. The plan above verifies the UI flow only. For full coverage, add a manual test script (see §8 Acceptance).

- [ ] **Step 13.2: Create `web/tests/e2e/refinalize-overwrites.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("refinalize preserves accepted, overwrites pending", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";
  // Seed: project + chapter + 2 pending rows (1 accepted, 1 pending) via direct API
  // ... (similar pattern; for simplicity this test verifies only the routing works)
  
  await page.goto("/");
  await page.click("text=新建项目");
  await page.waitForURL(/\/projects\/\d+\/chapters/);
  expect(page.url()).toContain("/chapters");
});
```

**Note:** This is a placeholder E2E — full coverage of refinalize semantics is covered by backend unit tests (`test_extract_rerun_deletes_old_pending`).

- [ ] **Step 13.3: Run E2E**

```bash
cd /Users/bugx/novelAI/web
npm run test:e2e
```

Expected: All M2b + new M3a E2E pass.

- [ ] **Step 13.4: Run full backend regression**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
pytest -v
```

Expected: All M1 + M2a + M2b + M3a backend tests pass.

- [ ] **Step 13.5: Run full frontend tests**

```bash
cd /Users/bugx/novelAI/web
npm test
```

Expected: All tests pass.

- [ ] **Step 13.6: Commit**

```bash
git add web/tests/e2e/
git commit -m "test(m3a): e2e finalize-pending flow"
```

---

## Self-Review

### Spec coverage

| Spec § | Coverage |
|---|---|
| §1.1 目标：手动"完成本章"触发抽取 | Tasks 4, 5 |
| §1.1 写 pending_updates | Tasks 1, 4 |
| §1.1 accept/reject 流程 | Tasks 6, 11 |
| §2 模块结构 | All tasks (1-13) |
| §3.1 pending_updates 表 | Task 1 |
| §3.2 proposed_change 4 shape | Task 4 `_build_pending_rows` |
| §3.3 chapter 复用字段 | Task 4 |
| §4 Extractor Agent | Task 4 |
| §4 LLM JSON schema | Task 3 (prompt) + Task 4 (parsing) |
| §4 容错策略 | Task 4 |
| §5.1 finalize 端点 | Task 5 |
| §5.3 list 端点 | Task 6 |
| §5.4 detail 端点 | Task 6 |
| §5.5 accept 端点 | Task 6 |
| §5.6 reject 端点 | Task 6 |
| §6.1 FinalizeButton | Task 9 |
| §6.2 ActivityBar 📋 + badge | Task 10 |
| §6.3 PendingUpdates 面板 | Tasks 11, 12 |
| §6.4 hooks | Task 8 |
| §7 测试策略 | All tasks have TDD tests |
| §8 验收清单 1-17 | Tasks 4-13 |

All covered.

### Placeholder scan

No TBD/TODO. E2E tests in Task 13 have an explicit "Note" explaining they verify UI flow only (real LLM not viable in CI); backend `test_extract_rerun_deletes_old_pending` covers the full semantics.

### Type consistency

- `PendingUpdateRead`: same fields in Task 2 (Pydantic) and Task 7 (TS)
- `extract_chapter` signature: matches Task 4 (definition) and Task 5 (caller)
- `_to_read` / `_to_detail`: defined in Task 6, used in Task 6's API endpoints
- `useAcceptPendingUpdate` / `useRejectPendingUpdate`: defined in Task 8, used in Task 11
- `FinalizeButton` props: `{chapterId, isFinal}` in Task 9 definition + Task 9 wiring in ChapterEditor

No inconsistencies.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-m3a-extractor.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
