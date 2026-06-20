# M3c-B 人物状态时序（character_states）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Extractor 在 finalize 时额外抽取出场人物的显著状态变化，落 `pending_updates` 软事实队列；用户 accept 后追加到 `character_states` 时序表并镜像更新 `characters.current_state`；人物编辑面板展示状态轨迹。

**Architecture:** 镜像策略 B（`characters.current_state` = 最新 `character_states.state_snapshot`）。常驻层注入逻辑零改动；新增只是"额外加一张历史表 + 新一类 pending 分支 + 历史回溯 API + 前端轨迹折叠区"。Extractor prompt 扩展一次 LLM 调用同时返回 summary + entities + state_changes。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + SQLite；Next.js 15 + React + TanStack Query + Vitest + Playwright。

**Spec:** `docs/superpowers/specs/2026-06-20-m3c-character-states-design.md`

**Port conventions:** Backend `http://127.0.0.1:8005`, Frontend `http://localhost:3300`.

---

## File Structure

**Backend new files:**
- `app/models/character_state.py` — `CharacterStateRead` Pydantic schema
- `app/api/characters_states.py` — `GET /api/characters/{id}/states` endpoint
- `alembic/versions/<hash>_add_character_states.py` — Alembic migration
- `tests/test_extractor_state_changes.py` — Extractor state_changes tests
- `tests/test_pending_character_states.py` — accept/reject + list states tests
- `tests/test_characters_states.py` — `GET /api/characters/{id}/states` tests

**Backend modified files:**
- `app/memory/schema.py` — Add `CharacterState` ORM class
- `app/agents/extractor.py` — Remove `current_state` from `ALLOWED_CHARACTER_FIELDS`; add state_changes branch in `_build_pending_rows`
- `app/api/pending_updates.py` — Extend `_derive_summary_fields` + accept handler for `character_states`
- `app/main.py` — Register `characters_states` router
- `app/llm/prompts/extractor/system.j2` — Drop `current_state` from updated_characters enum; add state_changes section
- `app/llm/prompts/extractor/user.j2` — Show `current_state` per existing character
- `tests/test_extractor_prompts.py` — Add rendering tests for state_changes section

**Frontend new files:**
- `web/components/entities/CharacterStateTimeline.tsx` — Collapsible timeline component
- `web/tests/CharacterStateTimeline.test.tsx` — Unit tests
- `web/tests/e2e/finalize-character-state.spec.ts` — E2E test

**Frontend modified files:**
- `web/lib/types.ts` — Add `CharacterState` interface; widen `PendingUpdateRead.target_table` union
- `web/lib/api.ts` — Add `listCharacterStates` method
- `web/lib/queries.ts` — Add `useCharacterStates`; update `useAcceptPendingUpdate` invalidation
- `web/components/entities/PendingUpdateItem.tsx` — Add state_changes card branch
- `web/components/entities/CharacterForm.tsx` — Mount timeline at bottom
- `web/tests/PendingUpdateItem.test.tsx` — Add state_changes card test

---

## Task 1: Add CharacterState ORM + Alembic migration

**Files:**
- Modify: `app/memory/schema.py:200-219` (append after ChunkMeta)
- Create: `alembic/versions/<hash>_add_character_states.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_character_state_schema.py`:

```python
"""Schema-level tests for CharacterState ORM (M3c-B)."""
from datetime import UTC, datetime

from sqlalchemy import inspect, select

from app.memory.schema import Character, CharacterState, Chapter, Project


def test_character_state_table_columns(db_session):
    """Verify the character_states table has the expected columns."""
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("character_states")}
    expected = {
        "id", "character_id", "chapter_id",
        "state_snapshot", "change_summary",
        "extractor_log_id", "pending_update_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_character_state_indexes_exist(db_session):
    """Verify indexes were created."""
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("character_states")}
    assert "idx_char_state_char_chapter" in index_names
    assert "idx_char_state_chapter" in index_names


def test_character_state_insert_and_query(db_session):
    """Round-trip: insert a row and read it back."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch)
    db_session.flush()
    c = Character(project_id=p.id, name="李雷")
    db_session.add(c)
    db_session.flush()

    s = CharacterState(
        character_id=c.id, chapter_id=ch.id,
        state_snapshot="愤怒", change_summary="被背叛",
    )
    db_session.add(s)
    db_session.commit()

    rows = list(db_session.scalars(
        select(CharacterState).where(CharacterState.character_id == c.id)
    ))
    assert len(rows) == 1
    assert rows[0].state_snapshot == "愤怒"
    assert rows[0].change_summary == "被背叛"
    assert rows[0].extractor_log_id is None
    assert rows[0].pending_update_id is None


def test_character_state_cascade_delete_with_character(db_session):
    """Deleting a character cascades to their states."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c = Character(project_id=p.id, name="李雷")
    db_session.add(c); db_session.flush()
    s = CharacterState(
        character_id=c.id, chapter_id=ch.id,
        state_snapshot="x", change_summary="",
    )
    db_session.add(s); db_session.commit()

    db_session.delete(c)
    db_session.commit()

    rows = list(db_session.scalars(select(CharacterState)))
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_character_state_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'CharacterState' from 'app.memory.schema'`

- [ ] **Step 3: Add CharacterState ORM to schema.py**

Append to `app/memory/schema.py` (after the `ChunkMeta` class, end of file):

```python
class CharacterState(Base):
    """Temporal log of a character's state at the end of each chapter where
    they experienced a significant change. M3c-B: append-only, diff-style
    (rows only created when Extractor detects a notable change). The latest
    snapshot for a character is mirrored to characters.current_state."""
    __tablename__ = "character_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    state_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Audit fields (nullable; future manual creation paths may leave these null)
    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_update_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        Index("idx_char_state_char_chapter", "character_id", "chapter_id"),
        Index("idx_char_state_chapter", "chapter_id"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_character_state_schema.py -v`
Expected: PASS (4 tests). `Base.metadata.create_all` in `init_db` creates the new table automatically during test fixtures.

- [ ] **Step 5: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add character_states"`

This creates `alembic/versions/<hash>_add_character_states.py`. Open it and verify the `upgrade()` body matches:

```python
def upgrade() -> None:
    op.create_table(
        'character_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('state_snapshot', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_char_state_char_chapter', 'character_states',
                    ['character_id', 'chapter_id'], unique=False)
    op.create_index('idx_char_state_chapter', 'character_states',
                    ['chapter_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_char_state_chapter', table_name='character_states')
    op.drop_index('idx_char_state_char_chapter', table_name='character_states')
    op.drop_table('character_states')
```

If autogenerate missed `server_default=''` on `change_summary`, add it manually (matches the `default=""` in ORM). Set `down_revision` to `'f3a6512d59c3'` (the M3b migration).

- [ ] **Step 6: Apply migration to dev.db**

Run: `uv run alembic upgrade head`
Expected output: `Running upgrade f3a6512d59c3 -> <hash>, add character_states`

Verify: `sqlite3 dev.db ".schema character_states"` shows the table.

- [ ] **Step 7: Commit**

```bash
git add app/memory/schema.py alembic/versions/*_add_character_states.py tests/test_character_state_schema.py
git commit -m "feat(m3c-b): add character_states temporal table + migration"
```

---

## Task 2: Add CharacterStateRead Pydantic schema

**Files:**
- Create: `app/models/character_state.py`
- Modify: `app/models/__init__.py` (if it re-exports models — check first)

- [ ] **Step 1: Inspect models package**

Run: `cat app/models/__init__.py`

If it has explicit re-exports (e.g., `from app.models.pending import *`), plan to add `character_state` there. If empty, skip.

- [ ] **Step 2: Create CharacterStateRead**

Create `app/models/character_state.py`:

```python
from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class CharacterStateRead(ORMBase, TimestampMixin):
    id: int
    character_id: int
    chapter_id: int
    chapter_title: str        # JOIN chapters.title
    chapter_order: int        # JOIN chapters.order_index
    state_snapshot: str
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from app.models.character_state import CharacterStateRead; print(CharacterStateRead.model_fields.keys())"`
Expected: prints field names including `chapter_title`, `chapter_order`, `state_snapshot`, etc.

- [ ] **Step 4: Commit**

```bash
git add app/models/character_state.py
git commit -m "feat(m3c-b): add CharacterStateRead pydantic schema"
```

---

## Task 3: Update Extractor prompts

**Files:**
- Modify: `app/llm/prompts/extractor/system.j2`
- Modify: `app/llm/prompts/extractor/user.j2`
- Modify: `tests/test_extractor_prompts.py`

- [ ] **Step 1: Write the failing prompt tests**

Append to `tests/test_extractor_prompts.py`:

```python
from app.llm.prompts import render
from app.memory.schema import Character, Chapter, LoreEntry, Project


def _stub_project():
    return Project(title="T", genre="g", premise="p")


def _stub_chapter():
    return Chapter(project_id=1, order_index=3, title="第三章", content="正文...")


def test_system_prompt_has_state_changes_section():
    """system.j2 must document state_changes extraction rules."""
    out = render("extractor/system.j2")
    assert "state_changes" in out
    assert "情绪转变" in out or "情绪" in out
    assert "state_snapshot" in out
    assert "change_summary" in out


def test_system_prompt_removed_current_state_from_updated_characters():
    """current_state field changes must go through state_changes, not updated_characters."""
    out = render("extractor/system.j2")
    # Find the updated_characters field enum line
    assert "background|motivation|appearance" in out
    # The enum must NOT still list current_state as an updated_characters field
    # (it may still appear elsewhere — in the state_changes section — which is fine)
    # Find the updated_characters sample line and check it
    for line in out.splitlines():
        if "background|motivation|appearance" in line and "field" in line:
            assert "current_state" not in line, (
                f"updated_characters enum still lists current_state: {line!r}"
            )


def test_user_prompt_shows_current_state_for_existing_characters():
    """user.j2 must surface each existing character's current_state."""
    chars = [
        Character(id=1, project_id=1, name="李雷", role="protagonist",
                  background="bg", current_state="警惕"),
        Character(id=2, project_id=1, name="韩梅", role="supporting",
                  background="bg2", current_state=""),
    ]
    out = render("extractor/user.j2",
                 project=_stub_project(),
                 chapter=_stub_chapter(),
                 existing_characters=chars,
                 existing_lore=[])
    assert "现状=警惕" in out
    assert "现状=(未记录)" in out  # empty current_state placeholder
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractor_prompts.py::test_system_prompt_has_state_changes_section tests/test_extractor_prompts.py::test_system_prompt_removed_current_state_from_updated_characters tests/test_extractor_prompts.py::test_user_prompt_shows_current_state_for_existing_characters -v`
Expected: FAIL — first two fail because the section doesn't exist yet and `current_state` is still in the enum; third fails because user.j2 doesn't render `现状=`.

- [ ] **Step 3: Rewrite system.j2**

Replace the entire contents of `app/llm/prompts/extractor/system.j2` with:

```
你是一位细心的小说编辑助手，从章节正文中抽取事实信息。

# 你的工作准则

## 抽取范围
- 新人物：本章首次出现、项目人物库中没有的角色
- 新设定：本章首次出现的地点/势力/物品
- 描述补充：现有实体的描述不够准确，本章透露了更多细节
- 人物状态变化：本章透露了出场人物的显著状态转变

## 抽取原则
- 严格基于正文，不要发挥想象
- 硬事实（名字、明确身份、客观描述）和软事实（情绪、关系、状态）分开抽取
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
      {"name": "已有人物名", "field": "background|motivation|appearance", "new_value": "新描述"}
    ],
    "new_lore": [
      {"type": "location|faction|item|organization|concept", "name": "名字", "description": "一句话描述"}
    ],
    "updated_lore": [
      {"name": "已有设定名", "field": "description", "new_value": "新描述"}
    ]
  },
  "state_changes": [
    {
      "character_name": "已有人物名",
      "state_snapshot": "本章末该人物的状态描述（情绪/处境/身体状况/目标），≤100 字",
      "change_summary": "触发本章状态变化的事件（1-2 句话）"
    }
  ]
}

如果某类抽取为空，对应数组返回空 []。永远不要省略字段（包括 state_changes）。

# 软事实：人物状态变化（state_changes）抽取准则

## 何时抽
仅当本章透露了该人物的明确状态变化时才抽。状态变化包括：
- 情绪转变（如"愤怒 → 平静"、"绝望 → 重燃希望"）
- 受伤 / 痊愈 / 身体状况变化
- 身份改变（如"流浪者 → 守夜人"、"凡人 → 修士"）
- 关键决策（如"决心复仇"、"放弃出走"）
- 关系破裂 / 重建

## 不抽
- 人物本章只是出场但状态无显著变化
- 仅是位置移动、对话参与（不算状态变化）

## 与 updated_characters 的边界（重要）
- current_state 字段的变化一律走 state_changes，不再走 updated_characters
- updated_characters 仅用于 background / motivation / appearance / 其他档案类字段的补充
- 这避免同一人物的同一变化被两条 pending 重复抽取

## 字段要求
- state_snapshot：一段话，覆盖情绪/处境/身体状况/当前目标等，≤100 字
- change_summary：1-2 句话，说明触发本章状态变化的具体事件；无变化原因时留空字符串
```

- [ ] **Step 4: Rewrite user.j2**

Replace the entire contents of `app/llm/prompts/extractor/user.j2` with:

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
- {{ c.name }}（{{ c.role }}）：背景={{ c.background }} | 动机={{ c.motivation }} | 外貌={{ c.appearance }} | 现状={{ c.current_state or "(未记录)" }}
{% endfor %}

## 已有设定（{{ existing_lore|length }} 个）
{% for l in existing_lore %}
- [{{ l.type }}] {{ l.name }}：{{ l.description }}
{% endfor %}

请抽取本章的新实体、描述补充、以及人物状态变化。
```

- [ ] **Step 5: Run prompt tests to verify pass**

Run: `pytest tests/test_extractor_prompts.py -v`
Expected: ALL PASS (including existing M3a tests + 3 new ones).

- [ ] **Step 6: Commit**

```bash
git add app/llm/prompts/extractor/system.j2 app/llm/prompts/extractor/user.j2 tests/test_extractor_prompts.py
git commit -m "feat(m3c-b): extractor prompts add state_changes section"
```

---

## Task 4: Extractor agent — handle state_changes

**Files:**
- Modify: `app/agents/extractor.py:58` (ALLOWED_CHARACTER_FIELDS constant)
- Modify: `app/agents/extractor.py:75-241` (`_build_pending_rows` function)
- Create: `tests/test_extractor_state_changes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_extractor_state_changes.py`:

```python
"""M3c-B: state_changes branch of _build_pending_rows + extract_chapter."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import _build_pending_rows, ALLOWED_CHARACTER_FIELDS
from app.llm.base import LLMResponse
from app.memory.schema import Character, Chapter, PendingUpdate, Project


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )


def _seed_existing(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=5, title="第五章", content="x")
    db_session.add(ch); db_session.flush()
    c = Character(project_id=p.id, name="李雷", role="protagonist",
                  current_state="警惕")
    db_session.add(c); db_session.flush()
    return p, ch, c


def test_current_state_removed_from_allowed_character_fields():
    """M3c-B: current_state changes go through state_changes, not updated_characters."""
    assert "current_state" not in ALLOWED_CHARACTER_FIELDS
    assert "background" in ALLOWED_CHARACTER_FIELDS


def test_build_pending_rows_state_changes_creates_soft_fact(db_session):
    """state_changes produce update_type='soft_fact', target_table='character_states', auto=False."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="claude-haiku-4-5",
        state_changes=[
            {"character_name": "李雷",
             "state_snapshot": "愤怒且受伤",
             "change_summary": "被韩梅伏击"},
        ],
    )
    state_rows = [r for r in rows if r.target_table == "character_states"]
    assert len(state_rows) == 1
    r = state_rows[0]
    assert r.update_type == "soft_fact"
    assert r.operation == "create"
    assert r.target_id is None
    assert r.auto is False
    assert r.proposed_change["character_id"] == c.id
    assert r.proposed_change["character_name"] == "李雷"
    assert r.proposed_change["state_snapshot"] == "愤怒且受伤"
    assert r.proposed_change["change_summary"] == "被韩梅伏击"


def test_build_pending_rows_state_changes_unknown_character_skipped(db_session):
    """character_name not in existing → skip silently."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "鬼魂",  # not in existing
             "state_snapshot": "x", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_empty_snapshot_skipped(db_session):
    """Empty state_snapshot → skip."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "  ", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_empty_name_skipped(db_session):
    """Empty character_name → skip."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "", "state_snapshot": "x", "change_summary": ""},
        ],
    )
    assert rows == []


def test_build_pending_rows_state_changes_missing_change_summary_ok(db_session):
    """Missing change_summary → defaults to empty string."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "x"},
            # change_summary missing
        ],
    )
    assert len(rows) == 1
    assert rows[0].proposed_change["change_summary"] == ""


def test_build_pending_rows_state_changes_missing_field_ok(db_session):
    """Missing state_changes field entirely → treated as empty list, no error."""
    p, ch, c = _seed_existing(db_session)
    # Call WITHOUT passing state_changes kwarg — should default to []
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
    )
    assert rows == []


def test_build_pending_rows_multiple_state_changes_same_character(db_session):
    """Same character, multiple state changes in one chapter → multiple rows (append-only)."""
    p, ch, c = _seed_existing(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c], existing_lore=[],
        model_name="m",
        state_changes=[
            {"character_name": "李雷", "state_snapshot": "中段：愤怒",
             "change_summary": "e1"},
            {"character_name": "李雷", "state_snapshot": "结尾：决绝",
             "change_summary": "e2"},
        ],
    )
    assert len(rows) == 2
    assert all(r.target_table == "character_states" for r in rows)


def test_extract_chapter_writes_state_changes_pending(db_session, monkeypatch):
    """End-to-end: extract_chapter with mock LLM produces state_changes pending rows."""
    from app.agents.extractor import extract_chapter

    p, ch, c = _seed_existing(db_session)

    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=_llm_response({
        "summary": "摘要",
        "entities": {"new_characters": [], "updated_characters": [],
                     "new_lore": [], "updated_lore": []},
        "state_changes": [
            {"character_name": "李雷",
             "state_snapshot": "愤怒", "change_summary": "被伏击"},
        ],
    }))
    # M3b: embed() needed for chunking branch
    fake.embed = MagicMock(return_value=[[0.0] * 1024])

    result = extract_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.pending_created == 1

    rows = list(db_session.query(PendingUpdate).filter(
        PendingUpdate.target_table == "character_states"
    ))
    assert len(rows) == 1
    assert rows[0].update_type == "soft_fact"
    assert rows[0].auto is False
    assert rows[0].proposed_change["character_id"] == c.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractor_state_changes.py -v`
Expected: FAIL — `_build_pending_rows` doesn't accept `state_changes` kwarg, and `ALLOWED_CHARACTER_FIELDS` still contains `current_state`.

- [ ] **Step 3: Drop current_state from ALLOWED_CHARACTER_FIELDS**

In `app/agents/extractor.py:58`, change:

```python
ALLOWED_CHARACTER_FIELDS = {"background", "motivation", "appearance", "current_state"}
```

to:

```python
ALLOWED_CHARACTER_FIELDS = {"background", "motivation", "appearance"}
# M3c-B: current_state changes go through state_changes, not updated_characters
```

- [ ] **Step 4: Extend _build_pending_rows signature + add state_changes branch**

Modify `app/agents/extractor.py:75-83` to add `state_changes` parameter:

```python
def _build_pending_rows(
    entities: dict,
    *,
    project_id: int,
    chapter_id: int,
    existing_characters: list[Character],
    existing_lore: list[LoreEntry],
    model_name: str,
    state_changes: list[dict] | None = None,
) -> list[PendingUpdate]:
```

Update the docstring under the function to mention state_changes tolerance:

```python
    """Convert LLM entities dict + state_changes to PendingUpdate rows.

    Tolerance rules:
        - new_characters / new_lore: empty/duplicate name → skip
        - new_characters: unknown role → "extra"
        - new_lore: unknown type → skip
        - updated_characters: name not in existing → skip; unknown field → skip;
          empty new_value → skip
        - updated_lore: name not in existing → skip; field != "description" → skip;
          empty new_value → skip
        - state_changes: character_name not in existing → skip; empty name/snapshot → skip;
          missing change_summary → defaults to ""
    """
```

Before the `return rows` at the end of `_build_pending_rows`, add the state_changes branch (after the `updated_lore` block):

```python
    # M3c-B: state_changes → soft_fact pending (target_table='character_states')
    # Append-only temporal log. character_name must resolve to an existing character;
    # state changes for new (not-yet-created) characters are skipped — user should
    # accept the new_character create first, then re-finalize to capture the state.
    for sc in (state_changes or []):
        name = (sc.get("character_name") or "").strip()
        snapshot = (sc.get("state_snapshot") or "").strip()
        if not name or not snapshot:
            logger.info(
                "extractor: skipping state_change — empty name/snapshot "
                "(chapter_id=%s); entry=%r", chapter_id, sc,
            )
            continue
        char = char_by_name.get(name)
        if char is None:
            logger.info(
                "extractor: skipping state_change — character %r not in existing "
                "(chapter_id=%s); accept the new_character first then re-finalize",
                name, chapter_id,
            )
            continue
        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="soft_fact", operation="create",
            target_table="character_states", target_id=None,
            proposed_change={
                "character_id": char.id,
                "character_name": char.name,
                "state_snapshot": snapshot,
                "change_summary": (sc.get("change_summary") or "").strip(),
            },
            reason=f"第 {chapter.order_index} 章状态变化",
            auto=False,
            extractor_model=model_name,
            status="pending",
        ))

    return rows
```

**Important:** `chapter` is not currently in scope inside `_build_pending_rows`. To reference `chapter.order_index` in the reason string, either pass `chapter` in as a kwarg OR use `chapter_id` directly. Simpler fix: change the reason to use `chapter_id`:

```python
            reason=f"chapter_id={chapter_id} 状态变化",
```

Use that simpler version to avoid widening the signature further.

- [ ] **Step 5: Pass state_changes when calling _build_pending_rows in extract_chapter**

In `app/agents/extractor.py:309-316`, change:

```python
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}) or {},
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
    )
```

to:

```python
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}) or {},
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
        state_changes=parsed.get("state_changes") or [],
    )
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_extractor_state_changes.py -v`
Expected: ALL 9 tests PASS.

- [ ] **Step 7: Run regression — all extractor tests still pass**

Run: `pytest tests/test_extractor_agent.py tests/test_extractor_prompts.py tests/test_chapters_finalize.py -v`
Expected: ALL PASS. (M3a tests using `updated_characters.field="current_state"` may break — those tests need updating. Inspect any failures and remove/adjust any test fixtures that relied on the old `current_state` field path. Search: `grep -rn "current_state" tests/` to find them.)

- [ ] **Step 8: Fix any M3a tests broken by current_state removal**

Search and update any tests that asserted `updated_characters` with `field: "current_state"`. Convert them to use the new `state_changes` path or remove the assertion.

- [ ] **Step 9: Commit**

```bash
git add app/agents/extractor.py tests/test_extractor_state_changes.py tests/
git commit -m "feat(m3c-b): extractor handles state_changes as soft_fact pending"
```

---

## Task 5: pending_updates API — summary fields + accept handler

**Files:**
- Modify: `app/api/pending_updates.py:24-45` (`_derive_summary_fields`)
- Modify: `app/api/pending_updates.py:131-191` (`accept_pending` handler)
- Modify: `app/api/pending_updates.py:65-96` (`_to_detail` for target_entity_name)
- Modify: `tests/test_pending_updates.py`

- [ ] **Step 1: Write failing tests for accept handler**

Append to `tests/test_pending_updates.py`:

```python
def test_accept_character_state_inserts_row_and_mirrors_current_state(client, fake_router):
    """Accept a character_states pending → INSERT character_states row + UPDATE characters.current_state."""
    # Override fake_router.complete to return state_changes
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [
                {"character_name": "李雷",
                 "state_snapshot": "愤怒且受伤",
                 "change_summary": "被伏击"}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    # M3b embed mock
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "current_state": "警惕",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")
    assert state_pending["update_type"] == "soft_fact"
    assert state_pending["entity_name"] == "李雷"
    assert state_pending["proposed_value"] == "愤怒且受伤"

    r = client.post(f"/api/pending-updates/{state_pending['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    # Mirror: characters.current_state updated
    char = client.get(f"/api/characters/{cid}").json()
    assert char["current_state"] == "愤怒且受伤"

    # Direct DB check: character_states row exists
    from app.memory import session as sm
    from app.memory.schema import CharacterState
    with sm.SessionLocal() as s:
        rows = list(s.query(CharacterState).filter(CharacterState.character_id == cid))
    assert len(rows) == 1
    assert rows[0].state_snapshot == "愤怒且受伤"
    assert rows[0].change_summary == "被伏击"
    assert rows[0].extractor_log_id is not None
    assert rows[0].pending_update_id == state_pending["id"]


def test_accept_character_state_target_gone_returns_500(client, fake_router):
    """If the character was deleted before accept → 500."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [{"character_name": "李雷",
                               "state_snapshot": "x", "change_summary": ""}],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")

    # Delete the character (cascades: but pending_update rows have target_table='character_states'
    # with target_id=null, so they survive)
    client.delete(f"/api/characters/{cid}")

    r = client.post(f"/api/pending-updates/{state_pending['id']}/accept")
    assert r.status_code == 500


def test_reject_character_state_no_db_change(client, fake_router):
    """Reject → no character_states row, no current_state change."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [{"character_name": "李雷",
                               "state_snapshot": "x", "change_summary": ""}],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "current_state": "警惕",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")

    r = client.post(f"/api/pending-updates/{state_pending['id']}/reject",
                    json={"note": "no"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # current_state unchanged
    char = client.get(f"/api/characters/{cid}").json()
    assert char["current_state"] == "警惕"

    # No character_states row
    from app.memory import session as sm
    from app.memory.schema import CharacterState
    with sm.SessionLocal() as s:
        rows = list(s.query(CharacterState).filter(CharacterState.character_id == cid))
    assert rows == []
```

Also add at top of file if not already imported:

```python
from app.llm.base import LLMResponse
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pending_updates.py::test_accept_character_state_inserts_row_and_mirrors_current_state tests/test_pending_updates.py::test_accept_character_state_target_gone_returns_500 tests/test_pending_updates.py::test_reject_character_state_no_db_change -v`
Expected: FAIL — accept handler doesn't have character_states branch.

- [ ] **Step 3: Update imports in pending_updates.py**

In `app/api/pending_updates.py:8-13`, extend the schema import to include `CharacterState`:

```python
from app.memory.schema import (
    Chapter,
    Character,
    CharacterState,
    LoreEntry,
    PendingUpdate,
)
```

- [ ] **Step 4: Extend _derive_summary_fields for character_states**

Replace `app/api/pending_updates.py:24-45` with:

```python
def _derive_summary_fields(proposed_change: dict, target_table: str) -> dict:
    """Extract entity_name / entity_type / field_name / old_value / proposed_value
    from proposed_change JSON. Returns kwargs for PendingUpdateRead."""
    if target_table == "characters":
        entity_type = ""
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    elif target_table == "lore_entries":
        entity_type = proposed_change.get("type", "")
        entity_name = proposed_change.get("name", "")
        field_name = proposed_change.get("field", "")
        old_value = proposed_change.get("old_value", "")
        proposed_value = proposed_change.get("description") or proposed_change.get("new_value", "")
    elif target_table == "character_states":
        # M3c-B: state changes (always operation='create', target_id=null)
        entity_type = ""
        entity_name = proposed_change.get("character_name", "")
        field_name = "state_snapshot"
        old_value = ""
        proposed_value = proposed_change.get("state_snapshot", "")
    else:
        entity_type = ""
        entity_name = ""
        field_name = ""
        old_value = ""
        proposed_value = ""
    return {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "field_name": field_name,
        "old_value": old_value,
        "proposed_value": proposed_value,
    }
```

- [ ] **Step 5: Extend accept handler with character_states branch**

In `app/api/pending_updates.py:131-191`, replace the `accept_pending` function body. The character_states branch goes inside the `operation == "create"` block, after the lore_entries branch and before the `else`:

```python
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
            elif p.target_table == "character_states":
                # M3c-B: INSERT temporal row + mirror to characters.current_state
                char_id = data.get("character_id")
                if char_id is None:
                    raise HTTPException(
                        status_code=500,
                        detail="character_states pending missing character_id",
                    )
                char = db.get(Character, char_id)
                if char is None:
                    raise HTTPException(
                        status_code=500, detail="target character gone")
                state = CharacterState(
                    character_id=char_id,
                    chapter_id=p.chapter_id,
                    state_snapshot=data.get("state_snapshot", ""),
                    change_summary=data.get("change_summary", ""),
                    extractor_log_id=p.extractor_log_id,
                    pending_update_id=p.id,
                )
                db.add(state)
                db.flush()  # get state.id for audit
                # Mirror strategy B: characters.current_state = latest snapshot
                char.current_state = data.get("state_snapshot", "")
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
```

- [ ] **Step 6: Run accept tests to verify pass**

Run: `pytest tests/test_pending_updates.py -v`
Expected: ALL PASS (existing M3a tests + 3 new ones).

- [ ] **Step 7: Commit**

```bash
git add app/api/pending_updates.py tests/test_pending_updates.py
git commit -m "feat(m3c-b): pending accept handler supports character_states"
```

---

## Task 6: GET /api/characters/{id}/states endpoint

**Files:**
- Create: `app/api/characters_states.py`
- Modify: `app/main.py:49` (register router after characters router)
- Create: `tests/test_characters_states.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_characters_states.py`:

```python
"""M3c-B: GET /api/characters/{id}/states endpoint."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_state_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [
                {"character_name": "李雷",
                 "state_snapshot": "愤怒", "change_summary": "被伏击"},
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake.embed = MagicMock(return_value=[[0.0] * 1024])
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _setup_and_accept_state(client):
    """Finalize → accept the state_changes pending → return (pid, char_id, chapter_id)."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "第一章", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_p = next(p for p in pendings if p["target_table"] == "character_states")
    client.post(f"/api/pending-updates/{state_p['id']}/accept")
    return pid, cid, ch


def test_list_states_404_unknown_character(client):
    r = client.get("/api/characters/99999/states")
    assert r.status_code == 404


def test_list_states_empty(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    r = client.get(f"/api/characters/{cid}/states")
    assert r.status_code == 200
    assert r.json() == []


def test_list_states_default_desc(client, fake_state_router):
    """Default order is desc (latest chapter first)."""
    pid, cid, ch1 = _setup_and_accept_state(client)
    # Add a second chapter + state
    ch2 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "第二章", "content": "y",
    }).json()["id"]
    client.post(f"/api/chapters/{ch2}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_p = next(p for p in pendings
                   if p["target_table"] == "character_states" and p["status"] == "pending")
    client.post(f"/api/pending-updates/{state_p['id']}/accept")

    r = client.get(f"/api/characters/{cid}/states")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # Desc: ch2 (order=2) first
    assert data[0]["chapter_order"] == 2
    assert data[1]["chapter_order"] == 1
    # Each row includes chapter_title and chapter_order join fields
    assert data[0]["chapter_title"] == "第二章"
    assert data[0]["state_snapshot"] == "愤怒"
    assert data[0]["change_summary"] == "被伏击"


def test_list_states_explicit_asc(client, fake_state_router):
    pid, cid, _ = _setup_and_accept_state(client)
    r = client.get(f"/api/characters/{cid}/states?order=asc")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["chapter_order"] == 1


def test_list_states_limit_cap(client, fake_state_router):
    """limit > 100 should be capped to 100."""
    pid, cid, _ = _setup_and_accept_state(client)
    r = client.get(f"/api/characters/{cid}/states?limit=500")
    assert r.status_code == 200  # not 422 — capped silently
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_characters_states.py -v`
Expected: FAIL — endpoint doesn't exist (404 from FastAPI default route, not our 404).

- [ ] **Step 3: Create characters_states.py**

Create `app/api/characters_states.py`:

```python
"""M3c-B: GET /api/characters/{id}/states — list a character's state history."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character, CharacterState, Chapter
from app.models.character_state import CharacterStateRead

router = APIRouter()


@router.get("/{character_id}/states", response_model=list[CharacterStateRead])
def list_character_states(
    character_id: int,
    order: str = Query("desc", pattern="^(desc|asc)$"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    char = db.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=404, detail="character not found")

    stmt = (
        select(CharacterState, Chapter)
        .join(Chapter, Chapter.id == CharacterState.chapter_id)
        .where(CharacterState.character_id == character_id)
    )
    if order == "desc":
        stmt = stmt.order_by(Chapter.order_index.desc(),
                             CharacterState.created_at.desc())
    else:
        stmt = stmt.order_by(Chapter.order_index.asc(),
                             CharacterState.created_at.asc())
    stmt = stmt.limit(limit)

    rows = list(db.execute(stmt))
    return [
        CharacterStateRead(
            id=cs.id,
            character_id=cs.character_id,
            chapter_id=cs.chapter_id,
            chapter_title=ch.title,
            chapter_order=ch.order_index,
            state_snapshot=cs.state_snapshot,
            change_summary=cs.change_summary,
            extractor_log_id=cs.extractor_log_id,
            pending_update_id=cs.pending_update_id,
            created_at=cs.created_at,
            updated_at=cs.updated_at,
        )
        for cs, ch in rows
    ]
```

- [ ] **Step 4: Register router in main.py**

In `app/main.py`, after the `characters.router` import and include (line 49), add:

```python
from app.api import characters_states
# ...
app.include_router(characters_states.router, prefix="/api/characters",
                   tags=["characters"])
```

Place the `include_router` call AFTER the existing `characters.router` registration so both share the `/api/characters` prefix without conflict.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_characters_states.py -v`
Expected: ALL 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/characters_states.py app/main.py tests/test_characters_states.py
git commit -m "feat(m3c-b): GET /api/characters/{id}/states endpoint"
```

---

## Task 7: Frontend types + API client

**Files:**
- Modify: `web/lib/types.ts:271-307` (PendingUpdate section)
- Modify: `web/lib/api.ts:108-128` (Pending Updates section)

- [ ] **Step 1: Add CharacterState interface + widen PendingUpdateRead**

In `web/lib/types.ts`, append to the `// === M3a: Pending Updates ===` section (after `PendingStatus`):

```typescript
// === M3c-B: Character States ===

export interface CharacterState {
  id: number;
  character_id: number;
  chapter_id: number;
  chapter_title: string;
  chapter_order: number;
  state_snapshot: string;
  change_summary: string;
  extractor_log_id: number | null;
  pending_update_id: number | null;
  created_at: string;
  updated_at: string;
}
```

And update the `PendingUpdateRead.target_table` union on line ~277 from:

```typescript
  target_table: "characters" | "lore_entries";
```

to:

```typescript
  target_table: "characters" | "lore_entries" | "character_states";
```

- [ ] **Step 2: Add listCharacterStates to api.ts**

In `web/lib/api.ts`, update the import on line 1-10 to include `CharacterState`:

```typescript
import type {
  Project, ProjectCreate, ProjectUpdate,
  WorldOverview, WorldOverviewUpdate,
  LoreEntry, LoreCreate, LoreUpdate,
  Character, CharacterCreate, CharacterUpdate,
  Chapter, ChapterCreate, ChapterUpdate,
  GenerationLogRead, GenerationLogDetail,
  PendingUpdateRead, PendingUpdateDetail,
  FinalizeResponse, PendingStatus,
  CharacterState,
} from "./types";
```

Then inside the `api` object (after `finalizeChapter`), add:

```typescript
  // M3c-B: Character States
  listCharacterStates: (
    characterId: number,
    opts?: { order?: "desc" | "asc"; limit?: number },
  ) =>
    http<CharacterState[]>(
      `/api/characters/${characterId}/states${qs({
        order: opts?.order ?? "desc",
        limit: opts?.limit ?? 20,
      } as Record<string, unknown>)}`,
    ),
```

- [ ] **Step 3: Run frontend typecheck**

Run: `cd web && npm run typecheck 2>/dev/null || npx tsc --noEmit`
Expected: 0 errors. If `npm run typecheck` doesn't exist, check `web/package.json` scripts and use whatever variant exists; if none, run `npx tsc --noEmit`.

- [ ] **Step 4: Commit**

```bash
git add web/lib/types.ts web/lib/api.ts
git commit -m "feat(m3c-b): frontend types + api client for character states"
```

---

## Task 8: useCharacterStates hook + accept invalidation

**Files:**
- Modify: `web/lib/queries.ts:212-223` (`useAcceptPendingUpdate`)
- Modify: `web/lib/queries.ts` (append after `useRejectPendingUpdate`)

- [ ] **Step 1: Add useCharacterStates hook**

In `web/lib/queries.ts`, after `useRejectPendingUpdate` (end of file), append:

```typescript

// === M3c-B: Character States ===

export function useCharacterStates(characterId: number | null) {
  return useQuery({
    queryKey: ["character-states", characterId],
    queryFn: () => api.listCharacterStates(characterId!),
    enabled: characterId != null,
  });
}
```

- [ ] **Step 2: Update useAcceptPendingUpdate invalidation**

The current `onSuccess` doesn't know which character_id was affected. Change `useAcceptPendingUpdate` to read the response and invalidate the right `character-states` cache:

Replace `web/lib/queries.ts:212-223` with:

```typescript
export function useAcceptPendingUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.acceptPendingUpdate(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
      qc.invalidateQueries({ queryKey: ["characters"] });
      qc.invalidateQueries({ queryKey: ["lore"] });
      // M3c-B: character_states target_id is null; read character_id from
      // proposed_change via the detail endpoint. Simpler: invalidate all
      // character-states caches (single-user, low cardinality).
      if (data.target_table === "character_states") {
        qc.invalidateQueries({ queryKey: ["character-states"] });
      }
    },
  });
}
```

**Note:** `PendingUpdateRead` returned by accept doesn't include `proposed_change` (it's only in `PendingUpdateDetail`). The simpler path is to invalidate all `["character-states"]` queries regardless — single-user local app, low cost. The code above does that.

- [ ] **Step 3: Run typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add web/lib/queries.ts
git commit -m "feat(m3c-b): useCharacterStates hook + accept invalidation"
```

---

## Task 9: PendingUpdateItem — state_changes card branch

**Files:**
- Modify: `web/components/entities/PendingUpdateItem.tsx`
- Modify: `web/tests/PendingUpdateItem.test.tsx`

- [ ] **Step 1: Write failing test**

Append to `web/tests/PendingUpdateItem.test.tsx` (inside the existing `describe` block or as a new one):

```typescript
describe("PendingUpdateItem — character_states", () => {
  const statePending: PendingUpdateRead = {
    ...basePending,
    id: 2,
    update_type: "soft_fact",
    target_table: "character_states",
    entity_name: "李雷",
    field_name: "state_snapshot",
    proposed_value: "愤怒且受伤；决心复仇",
    reason: "chapter_id=5 状态变化",
  };

  it("renders state change card with 📝 icon and snapshot", () => {
    renderWithProviders(<PendingUpdateItem pending={statePending} />);
    expect(screen.getByText(/📝/)).toBeTruthy();
    expect(screen.getByText(/状态变化/)).toBeTruthy();
    expect(screen.getByText(/李雷/)).toBeTruthy();
    expect(screen.getByText(/愤怒且受伤；决心复仇/)).toBeTruthy();
  });

  it("does not render 旧值/新值 diff for state changes", () => {
    renderWithProviders(<PendingUpdateItem pending={statePending} />);
    // state_snapshot already shown via proposed_value; should NOT also show
    // "新值：" prefix (which is for update ops with field_name)
    expect(screen.queryByText(/新值：/)).toBeNull();
  });
});
```

If `basePending` is defined in that file (it is, per the head we read), the spread should work. Adjust field set if `basePending` is missing any required field.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/PendingUpdateItem.test.tsx`
Expected: FAIL — current PendingUpdateItem treats character_states as lore (since `isCharacter=false`).

- [ ] **Step 3: Update PendingUpdateItem.tsx**

Replace `web/components/entities/PendingUpdateItem.tsx` contents with:

```typescript
"use client";

import { Button } from "@/components/ui/Button";
import { useAcceptPendingUpdate, useRejectPendingUpdate } from "@/lib/queries";
import { loreTypeLabel } from "@/lib/types";
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

  const isStateChange = pending.target_table === "character_states";
  const isCharacter = pending.target_table === "characters";
  const isLore = pending.target_table === "lore_entries";

  // Header rendering
  let icon: string;
  let headerLabel: string;
  if (isStateChange) {
    icon = "📝";
    headerLabel = `状态变化 · ${pending.entity_name}`;
  } else {
    const entityLabel = isCharacter ? "人物" : "设定";
    const opLabel = pending.operation === "create" ? "新建" : "更新";
    icon = pending.operation === "create" ? "✏️" : "🔄";
    headerLabel = `${opLabel}${entityLabel} · ${pending.entity_name}${
      pending.field_name ? ` · ${pending.field_name}` : ""
    }`;
  }

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
            <strong>{headerLabel}</strong>
          </span>
        </div>
        {isLore && pending.entity_type && (
          <span className="text-xs text-text-dim">[{loreTypeLabel(pending.entity_type)}]</span>
        )}
      </div>

      <div className="text-xs text-text-muted mb-2 pl-6">
        {isStateChange ? (
          <div>{pending.proposed_value}</div>
        ) : pending.field_name ? (
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
          {` · ${formatTime(pending.updated_at)}`}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run all PendingUpdateItem tests**

Run: `cd web && npx vitest run tests/PendingUpdateItem.test.tsx`
Expected: ALL PASS (existing M3a tests + 2 new ones).

If existing tests asserted specific DOM structure (e.g., `screen.getByText("新建人物 · 韩梅")`), the new code splits the entity name into the bold tag — adjust assertions to use regex matchers like `/新建人物.*韩梅/`.

- [ ] **Step 5: Commit**

```bash
git add web/components/entities/PendingUpdateItem.tsx web/tests/PendingUpdateItem.test.tsx
git commit -m "feat(m3c-b): PendingUpdateItem renders state_changes cards"
```

---

## Task 10: CharacterStateTimeline component

**Files:**
- Create: `web/components/entities/CharacterStateTimeline.tsx`
- Create: `web/tests/CharacterStateTimeline.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `web/tests/CharacterStateTimeline.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CharacterStateTimeline } from "@/components/entities/CharacterStateTimeline";
import type { CharacterState } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useCharacterStates: (id: number | null) => ({
    data: id === null ? [] : MOCK_STATES,
    isLoading: false,
  }),
}));

const MOCK_STATES: CharacterState[] = [
  {
    id: 2, character_id: 1, chapter_id: 5,
    chapter_title: "残月重逢", chapter_order: 5,
    state_snapshot: "愤怒且受伤", change_summary: "被韩梅伏击",
    extractor_log_id: 10, pending_update_id: 20,
    created_at: "2026-06-20T14:30:00Z", updated_at: "2026-06-20T14:30:00Z",
  },
  {
    id: 1, character_id: 1, chapter_id: 3,
    chapter_title: "入城", chapter_order: 3,
    state_snapshot: "警惕", change_summary: "初入青石城",
    extractor_log_id: 8, pending_update_id: 18,
    created_at: "2026-06-19T10:00:00Z", updated_at: "2026-06-19T10:00:00Z",
  },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("CharacterStateTimeline", () => {
  it("renders header with count", () => {
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    expect(screen.getByText(/状态轨迹.*2/)).toBeTruthy();
  });

  it("is collapsed by default", () => {
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    // State snapshot text should not be visible until expanded
    expect(screen.queryByText("愤怒且受伤")).toBeNull();
  });

  it("expands on click and shows states", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    await user.click(screen.getByRole("button", { name: /状态轨迹/ }));
    expect(screen.getByText("愤怒且受伤")).toBeTruthy();
    expect(screen.getByText("警惕")).toBeTruthy();
    expect(screen.getByText(/第 5 章 · 残月重逢/)).toBeTruthy();
    expect(screen.getByText(/被韩梅伏击/)).toBeTruthy();
  });

  it("renders empty state when no history", () => {
    renderWithProviders(<CharacterStateTimeline characterId={null} />);
    // When characterId is null, hook returns []; show placeholder
    expect(screen.getByText(/暂无状态轨迹/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run tests/CharacterStateTimeline.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Create the component**

Create `web/components/entities/CharacterStateTimeline.tsx`:

```typescript
"use client";

import { useState } from "react";
import { useCharacterStates } from "@/lib/queries";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function CharacterStateTimeline({ characterId }: { characterId: number | null }) {
  const [expanded, setExpanded] = useState(false);
  const { data: states = [], isLoading } = useCharacterStates(characterId);
  const count = states.length;

  if (characterId === null) {
    return (
      <div className="border-t border-line pt-3 mt-4">
        <p className="text-xs text-text-muted">
          暂无状态轨迹记录。完成章节后 Extractor 会自动抽取显著状态变化。
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-line pt-3 mt-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="text-sm text-text-muted-bright hover:text-text w-full text-left flex items-center gap-1"
      >
        <span>{expanded ? "▼" : "▶"}</span>
        <span>状态轨迹（{count} 条）</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {isLoading ? (
            <p className="text-xs text-text-muted">加载中...</p>
          ) : count === 0 ? (
            <p className="text-xs text-text-muted">
              暂无状态轨迹记录。完成章节后 Extractor 会自动抽取显著状态变化。
            </p>
          ) : (
            states.map((s) => (
              <div
                key={s.id}
                className="border border-line rounded p-2 bg-input/30"
              >
                <div className="text-xs text-text-dim mb-1">
                  第 {s.chapter_order} 章 · {s.chapter_title}
                </div>
                <div className="text-sm text-text mb-1">
                  状态：{s.state_snapshot}
                </div>
                {s.change_summary && (
                  <div className="text-xs text-text-muted mb-1">
                    原因：{s.change_summary}
                  </div>
                )}
                <div className="text-[10px] text-text-dim">
                  抽取于 {formatTime(s.created_at)}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd web && npx vitest run tests/CharacterStateTimeline.test.tsx`
Expected: ALL 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/components/entities/CharacterStateTimeline.tsx web/tests/CharacterStateTimeline.test.tsx
git commit -m "feat(m3c-b): CharacterStateTimeline collapsible component"
```

---

## Task 11: Mount timeline in CharacterForm

**Files:**
- Modify: `web/components/entities/CharacterForm.tsx:107-176`

- [ ] **Step 1: Update imports + mount timeline**

In `web/components/entities/CharacterForm.tsx`:

Update the imports at the top to include the new component:

```typescript
import { CharacterStateTimeline } from "@/components/entities/CharacterStateTimeline";
```

Then at the end of the returned JSX (right before the closing `</div>` of the outer `space-y-4` container, after the "活动地点" block ending around line 173), insert:

```typescript
      <CharacterStateTimeline characterId={character.id} />
```

The final JSX structure should look like:

```typescript
  return (
    <div className="p-4 space-y-4 max-w-2xl">
      {/* ... header + text fields + affiliations + locations ... */}

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">活动地点</label>
        <div className="flex flex-wrap gap-1">
          {locations.map((l) => (
            <Chip
              key={l.id}
              selected={(form.known_locations ?? character.affiliations ?? []).includes(l.id)}
              onClick={() => toggleLoc(l.id)}
            >
              {l.name}
            </Chip>
          ))}
        </div>
      </div>

      <CharacterStateTimeline characterId={character.id} />
    </div>
  );
```

- [ ] **Step 2: Run typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Run all frontend unit tests**

Run: `cd web && npx vitest run`
Expected: ALL PASS (existing + new).

- [ ] **Step 4: Commit**

```bash
git add web/components/entities/CharacterForm.tsx
git commit -m "feat(m3c-b): mount CharacterStateTimeline in character form"
```

---

## Task 12: E2E test

**Files:**
- Create: `web/tests/e2e/finalize-character-state.spec.ts`

- [ ] **Step 1: Write the E2E test**

Create `web/tests/e2e/finalize-character-state.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test("finalize produces state_changes pending → accept → see in character timeline", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + character + chapter via API
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M3c-B" },
  }).then((r) => r.json());
  const pid = project.id;

  const char = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷", current_state: "警惕" },
  }).then((r) => r.json());
  const cid = char.id;

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid, order_index: 1, title: "伏击",
      content: "李雷被韩梅伏击受伤，左臂中刀。他决心复仇。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock finalize response with a state_changes entry
  await page.route(`**/api/chapters/${chId}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId,
        summary: "李雷被伏击。",
        pending_created: 1,
        log_id: 999,
      }),
    });
  });

  // 3. Mock pending list to include a state_changes entry
  await page.route(`**/api/pending-updates*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 50, project_id: pid, chapter_id: chId,
          update_type: "soft_fact", operation: "create",
          target_table: "character_states", target_id: null,
          reason: "chapter_id=1 状态变化",
          status: "pending",
          entity_name: "李雷", entity_type: "",
          field_name: "state_snapshot", old_value: "",
          proposed_value: "愤怒且受伤；决心复仇",
          created_at: "2026-06-20T14:00:00Z",
          updated_at: "2026-06-20T14:00:00Z",
        },
      ]),
    });
  });

  // 4. Mock accept → returns accepted status
  await page.route(`**/api/pending-updates/50/accept`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 50, project_id: pid, chapter_id: chId,
        update_type: "soft_fact", operation: "create",
        target_table: "character_states", target_id: null,
        reason: "chapter_id=1 状态变化",
        status: "accepted",
        entity_name: "李雷", entity_type: "",
        field_name: "state_snapshot", old_value: "",
        proposed_value: "愤怒且受伤；决心复仇",
        created_at: "2026-06-20T14:00:00Z",
        updated_at: "2026-06-20T14:01:00Z",
      }),
    });
  });

  // 5. Mock character-states endpoint to return the accepted state
  await page.route(`**/api/characters/${cid}/states*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 1, character_id: cid, chapter_id: chId,
          chapter_title: "伏击", chapter_order: 1,
          state_snapshot: "愤怒且受伤；决心复仇",
          change_summary: "被伏击",
          extractor_log_id: 999, pending_update_id: 50,
          created_at: "2026-06-20T14:01:00Z",
          updated_at: "2026-06-20T14:01:00Z",
        },
      ]),
    });
  });

  // 6. Mock character detail to show mirrored current_state
  await page.route(`**/api/characters/${cid}`, (route) => {
    // Only respond to GET (not PATCH); let PATCH fall through
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...char,
        current_state: "愤怒且受伤；决心复仇",
      }),
    });
  });

  // 7. Mock characters list to include updated character
  await page.route(`**/api/characters?*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { ...char, current_state: "愤怒且受伤；决心复仇" },
      ]),
    });
  });

  // 8. Navigate to pending page → accept state_changes pending
  await page.goto(`http://localhost:3300/projects/${pid}/pending`);
  await expect(page.getByText(/状态变化.*李雷/)).toBeVisible();
  await page.getByRole("button", { name: /接受/ }).first().click();
  await expect(page.getByText(/已接受/)).toBeVisible();

  // 9. Navigate to characters page → open character → expand timeline
  await page.goto(`http://localhost:3300/projects/${pid}/characters`);
  await page.getByText("李雷").click();
  await page.getByRole("button", { name: /状态轨迹/ }).click();

  // 10. Verify timeline shows the state
  await expect(page.getByText(/第 1 章 · 伏击/)).toBeVisible();
  await expect(page.getByText(/愤怒且受伤；决心复仇/)).toBeVisible();
});
```

- [ ] **Step 2: Start backend + frontend**

In one terminal: `uv run uvicorn app.main:app --port 8005 --reload`
In another: `cd web && npm run dev` (ensure PORT=3300)

- [ ] **Step 3: Run the E2E test**

Run: `cd web && npx playwright test tests/e2e/finalize-character-state.spec.ts`
Expected: PASS.

If the test flakes on element visibility timing, add explicit `await page.waitForResponse(...)` for the accept call.

- [ ] **Step 4: Commit**

```bash
git add web/tests/e2e/finalize-character-state.spec.ts
git commit -m "test(m3c-b): e2e finalize → accept state → see timeline"
```

---

## Task 13: Full regression + manual smoke test

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `pytest -v`
Expected: ALL tests pass. If any M3a tests broke due to `current_state` removal from `ALLOWED_CHARACTER_FIELDS`, fix them now (they should assert through `state_changes` path instead).

- [ ] **Step 2: Run full frontend test suite**

Run: `cd web && npx vitest run`
Expected: ALL pass.

- [ ] **Step 3: Run all E2E tests**

Run: `cd web && npx playwright test`
Expected: ALL pass (existing + new).

- [ ] **Step 4: Manual smoke test**

1. Start backend: `uv run uvicorn app.main:app --port 8005 --reload`
2. Start frontend: `cd web && npm run dev`
3. Open `http://localhost:3300`
4. Create or open an existing project
5. Add a character "李雷" with `current_state="警惕"`
6. Create a chapter with content describing a state change (e.g., "李雷被伏击，左臂中刀。他决心复仇。")
7. Click "完成本章" → wait for toast
8. Navigate to 📋 待处理 → verify 📝 状态变化 · 李雷 card visible
9. Accept → verify card shows "已接受"
10. Navigate to 👥 人物 → click 李雷 → expand 状态轨迹 → verify state shown
11. Verify ActivityBar badge decremented

- [ ] **Step 5: Verify Alembic state is clean**

Run: `uv run alembic current`
Expected: shows `<hash> (head)`

- [ ] **Step 6: Update memory file**

Update `/Users/bugx/.claude/projects/-Users-bugx-novelAI/memory/novelai-m2b-status.md` to add M3c-B to the completed list and note next milestone is M3c-A (relationships) or M4 Reviewer.

- [ ] **Step 7: Final commit (if any cleanup)**

```bash
git status
# If clean, done. If not:
git add -A
git commit -m "chore(m3c-b): post-implementation cleanup"
```

---

## Self-Review Notes

**Spec coverage check:**
- §1.1 (5 goals): Tasks 1, 4, 5, 6, 10/11 — covered
- §3.1 schema: Task 1 — covered
- §3.3 Alembic: Task 1 — covered
- §4.1 prompt changes: Task 3 — covered (both removing current_state from updated_characters enum + adding state_changes section + adding 现状= in user.j2)
- §4.2 LLM response format: Task 4 tests — covered
- §4.3 _build_pending_rows: Task 4 — covered
- §5.2 accept handler: Task 5 — covered (mirror + INSERT)
- §5.3 PendingUpdateRead summary fields: Task 5 step 4 — covered
- §5.4 GET /api/characters/{id}/states: Task 6 — covered
- §6.1 PendingUpdateItem: Task 9 — covered
- §6.2 CharacterStateTimeline: Task 10 — covered
- §6.3 hooks: Task 8 — covered
- §7 tests: Tasks 1, 3, 4, 5, 6, 9, 10, 12 — covered
- §8 acceptance checklist: Task 13 — covered

**Type consistency:**
- `CharacterState` (ORM) → `CharacterStateRead` (Pydantic) → `CharacterState` (TS) — field names match (`state_snapshot`, `change_summary`, `chapter_title`, `chapter_order`, `extractor_log_id`, `pending_update_id`)
- `_build_pending_rows` signature: `state_changes: list[dict] | None = None` — defaults to None, function treats as `[]`
- `proposed_change` shape for character_states: `{character_id, character_name, state_snapshot, change_summary}` — used consistently in extractor (Task 4) and accept handler (Task 5)
- API path: `/api/characters/{id}/states` matches in main.py (Task 6) and frontend api.ts (Task 7)
- `target_table` union widened in TS types (Task 7) to include `"character_states"`

**Known compromises:**
- `useAcceptPendingUpdate` invalidates ALL `["character-states"]` queries instead of the specific one — acceptable for single-user local app; `PendingUpdateRead` doesn't carry `proposed_change` so we can't read character_id from response without an extra detail fetch
- E2E test mocks everything (no real LLM) — consistent with M3a/M3b E2E pattern
- Manual smoke test (Task 13 step 4) requires real LLM credentials in `.env` — if user doesn't have them, skip with a note
