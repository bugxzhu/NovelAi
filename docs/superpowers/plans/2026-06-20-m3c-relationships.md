# M3c-A 关系演变（relationships）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AI 记住人物关系及其演变——Extractor 抽取章节末的关系变化（新建/转变/破裂），accept 时事务内软失效旧版 + INSERT 新版，retrieval 自动注入涉及人物的当前关系，前端管理页支持手动 CRUD + 查看演变历史。

**Architecture:** 单向关系（from→to）时序表 + 部分唯一索引保证同方向只有一条当前有效。版本切换走"accept 自动软失效旧版 + INSERT 新版"模式（沿用 M3c-B 的"一次点击做两件事"风格）。retrieval 填充 M2a 已预留的 `ContextBundle.relationships=[]` 占位。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + SQLite（部分唯一索引）；Next.js 15 + React + TanStack Query + Vitest + Playwright。

**Spec:** `docs/superpowers/specs/2026-06-20-m3c-relationships-design.md`

**Port conventions:** Backend `http://127.0.0.1:8005`, Frontend `http://localhost:3300`.

---

## File Structure

**Backend new files:**
- `app/models/relationship.py` — `RelationshipRead`, `RelationshipHistoryItem`, `RelationshipCreate`, `RelationshipUpdate`, `RelationshipSoftCloseBody`
- `app/api/relationships.py` — GET list / GET history / POST create / PATCH update / DELETE / POST soft-close
- `alembic/versions/<hash>_add_relationships.py` — Alembic migration
- `tests/test_relationship_schema.py` — schema + partial unique index tests
- `tests/test_extractor_relationships.py` — relationship_changes extraction tests
- `tests/test_relationships_api.py` — CRUD + history + soft-close tests

**Backend modified files:**
- `app/memory/schema.py` — add `Relationship` ORM
- `app/agents/extractor.py` — add `relationship_changes` param + branch in `_build_pending_rows`; pass `existing_relationships` for prompt context
- `app/memory/retrieval.py` — populate `ContextBundle.relationships`
- `app/api/pending_updates.py` — extend `_derive_summary_fields` + accept handler with relationships branch (version-switch)
- `app/main.py` — register relationships router
- `app/llm/prompts/extractor/system.j2` — add relationship_changes JSON schema + extraction rules
- `app/llm/prompts/extractor/user.j2` — render existing_relationships section
- `tests/test_extractor_prompts.py` — add relationship section tests
- `tests/test_pending_updates.py` — add relationship accept/reject tests
- `tests/test_context_assembly.py` — add relationship injection tests

**Frontend new files:**
- `web/app/projects/[projectId]/relationships/page.tsx` — management page
- `web/components/entities/RelationshipForm.tsx` — create/edit form
- `web/components/entities/RelationshipList.tsx` — left list
- `web/components/entities/RelationshipHistoryPanel.tsx` — version timeline
- `web/tests/RelationshipForm.test.tsx` — unit tests
- `web/tests/RelationshipHistoryPanel.test.tsx` — unit tests
- `web/tests/e2e/finalize-relationship.spec.ts` — E2E

**Frontend modified files:**
- `web/components/layout/ActivityBar.tsx` — add 🤝 icon (between characters and lore)
- `web/components/entities/PendingUpdateItem.tsx` — add 🤝 relationship card branch
- `web/lib/types.ts` — add Relationship types
- `web/lib/api.ts` — add relationships endpoints
- `web/lib/queries.ts` — add useRelationships + CRUD hooks; extend useAcceptPendingUpdate invalidation
- `web/tests/PendingUpdateItem.test.tsx` — add relationship card test

---

## Task 1: Add Relationship ORM + Alembic migration

**Files:**
- Modify: `app/memory/schema.py` (append after `CharacterState` class, end of file)
- Create: `alembic/versions/<hash>_add_relationships.py`
- Create: `tests/test_relationship_schema.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_relationship_schema.py`:

```python
"""Schema-level tests for Relationship ORM (M3c-A)."""
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.memory.schema import (
    Chapter, Character, Project, Relationship,
)


def _seed_project_and_two_characters(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    return p, c1, c2


def test_relationship_table_columns(db_session):
    """Verify the relationships table has the expected columns."""
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("relationships")}
    expected = {
        "id", "project_id", "from_char_id", "to_char_id",
        "type", "strength", "description",
        "valid_from_chapter", "valid_to_chapter",
        "change_summary", "extractor_log_id", "pending_update_id",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_relationship_indexes_exist(db_session):
    """Verify indexes (including partial unique) were created."""
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("relationships")}
    assert "idx_rel_from_to_current" in index_names
    assert "idx_rel_project" in index_names
    assert "uq_rel_current" in index_names


def test_relationship_partial_unique_blocks_second_current(db_session):
    """Same from→to direction cannot have two valid_to=NULL rows."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()

    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5, description="",
        valid_from_chapter=ch.id,
    ))
    db_session.commit()

    # Second current-valid for same direction should fail
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.5, description="",
        valid_from_chapter=ch.id,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_relationship_partial_unique_allows_history(db_session):
    """Same direction can have multiple rows if older ones have valid_to set."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch1 = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2", content="x")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # Old version (soft-closed)
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5,
        valid_from_chapter=ch1.id, valid_to_chapter=ch2.id,
    ))
    # New current version
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.5,
        valid_from_chapter=ch2.id,
    ))
    db_session.commit()  # should not raise

    rows = list(db_session.scalars(
        select(Relationship).where(
            Relationship.from_char_id == c1.id,
            Relationship.to_char_id == c2.id,
        )
    ))
    assert len(rows) == 2


def test_relationship_reverse_direction_independent(db_session):
    """A→B and B→A are independent records (both can be current-valid)."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()

    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="暗恋", strength=0.7,
        valid_from_chapter=ch.id,
    ))
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c2.id, to_char_id=c1.id,
        type="朋友", strength=0.3,
        valid_from_chapter=ch.id,
    ))
    db_session.commit()  # should NOT raise — opposite directions


def test_relationship_cascade_delete_with_character(db_session):
    """Deleting a character cascades to all their relationships."""
    p, c1, c2 = _seed_project_and_two_characters(db_session)
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="朋友", strength=0.5,
        valid_from_chapter=ch.id,
    ))
    db_session.commit()

    db_session.delete(c1)
    db_session.commit()

    rows = list(db_session.scalars(select(Relationship)))
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_relationship_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'Relationship' from 'app.memory.schema'`

- [ ] **Step 3: Add Relationship ORM to schema.py**

Append to `app/memory/schema.py` (after the `CharacterState` class, end of file):

```python
class Relationship(Base):
    """Temporal log of directed relationships between characters. M3c-A:
    append-only version log — accept handler soft-closes the previous current-valid
    row (sets valid_to_chapter) before INSERTing a new one. The partial unique
    index uq_rel_current guarantees at most one current-valid row per direction."""
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_char_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    to_char_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(nullable=False, default=0.0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    valid_from_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_update_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        # Partial indexes on SQLite — declared via sqlite_where in Index.
        # autogenerate does not handle sqlite_where; migration writes them manually.
        Index(
            "idx_rel_from_to_current",
            "from_char_id", "to_char_id",
            sqlite_where=text("valid_to_chapter IS NULL"),
        ),
        Index("idx_rel_project", "project_id", "from_char_id"),
        # Partial UNIQUE: same direction can only have one current-valid row.
        Index(
            "uq_rel_current", "from_char_id", "to_char_id",
            unique=True,
            sqlite_where=text("valid_to_chapter IS NULL"),
        ),
    )
```

Add `text` to the sqlalchemy import at the top of schema.py:

```python
from sqlalchemy import ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint, text
```

Note: `Float` is not strictly needed — SQLAlchemy infers it from `Mapped[float]`. The `nullable=False, default=0.0` on `strength` is sufficient.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_relationship_schema.py -v`
Expected: PASS (6 tests). `Base.metadata.create_all` in `init_db` creates the table + partial indexes automatically via the ORM definition.

- [ ] **Step 5: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add relationships"`

**WARNING:** Per M3c-B Task 1 experience, autogenerate may produce an empty migration body if `data/novelai.db` has already been schema-updated via `init_db`. If upgrade()/downgrade() are `pass`, write the body manually.

Expected migration body:

```python
def upgrade() -> None:
    op.create_table(
        'relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('from_char_id', sa.Integer(), nullable=False),
        sa.Column('to_char_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('strength', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('valid_from_chapter', sa.Integer(), nullable=False),
        sa.Column('valid_to_chapter', sa.Integer(), nullable=True),
        sa.Column('change_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_char_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['to_char_id'], ['characters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Partial indexes (sqlite_where clause) cannot be created via op.create_index
    # in older Alembic versions reliably; use raw SQL.
    op.execute(
        "CREATE INDEX idx_rel_from_to_current "
        "ON relationships(from_char_id, to_char_id) "
        "WHERE valid_to_chapter IS NULL"
    )
    op.create_index('idx_rel_project', 'relationships',
                    ['project_id', 'from_char_id'], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_rel_current "
        "ON relationships(from_char_id, to_char_id) "
        "WHERE valid_to_chapter IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rel_current")
    op.drop_index('idx_rel_project', table_name='relationships')
    op.execute("DROP INDEX IF EXISTS idx_rel_from_to_current")
    op.drop_table('relationships')
```

Set `down_revision = 'd9dd1e0c1224'` (M3c-B's character_states migration).

- [ ] **Step 6: Apply migration**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade d9dd1e0c1224 -> <hash>, add relationships`

Verify: `sqlite3 data/novelai.db ".schema relationships"` shows the table + 3 indexes.

If `data/novelai.db` was already schema-updated via init_db (autogenerate produced empty migration), you can verify the migration applies cleanly on a fresh DB by:
```
mv data/novelai.db data/novelai.db.bak
uv run alembic upgrade head
sqlite3 data/novelai.db ".schema relationships"
mv data/novelai.db.bak data/novelai.db  # restore
```

- [ ] **Step 7: Commit**

```bash
git add app/memory/schema.py alembic/versions/*_add_relationships.py tests/test_relationship_schema.py
git commit -m "feat(m3c-a): add relationships temporal table + migration"
```

---

## Task 2: Pydantic schemas for relationships

**Files:**
- Create: `app/models/relationship.py`

- [ ] **Step 1: Create the schemas**

Create `app/models/relationship.py`:

```python
from datetime import datetime

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class RelationshipRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    from_char_id: int
    from_char_name: str        # JOIN characters.name
    to_char_id: int
    to_char_name: str          # JOIN characters.name
    type: str
    strength: float
    description: str
    valid_from_chapter: int
    valid_to_chapter: int | None
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None


class RelationshipHistoryItem(BaseModel):
    """One row in the relationship evolution timeline (per direction pair)."""
    version_id: int            # relationships.id
    valid_from_chapter: int
    valid_to_chapter: int | None
    type: str
    strength: float
    description: str
    change_summary: str
    created_at: datetime


class RelationshipCreate(BaseModel):
    project_id: int
    from_char_id: int
    to_char_id: int
    type: str
    strength: float = 0.0
    description: str = ""
    valid_from_chapter: int = 0  # 0 = before any chapter (initial setup)
    change_summary: str = ""


class RelationshipUpdate(BaseModel):
    # Only type/strength/description are mutable. valid_from/to_chapter,
    # from/to_char_id, project_id are NOT (would break temporal semantics).
    type: str | None = None
    strength: float | None = None
    description: str | None = None


class RelationshipSoftCloseBody(BaseModel):
    valid_to_chapter: int
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from app.models.relationship import RelationshipRead, RelationshipHistoryItem, RelationshipCreate, RelationshipUpdate, RelationshipSoftCloseBody; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add app/models/relationship.py
git commit -m "feat(m3c-a): pydantic schemas for relationships"
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
def test_system_prompt_has_relationship_changes_section():
    """system.j2 must document relationship_changes extraction rules."""
    out = render("extractor/system.j2")
    assert "relationship_changes" in out
    assert "from_character_name" in out
    assert "to_character_name" in out
    assert "strength" in out
    # Boundary / direction guidance
    assert "单向" in out or "方向" in out


def test_user_prompt_lists_existing_relationships():
    """user.j2 must render existing_relationships (current-valid only)."""
    from types import SimpleNamespace
    chars = [
        SimpleNamespace(id=1, name="李雷"),
        SimpleNamespace(id=2, name="韩梅"),
    ]
    existing_rels = [
        SimpleNamespace(
            from_char_id=1, from_name="李雷",
            to_char_id=2, to_name="韩梅",
            type="旧友", strength=0.5, description="童年同伴",
        ),
    ]
    out = render("extractor/user.j2",
                 project=SimpleNamespace(title="T", genre="g", premise="p"),
                 chapter=SimpleNamespace(title="C", content="x", order_index=3),
                 existing_characters=chars,
                 existing_lore=[],
                 existing_relationships=existing_rels)
    assert "已有关系" in out
    assert "李雷 → 韩梅" in out
    assert "旧友" in out
    assert "0.5" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_extractor_prompts.py::test_system_prompt_has_relationship_changes_section tests/test_extractor_prompts.py::test_user_prompt_lists_existing_relationships -v`
Expected: FAIL — neither relationship section nor existing_relationships rendering exists yet.

- [ ] **Step 3: Update system.j2**

Add `relationship_changes` to the JSON output schema in `app/llm/prompts/extractor/system.j2`. Find the JSON example block (currently has summary/entities/state_changes). Add `relationship_changes` array after `state_changes`:

```
  "state_changes": [ ... ],
  "relationship_changes": [
    {
      "from_character_name": "已有人物名",
      "to_character_name": "已有人物名",
      "type": "关系类型（自由文本，如 仇人/旧友/师徒/暗恋）",
      "strength": -1.0,
      "description": "关系的具体表现或缘由（1-2 句话）",
      "change_summary": "触发本章关系变化的事件（1-2 句话）"
    }
  ]
}
```

Update the trailing line "如果某类抽取为空，对应数组返回空 []。永远不要省略字段（包括 state_changes）。" to also mention relationship_changes:

```
如果某类抽取为空，对应数组返回空 []。永远不要省略字段（包括 state_changes 和 relationship_changes）。
```

Then append a new section at the very end of system.j2 (after the existing state_changes 字段要求 section):

```
# 软事实：人物关系变化（relationship_changes）

抽取本章透露的**人物间关系变化**。一条关系是单向的（from → to）。

## 何时抽
仅当本章透露了人物间关系的明确变化时才抽：
- 新关系建立（首次相遇、结盟、结仇）
- 关系类型转变（朋友→仇人、陌生人→恋人）
- 关系强度显著变化（信任度大幅升降）
- 关系破裂（决裂、背叛、断绝）
- 关系属性补充（如"原来 X 是 Y 的私生子"——揭示隐藏关系）

## 不抽
- 人物本章只是同框出现但关系无变化
- 描写细节但未透露关系本身

## 字段要求
- `from_character_name`、`to_character_name`：必须是已有人物库中的名字（不要为新人物抽关系——先 accept 新人物再重抽）
- `type`：自由文本，简明描述关系类型（"仇人"、"旧友"、"暗恋"、"师徒"、"主仆"等）
- `strength`：-1.0（极度敌对）~ 1.0（极度亲密）；0.0 为中立
- `description`：1-2 句话，关系的具体表现或缘由
- `change_summary`：1-2 句话，触发本章关系变化的事件

## 重要：方向性
关系是单向的。"李雷暗恋韩梅" 和 "韩梅视李雷为朋友" 是两条独立记录，from/to 不可颠倒。
```

- [ ] **Step 4: Update user.j2**

Find the "## 已有设定" section in `app/llm/prompts/extractor/user.j2`. AFTER that section (before the closing "请抽取..." line), insert a new section:

```
## 已有关系（{{ existing_relationships|length }} 条当前有效）
{% for r in existing_relationships %}
- {{ r.from_name }} → {{ r.to_name }}：{{ r.type }}（强度 {{ r.strength }}）{% if r.description %} — {{ r.description }}{% endif %}
{% endfor %}
```

Update the closing line from:
```
请抽取本章的新实体、描述补充、以及人物状态变化。
```
to:
```
请抽取本章的新实体、描述补充、人物状态变化、以及人物关系变化。
```

- [ ] **Step 5: Run prompt tests to verify pass**

Run: `uv run pytest tests/test_extractor_prompts.py -v`
Expected: ALL PASS (existing + 2 new).

If the M3c-B test `test_user_prompt_shows_current_state_for_existing_characters` still passes (it uses real `Character` objects, not SimpleNamespace), leave it alone. The new test `test_user_prompt_lists_existing_relationships` uses SimpleNamespace which is fine since it only needs `.from_name` etc.

- [ ] **Step 6: Commit**

```bash
git add app/llm/prompts/extractor/system.j2 app/llm/prompts/extractor/user.j2 tests/test_extractor_prompts.py
git commit -m "feat(m3c-a): extractor prompts add relationship_changes section"
```

---

## Task 4: Extractor agent — relationship_changes branch

**Files:**
- Modify: `app/agents/extractor.py` (`_build_pending_rows` signature + body; `extract_chapter` to fetch existing relationships and pass them through)
- Create: `tests/test_extractor_relationships.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_extractor_relationships.py`:

```python
"""M3c-A: relationship_changes branch of _build_pending_rows + extract_chapter."""
import json
from unittest.mock import MagicMock

import pytest

from app.agents.extractor import _build_pending_rows
from app.llm.base import LLMResponse
from app.memory.schema import Character, Chapter, PendingUpdate, Project, Relationship


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    )


def _seed_two_characters(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=5, title="第五章", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷", role="protagonist")
    c2 = Character(project_id=p.id, name="韩梅", role="supporting")
    db_session.add_all([c1, c2]); db_session.flush()
    return p, ch, c1, c2


def test_build_pending_rows_relationship_changes_creates_soft_fact(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="claude-haiku-4-5",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "仇人", "strength": -0.8,
             "description": "李雷决心复仇",
             "change_summary": "韩梅伏击李雷"},
        ],
    )
    rel_rows = [r for r in rows if r.target_table == "relationships"]
    assert len(rel_rows) == 1
    r = rel_rows[0]
    assert r.update_type == "soft_fact"
    assert r.operation == "create"
    assert r.target_id is None
    assert r.auto is False
    pc = r.proposed_change
    assert pc["from_character_id"] == c1.id
    assert pc["from_character_name"] == "李雷"
    assert pc["to_character_id"] == c2.id
    assert pc["to_character_name"] == "韩梅"
    assert pc["type"] == "仇人"
    assert pc["strength"] == -0.8
    assert pc["description"] == "李雷决心复仇"
    assert pc["change_summary"] == "韩梅伏击李雷"
    assert pc["valid_from_chapter"] == ch.id


def test_build_pending_rows_relationship_unknown_endpoint_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "鬼魂",
             "type": "x", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_self_reference_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "李雷",
             "type": "自我", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_empty_type_skipped(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "  ", "strength": 0.0},
        ],
    )
    assert rows == []


def test_build_pending_rows_relationship_strength_clamped_high(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": 1.5},
        ],
    )
    assert rows[0].proposed_change["strength"] == 1.0


def test_build_pending_rows_relationship_strength_clamped_low(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": -2.0},
        ],
    )
    assert rows[0].proposed_change["strength"] == -1.0


def test_build_pending_rows_relationship_invalid_strength_defaults_zero(db_session):
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "x", "strength": "abc"},
        ],
    )
    assert rows[0].proposed_change["strength"] == 0.0


def test_build_pending_rows_relationship_changes_missing_kwarg_ok(db_session):
    """Not passing relationship_changes kwarg → treated as empty list."""
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {"new_characters": [], "updated_characters": [],
         "new_lore": [], "updated_lore": []},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
    )
    assert rows == []


def test_build_pending_rows_relationship_reverse_direction_independent(db_session):
    """A→B and B→A in same chapter both produce pendings."""
    p, ch, c1, c2 = _seed_two_characters(db_session)
    rows = _build_pending_rows(
        {},
        project_id=p.id, chapter_id=ch.id,
        existing_characters=[c1, c2], existing_lore=[],
        model_name="m",
        relationship_changes=[
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "暗恋", "strength": 0.7},
            {"from_character_name": "韩梅", "to_character_name": "李雷",
             "type": "朋友", "strength": 0.3},
        ],
    )
    assert len(rows) == 2
    assert all(r.target_table == "relationships" for r in rows)


def test_extract_chapter_writes_relationship_pending(db_session, monkeypatch):
    """End-to-end: extract_chapter with mock LLM produces relationship pending row."""
    from app.agents.extractor import extract_chapter

    p, ch, c1, c2 = _seed_two_characters(db_session)

    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=_llm_response({
        "summary": "摘要",
        "entities": {"new_characters": [], "updated_characters": [],
                     "new_lore": [], "updated_lore": []},
        "state_changes": [],
        "relationship_changes": [
            {"from_character_name": "李雷", "to_character_name": "韩梅",
             "type": "仇人", "strength": -0.8,
             "description": "决心复仇",
             "change_summary": "伏击"},
        ],
    }))
    fake.embed = MagicMock(return_value=[[0.0] * 1024])

    result = extract_chapter(db_session, chapter_id=ch.id, router=fake)
    assert result.pending_created == 1

    rows = list(db_session.query(PendingUpdate).filter(
        PendingUpdate.target_table == "relationships"
    ))
    assert len(rows) == 1
    assert rows[0].update_type == "soft_fact"
    assert rows[0].auto is False
    assert rows[0].proposed_change["from_character_id"] == c1.id
    assert rows[0].proposed_change["to_character_id"] == c2.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_extractor_relationships.py -v`
Expected: FAIL — `_build_pending_rows` doesn't accept `relationship_changes` kwarg.

- [ ] **Step 3: Extend _build_pending_rows signature + add relationship_changes branch**

In `app/agents/extractor.py`, extend the signature of `_build_pending_rows` to add `relationship_changes`:

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
    relationship_changes: list[dict] | None = None,
) -> list[PendingUpdate]:
```

Update the docstring tolerance rules to include relationship_changes:

```python
    """Convert LLM entities dict + state_changes + relationship_changes to PendingUpdate rows.

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
        - relationship_changes: from/to not in existing → skip; from==to → skip;
          empty type → skip; strength out of [-1.0, 1.0] → clamped; non-numeric strength → 0.0
    """
```

Add the import of `Relationship` to the schema import block in extractor.py:

```python
from app.memory.schema import (
    Chapter,
    Character,
    GenerationLog,
    LoreEntry,
    PendingUpdate,
    Project,
    Relationship,
)
```

BEFORE the `return rows` line (after the state_changes block, around line 281), insert the relationship_changes branch:

```python
    # M3c-A: relationship_changes → soft_fact pending (target_table='relationships')
    # Version-switch semantics: accept handler will soft-close old + INSERT new
    for rc in (relationship_changes or []):
        from_name = (rc.get("from_character_name") or "").strip()
        to_name = (rc.get("to_character_name") or "").strip()
        rtype = (rc.get("type") or "").strip()
        if not from_name or not to_name or not rtype:
            logger.info(
                "extractor: skipping relationship_change — empty name/type "
                "(chapter_id=%s); entry=%r", chapter_id, rc,
            )
            continue
        if from_name == to_name:
            logger.info(
                "extractor: skipping relationship_change — self reference "
                "(name=%r, chapter_id=%s)", from_name, chapter_id,
            )
            continue
        from_char = char_by_name.get(from_name)
        to_char = char_by_name.get(to_name)
        if from_char is None or to_char is None:
            logger.info(
                "extractor: skipping relationship_change — endpoint not in existing "
                "(from=%r, to=%r, chapter_id=%s); accept new_character first then re-finalize",
                from_name, to_name, chapter_id,
            )
            continue

        # Strength range clamp + non-numeric tolerance
        try:
            strength = max(-1.0, min(1.0, float(rc.get("strength") or 0.0)))
        except (TypeError, ValueError):
            logger.info(
                "extractor: relationship_change strength %r not numeric, defaulting 0.0 "
                "(chapter_id=%s)", rc.get("strength"), chapter_id,
            )
            strength = 0.0

        rows.append(PendingUpdate(
            project_id=project_id, chapter_id=chapter_id,
            update_type="soft_fact", operation="create",
            target_table="relationships", target_id=None,
            proposed_change={
                "from_character_id": from_char.id,
                "from_character_name": from_char.name,
                "to_character_id": to_char.id,
                "to_character_name": to_char.name,
                "type": rtype,
                "strength": strength,
                "description": (rc.get("description") or "").strip(),
                "change_summary": (rc.get("change_summary") or "").strip(),
                "valid_from_chapter": chapter_id,
            },
            reason=(rc.get("reason") or ""),
            auto=False,
            extractor_model=model_name,
            status="pending",
        ))

```

- [ ] **Step 4: Pass relationship_changes from extract_chapter**

In `app/agents/extractor.py`, find the `_build_pending_rows` call (around line 350-360 after M3c-B). Add the `relationship_changes` kwarg:

```python
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}) or {},
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
        state_changes=parsed.get("state_changes") or [],
        relationship_changes=parsed.get("relationship_changes") or [],
    )
```

- [ ] **Step 5: Pass existing_relationships to user.j2 render call**

In `app/agents/extractor.py`, find the `render("extractor/user.j2", ...)` call (around line 270). Fetch existing relationships (current-valid only) and pass to the template:

```python
    existing_relationships_orm = list(db.scalars(
        select(Relationship).where(
            Relationship.project_id == chapter.project_id,
            Relationship.valid_to_chapter.is_(None),
        )
    ))
    char_id_to_name = {c.id: c.name for c in existing_characters}
    existing_relationships_view = []
    for r in existing_relationships_orm:
        from_name = char_id_to_name.get(r.from_char_id, "")
        to_name = char_id_to_name.get(r.to_char_id, "")
        if from_name and to_name:
            existing_relationships_view.append({
                "from_char_id": r.from_char_id,
                "from_name": from_name,
                "to_char_id": r.to_char_id,
                "to_name": to_name,
                "type": r.type,
                "strength": r.strength,
                "description": r.description,
            })

    user_prompt = render(
        "extractor/user.j2",
        project=project,
        chapter=chapter,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        existing_relationships=existing_relationships_view,
    )
```

Also add `select` to the sqlalchemy imports at the top if not already there:

```python
from sqlalchemy import delete, select
```

- [ ] **Step 6: Run new tests**

Run: `uv run pytest tests/test_extractor_relationships.py -v`
Expected: ALL 10 tests PASS.

- [ ] **Step 7: Run regression**

Run: `uv run pytest tests/test_extractor_agent.py tests/test_extractor_prompts.py tests/test_extractor_state_changes.py tests/test_chapters_finalize.py -v 2>&1 | tail -20`
Expected: ALL PASS except the pre-existing M3b `test_extract_batch_split_for_long_chapter` failure (unrelated).

- [ ] **Step 8: Commit**

```bash
git add app/agents/extractor.py tests/test_extractor_relationships.py
git commit -m "feat(m3c-a): extractor handles relationship_changes as soft_fact pending"
```

---

## Task 5: pending_updates accept branch + _derive_summary_fields

**Files:**
- Modify: `app/api/pending_updates.py` (imports + `_derive_summary_fields` + `accept_pending`)
- Modify: `tests/test_pending_updates.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pending_updates.py`:

```python
def test_accept_relationship_inserts_and_soft_closes_old(client, fake_router):
    """Accept a relationships pending → soft-close old + INSERT new."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [],
            "relationship_changes": [
                {"from_character_name": "李雷", "to_character_name": "韩梅",
                 "type": "仇人", "strength": -0.8,
                 "description": "决心复仇", "change_summary": "被伏击"}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]

    # Pre-create an initial current-valid relationship (manual setup)
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "strength": 0.5, "valid_from_chapter": 0,
    })

    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    rel_pending = next(p for p in pendings if p["target_table"] == "relationships")
    assert rel_pending["update_type"] == "soft_fact"
    assert rel_pending["entity_name"] == "李雷 → 韩梅"
    assert "仇人" in rel_pending["proposed_value"]

    r = client.post(f"/api/pending-updates/{rel_pending['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    # After accept: 2 rows for this direction; 1 current-valid (仇人), 1 soft-closed (旧友)
    from app.memory import session as sm
    from app.memory.schema import Relationship
    with sm.SessionLocal() as s:
        rows = list(s.query(Relationship).filter(
            Relationship.from_char_id == c1,
            Relationship.to_char_id == c2,
        ).order_by(Relationship.id))
    assert len(rows) == 2
    # Old version soft-closed
    assert rows[0].type == "旧友"
    assert rows[0].valid_to_chapter == ch
    # New version current
    assert rows[1].type == "仇人"
    assert rows[1].valid_to_chapter is None
    assert rows[1].valid_from_chapter == ch
    assert rows[1].pending_update_id == rel_pending["id"]

    # Partial unique still holds: only 1 current-valid for this direction
    current = [r for r in rows if r.valid_to_chapter is None]
    assert len(current) == 1


def test_accept_relationship_partial_unique_holds(client, fake_router):
    """After accept, trying to manually POST a duplicate current-valid → 409."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [],
            "relationship_changes": [
                {"from_character_name": "李雷", "to_character_name": "韩梅",
                 "type": "仇人", "strength": -0.8}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    rel_p = next(p for p in pendings if p["target_table"] == "relationships")
    client.post(f"/api/pending-updates/{rel_p['id']}/accept")

    # Manual POST duplicate → 409
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "敌人", "strength": -0.5,
    })
    assert r.status_code == 409


def test_accept_relationship_target_gone_returns_500(client, fake_router):
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [],
            "relationship_changes": [
                {"from_character_name": "李雷", "to_character_name": "韩梅",
                 "type": "仇人", "strength": -0.8}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    rel_p = next(p for p in pendings if p["target_table"] == "relationships")

    # Delete one endpoint
    client.delete(f"/api/characters/{c2}")

    r = client.post(f"/api/pending-updates/{rel_p['id']}/accept")
    assert r.status_code == 500


def test_reject_relationship_no_db_change(client, fake_router):
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [],
            "relationship_changes": [
                {"from_character_name": "李雷", "to_character_name": "韩梅",
                 "type": "仇人", "strength": -0.8}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    rel_p = next(p for p in pendings if p["target_table"] == "relationships")

    r = client.post(f"/api/pending-updates/{rel_p['id']}/reject", json={"note": "no"})
    assert r.status_code == 200

    from app.memory import session as sm
    from app.memory.schema import Relationship
    with sm.SessionLocal() as s:
        rows = list(s.query(Relationship))
    assert rows == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pending_updates.py -v -k relationship`
Expected: FAIL — accept handler has no relationships branch yet.

- [ ] **Step 3: Update imports in pending_updates.py**

In `app/api/pending_updates.py`, update the schema import to include `Relationship`:

```python
from app.memory.schema import (
    Chapter,
    Character,
    CharacterState,
    LoreEntry,
    PendingUpdate,
    Relationship,
)
```

Also add `update` to the sqlalchemy import (currently only has `select`):

```python
from sqlalchemy import select, update
```

- [ ] **Step 4: Extend _derive_summary_fields for relationships**

In `app/api/pending_updates.py`, find the `_derive_summary_fields` function. Add a `relationships` branch BEFORE the final `else`:

```python
    elif target_table == "relationships":
        from_name = proposed_change.get("from_character_name", "")
        to_name = proposed_change.get("to_character_name", "")
        entity_type = ""
        entity_name = f"{from_name} → {to_name}" if from_name and to_name else ""
        field_name = ""
        old_value = ""
        rtype = proposed_change.get("type", "")
        strength = proposed_change.get("strength", 0.0)
        desc = proposed_change.get("description", "")
        proposed_value = (
            f"{rtype}（强度 {strength}）：{desc}" if desc
            else f"{rtype}（强度 {strength}）"
        )
```

- [ ] **Step 5: Add relationships branch to accept_pending**

In `app/api/pending_updates.py`, inside the `if p.operation == "create":` block, AFTER the `character_states` branch and BEFORE the `else`, add:

```python
            elif p.target_table == "relationships":
                # M3c-A: version-switch semantics
                data = p.proposed_change or {}
                from_id = data.get("from_character_id")
                to_id = data.get("to_character_id")
                if from_id is None or to_id is None:
                    raise HTTPException(
                        status_code=500,
                        detail="relationships pending missing from/to",
                    )
                # Validate both endpoints still exist
                if db.get(Character, from_id) is None or db.get(Character, to_id) is None:
                    raise HTTPException(
                        status_code=500, detail="target character gone")

                new_from_chapter = data.get("valid_from_chapter", p.chapter_id)

                # ① Soft-close existing current-valid (same direction)
                db.execute(
                    update(Relationship)
                    .where(
                        Relationship.from_char_id == from_id,
                        Relationship.to_char_id == to_id,
                        Relationship.valid_to_chapter.is_(None),
                    )
                    .values(valid_to_chapter=new_from_chapter,
                            updated_at=datetime.now(UTC))
                )

                # ② INSERT new version
                rel = Relationship(
                    project_id=p.project_id,
                    from_char_id=from_id, to_char_id=to_id,
                    type=data.get("type", ""),
                    strength=data.get("strength", 0.0),
                    description=data.get("description", ""),
                    valid_from_chapter=new_from_chapter,
                    valid_to_chapter=None,
                    change_summary=data.get("change_summary", ""),
                    extractor_log_id=p.extractor_log_id,
                    pending_update_id=p.id,
                )
                db.add(rel)
```

- [ ] **Step 6: Run accept tests**

Run: `uv run pytest tests/test_pending_updates.py -v`
Expected: ALL PASS (existing + 4 new).

- [ ] **Step 7: Commit**

```bash
git add app/api/pending_updates.py tests/test_pending_updates.py
git commit -m "feat(m3c-a): pending accept handler supports relationships (version switch)"
```

---

## Task 6: GET/POST/PATCH/DELETE /api/relationships endpoints

**Files:**
- Create: `app/api/relationships.py`
- Modify: `app/main.py` (register router)
- Create: `tests/test_relationships_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_relationships_api.py`:

```python
"""M3c-A: /api/relationships endpoints."""
import pytest


def _seed_project_with_two_characters(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    return pid, c1, c2


def test_list_relationships_empty(client):
    pid, _, _ = _seed_project_with_two_characters(client)
    r = client.get(f"/api/relationships?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_relationship_default_valid_from_zero(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "strength": 0.5,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["from_char_name"] == "李雷"
    assert data["to_char_name"] == "韩梅"
    assert data["valid_from_chapter"] == 0
    assert data["valid_to_chapter"] is None


def test_create_relationship_self_reference_422(client):
    pid, c1, _ = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c1,
        "type": "自我",
    })
    assert r.status_code == 422


def test_create_relationship_partial_unique_conflict_409(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人",
    })
    assert r.status_code == 409


def test_create_relationship_strength_clamped(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "x", "strength": 1.5,
    })
    assert r.status_code == 201
    assert r.json()["strength"] == 1.0


def test_create_reverse_direction_allowed(client):
    """A→B and B→A can both be current-valid (independent records)."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r1 = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "暗恋",
    })
    r2 = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c2, "to_char_id": c1,
        "type": "朋友",
    })
    assert r1.status_code == 201
    assert r2.status_code == 201


def test_list_relationships_default_current_only(client):
    """Default: only valid_to IS NULL."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    # Old version (soft-closed)
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    # New current
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships?project_id={pid}")
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "仇人"


def test_list_relationships_include_history(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships?project_id={pid}&include_history=true")
    data = r.json()
    assert len(data) == 2


def test_relationship_history_endpoint_desc(client):
    """GET /api/relationships/history?from=X&to=Y → versions in desc order."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships/history?from_char_id={c1}&to_char_id={c2}")
    data = r.json()
    assert len(data) == 2
    # Desc by valid_from_chapter
    assert data[0]["valid_from_chapter"] == ch  # newer
    assert data[0]["valid_to_chapter"] is None
    assert data[1]["valid_from_chapter"] == 0
    assert data[1]["valid_to_chapter"] == ch


def test_relationship_history_empty_when_no_data(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.get(f"/api/relationships/history?from_char_id={c1}&to_char_id={c2}")
    assert r.status_code == 200
    assert r.json() == []


def test_patch_relationship_only_allowed_fields(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "strength": 0.5,
    })
    rid = create_r.json()["id"]

    r = client.patch(f"/api/relationships/{rid}", json={
        "type": "盟友", "strength": 0.7, "description": "更紧密",
    })
    assert r.status_code == 200
    assert r.json()["type"] == "盟友"
    assert r.json()["strength"] == 0.7
    assert r.json()["description"] == "更紧密"


def test_patch_relationship_ignores_valid_fields(client):
    """PATCH body with valid_from/to should be ignored (not 422, just no-op)."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    rid = create_r.json()["id"]
    original_valid_from = create_r.json()["valid_from_chapter"]

    # Pydantic schema doesn't include valid_* fields, so they're silently dropped
    r = client.patch(f"/api/relationships/{rid}", json={
        "type": "盟友",
        "valid_from_chapter": 99,  # not in schema → ignored
    })
    assert r.status_code == 200
    assert r.json()["valid_from_chapter"] == original_valid_from


def test_soft_close_relationship(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]

    r = client.post(f"/api/relationships/{rid}/soft-close",
                    json={"valid_to_chapter": ch})
    assert r.status_code == 200
    assert r.json()["valid_to_chapter"] == ch


def test_delete_current_returns_409(client):
    """Cannot physically delete a current-valid relationship."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]

    r = client.delete(f"/api/relationships/{rid}")
    assert r.status_code == 409


def test_delete_history_ok(client):
    """Can physically delete a soft-closed (history) relationship."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]
    client.post(f"/api/relationships/{rid}/soft-close", json={"valid_to_chapter": ch})

    r = client.delete(f"/api/relationships/{rid}")
    assert r.status_code == 204


def test_get_relationship_404(client):
    r = client.get("/api/relationships/99999")
    assert r.status_code == 404


def test_list_requires_project_id(client):
    r = client.get("/api/relationships")
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_relationships_api.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Create relationships.py**

Create `app/api/relationships.py`:

```python
"""M3c-A: /api/relationships — CRUD + history + soft-close."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character, Chapter, Relationship
from app.models.relationship import (
    RelationshipCreate,
    RelationshipHistoryItem,
    RelationshipRead,
    RelationshipSoftCloseBody,
    RelationshipUpdate,
)

router = APIRouter()


def _clamp_strength(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _to_read(r: Relationship, db: Session) -> RelationshipRead:
    from_c = db.get(Character, r.from_char_id)
    to_c = db.get(Character, r.to_char_id)
    return RelationshipRead(
        id=r.id,
        project_id=r.project_id,
        from_char_id=r.from_char_id,
        from_char_name=from_c.name if from_c else "",
        to_char_id=r.to_char_id,
        to_char_name=to_c.name if to_c else "",
        type=r.type,
        strength=r.strength,
        description=r.description,
        valid_from_chapter=r.valid_from_chapter,
        valid_to_chapter=r.valid_to_chapter,
        change_summary=r.change_summary,
        extractor_log_id=r.extractor_log_id,
        pending_update_id=r.pending_update_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=list[RelationshipRead])
def list_relationships(
    project_id: int = Query(...),
    include_history: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Relationship).where(Relationship.project_id == project_id)
    if not include_history:
        stmt = stmt.where(Relationship.valid_to_chapter.is_(None))
    stmt = stmt.order_by(Relationship.from_char_id, Relationship.to_char_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    return [_to_read(r, db) for r in rows]


@router.get("/history", response_model=list[RelationshipHistoryItem])
def relationship_history(
    from_char_id: int = Query(...),
    to_char_id: int = Query(...),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(
        select(Relationship).where(
            Relationship.from_char_id == from_char_id,
            Relationship.to_char_id == to_char_id,
        ).order_by(Relationship.valid_from_chapter.desc(),
                    Relationship.created_at.desc())
    ))
    return [
        RelationshipHistoryItem(
            version_id=r.id,
            valid_from_chapter=r.valid_from_chapter,
            valid_to_chapter=r.valid_to_chapter,
            type=r.type,
            strength=r.strength,
            description=r.description,
            change_summary=r.change_summary,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", response_model=RelationshipRead,
             status_code=status.HTTP_201_CREATED)
def create_relationship(payload: RelationshipCreate, db: Session = Depends(get_db)):
    if payload.from_char_id == payload.to_char_id:
        raise HTTPException(status_code=422, detail="from and to cannot be the same character")
    if db.get(Character, payload.from_char_id) is None:
        raise HTTPException(status_code=404, detail="from_char not found")
    if db.get(Character, payload.to_char_id) is None:
        raise HTTPException(status_code=404, detail="to_char not found")

    rel = Relationship(
        project_id=payload.project_id,
        from_char_id=payload.from_char_id,
        to_char_id=payload.to_char_id,
        type=payload.type,
        strength=_clamp_strength(payload.strength),
        description=payload.description,
        valid_from_chapter=payload.valid_from_chapter,
        valid_to_chapter=None,
        change_summary=payload.change_summary,
    )
    db.add(rel)
    try:
        db.commit()
    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="a current-valid relationship already exists for this direction",
        )
    db.refresh(rel)
    return _to_read(rel, db)


@router.get("/{relationship_id}", response_model=RelationshipRead)
def get_relationship(relationship_id: int, db: Session = Depends(get_db)):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    return _to_read(r, db)


@router.patch("/{relationship_id}", response_model=RelationshipRead)
def update_relationship(
    relationship_id: int,
    payload: RelationshipUpdate,
    db: Session = Depends(get_db),
):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    data = payload.model_dump(exclude_unset=True)
    if "type" in data:
        r.type = data["type"]
    if "strength" in data:
        r.strength = _clamp_strength(data["strength"])
    if "description" in data:
        r.description = data["description"]
    db.commit()
    db.refresh(r)
    return _to_read(r, db)


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(relationship_id: int, db: Session = Depends(get_db)):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    if r.valid_to_chapter is None:
        raise HTTPException(
            status_code=409,
            detail="cannot delete current-valid relationship; use soft-close instead",
        )
    db.delete(r)
    db.commit()


@router.post("/{relationship_id}/soft-close", response_model=RelationshipRead)
def soft_close_relationship(
    relationship_id: int,
    body: RelationshipSoftCloseBody,
    db: Session = Depends(get_db),
):
    r = db.get(Relationship, relationship_id)
    if r is None:
        raise HTTPException(status_code=404, detail="relationship not found")
    if r.valid_to_chapter is not None:
        raise HTTPException(
            status_code=409,
            detail="relationship already soft-closed",
        )
    r.valid_to_chapter = body.valid_to_chapter
    r.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(r)
    return _to_read(r, db)
```

- [ ] **Step 4: Register router in main.py**

In `app/main.py`, add the import to the existing `from app.api import (...)` block:

```python
from app.api import (
    chapters,
    chapters_finalize,
    chapters_generate,
    characters,
    characters_states,
    deps,
    generation_logs,
    health,
    llm,
    lore,
    pending_updates,
    projects,
    relationships,
    world,
)
```

Then in `create_app()`, after the `pending_updates.router` registration (near the end of the include_router calls), add:

```python
    app.include_router(relationships.router, prefix="/api/relationships",
                       tags=["relationships"])
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_relationships_api.py -v`
Expected: ALL 16 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/relationships.py app/main.py tests/test_relationships_api.py
git commit -m "feat(m3c-a): /api/relationships CRUD + history + soft-close"
```

---

## Task 7: Retrieval — populate ContextBundle.relationships

**Files:**
- Modify: `app/memory/retrieval.py`
- Modify: `tests/test_context_assembly.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_context_assembly.py` (look at existing tests for the fixture pattern):

```python
def test_assemble_populates_relationships_for_involved_pair(db_session):
    """When 2+ characters are involved, their current-valid relationships appear in bundle."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5, valid_from_chapter=0,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c2.id],
    )
    assert len(bundle.relationships) == 1
    r = bundle.relationships[0]
    assert r.from_char_id == c1.id
    assert r.to_char_id == c2.id
    assert r.from_name == "李雷"
    assert r.to_name == "韩梅"
    assert r.type == "旧友"
    assert r.strength == 0.5


def test_assemble_excludes_relationships_with_uninvolved(db_session):
    """A-B relationship, but bundle only involves A and C → not included."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")  # not involved
    c3 = Character(project_id=p.id, name="王五")
    db_session.add_all([c1, c2, c3]); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5, valid_from_chapter=0,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c3.id],
    )
    assert bundle.relationships == []


def test_assemble_excludes_history_relationships(db_session):
    """Soft-closed (history) relationships are NOT injected."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    # Only a soft-closed history row
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5,
        valid_from_chapter=0, valid_to_chapter=ch.id,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c2.id],
    )
    assert bundle.relationships == []
```

If the existing `test_context_assembly.py` uses a different fixture pattern (not `db_session`), adapt accordingly. Check the file first.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_assembly.py -v -k relationships`
Expected: FAIL — bundle.relationships is always empty.

- [ ] **Step 3: Wire retrieval.py to query relationships**

In `app/memory/retrieval.py`:

1. Add `Relationship` to the schema import:
```python
from app.memory.schema import (
    Chapter,
    Character,
    LoreEntry,
    Project,
    Relationship,
    WorldOverview,
)
```

2. Replace the `relationships=[]` placeholder in `assemble_context` (around line 159) with actual query logic. Just before the `return ContextBundle(...)`:

```python
    # M3c-A: relationships between involved characters (current valid only)
    char_id_set = {c.id for c in characters}
    relationships: list[RelationshipView] = []
    if len(char_id_set) >= 2:
        rels = list(db.scalars(
            select(Relationship).where(
                Relationship.project_id == project_id,
                Relationship.from_char_id.in_(char_id_set),
                Relationship.to_char_id.in_(char_id_set),
                Relationship.valid_to_chapter.is_(None),
            )
        ))
        char_by_id = {c.id: c for c in characters}
        for r in rels:
            from_c = char_by_id.get(r.from_char_id)
            to_c = char_by_id.get(r.to_char_id)
            if from_c and to_c:
                relationships.append(RelationshipView(
                    from_char_id=r.from_char_id, to_char_id=r.to_char_id,
                    from_name=from_c.name, to_name=to_c.name,
                    type=r.type, strength=r.strength, description=r.description,
                ))
```

3. Update the `ContextBundle(...)` construction to use this `relationships` variable instead of `[]`:

```python
    return ContextBundle(
        project=project,
        world_overview=world_overview,
        characters=characters,
        character_states={
            c.id: CharacterStateSnapshot(current_state=c.current_state)
            for c in characters
        },
        relationships=relationships,  # was []
        lore_entries=list(location_lore) + list(faction_lore),
        faction_lore=faction_lore,
        location_lore=location_lore,
        plot_lines=[],  # M3 fills in
        recent_chapter_summaries=recent_chapter_summaries,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_context_assembly.py -v`
Expected: ALL PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add app/memory/retrieval.py tests/test_context_assembly.py
git commit -m "feat(m3c-a): retrieval populates ContextBundle.relationships"
```

---

## Task 8: Frontend types + API client

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/api.ts`

- [ ] **Step 1: Add types**

In `web/lib/types.ts`, append after the `// === M3c-B: Character States ===` section:

```typescript
// === M3c-A: Relationships ===

export interface Relationship {
  id: number;
  project_id: number;
  from_char_id: number;
  from_char_name: string;
  to_char_id: number;
  to_char_name: string;
  type: string;
  strength: number;
  description: string;
  valid_from_chapter: number;
  valid_to_chapter: number | null;
  change_summary: string;
  extractor_log_id: number | null;
  pending_update_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface RelationshipCreate {
  project_id: number;
  from_char_id: number;
  to_char_id: number;
  type: string;
  strength?: number;
  description?: string;
  valid_from_chapter?: number;
  change_summary?: string;
}

export interface RelationshipUpdate {
  type?: string;
  strength?: number;
  description?: string;
}

export interface RelationshipHistoryItem {
  version_id: number;
  valid_from_chapter: number;
  valid_to_chapter: number | null;
  type: string;
  strength: number;
  description: string;
  change_summary: string;
  created_at: string;
}
```

Also widen `PendingUpdateRead.target_table` union on line ~277 from `"characters" | "lore_entries" | "character_states"` to include `"relationships"`:

```typescript
  target_table: "characters" | "lore_entries" | "character_states" | "relationships";
```

- [ ] **Step 2: Add api client methods**

In `web/lib/api.ts`:

1. Update the import block to include the new types:

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
  Relationship, RelationshipCreate, RelationshipUpdate, RelationshipHistoryItem,
} from "./types";
```

2. Inside the `api` object (after `listCharacterStates`), add:

```typescript
  // M3c-A: Relationships
  listRelationships: (projectId: number, opts?: { includeHistory?: boolean; limit?: number }) =>
    http<Relationship[]>(
      `/api/relationships${qs({
        project_id: projectId,
        include_history: opts?.includeHistory ? "true" : undefined,
        limit: opts?.limit ?? 200,
      } as Record<string, unknown>)}`,
    ),
  getRelationshipHistory: (fromCharId: number, toCharId: number) =>
    http<RelationshipHistoryItem[]>(
      `/api/relationships/history${qs({ from_char_id: fromCharId, to_char_id: toCharId })}`,
    ),
  createRelationship: (data: RelationshipCreate) =>
    http<Relationship>("/api/relationships", { method: "POST", body: JSON.stringify(data) }),
  updateRelationship: (id: number, data: RelationshipUpdate) =>
    http<Relationship>(`/api/relationships/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteRelationship: (id: number) =>
    http<void>(`/api/relationships/${id}`, { method: "DELETE" }),
  softCloseRelationship: (id: number, validToChapter: number) =>
    http<Relationship>(`/api/relationships/${id}/soft-close`, {
      method: "POST",
      body: JSON.stringify({ valid_to_chapter: validToChapter }),
    }),
```

- [ ] **Step 3: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/lib/types.ts web/lib/api.ts
git commit -m "feat(m3c-a): frontend types + api client for relationships"
```

---

## Task 9: React Query hooks for relationships

**Files:**
- Modify: `web/lib/queries.ts`

- [ ] **Step 1: Add hooks**

In `web/lib/queries.ts`, append after `useCharacterStates`:

```typescript

// === M3c-A: Relationships ===

export function useRelationships(projectId: number, opts?: { includeHistory?: boolean }) {
  return useQuery({
    queryKey: ["relationships", projectId, opts?.includeHistory ?? false],
    queryFn: () => api.listRelationships(projectId, opts),
  });
}

export function useRelationshipHistory(
  fromId: number | null,
  toId: number | null,
) {
  return useQuery({
    queryKey: ["relationship-history", fromId, toId],
    queryFn: () => api.getRelationshipHistory(fromId!, toId!),
    enabled: fromId != null && toId != null,
  });
}

export function useCreateRelationship() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RelationshipCreate) => api.createRelationship(data),
    onSuccess: (data) =>
      qc.invalidateQueries({ queryKey: ["relationships", data.project_id] }),
  });
}

export function useUpdateRelationship(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RelationshipUpdate) => api.updateRelationship(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["relationships", projectId] });
      // History endpoint may also change if strength/type changed
      qc.invalidateQueries({ queryKey: ["relationship-history"] });
    },
  });
}

export function useDeleteRelationship(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteRelationship(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["relationships", projectId] }),
  });
}

export function useSoftCloseRelationship(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, validToChapter }: { id: number; validToChapter: number }) =>
      api.softCloseRelationship(id, validToChapter),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["relationships", projectId] });
      qc.invalidateQueries({ queryKey: ["relationship-history"] });
    },
  });
}
```

Update the imports at the top of `queries.ts` to include `RelationshipCreate, RelationshipUpdate`:

```typescript
import type {
  ProjectCreate, ProjectUpdate,
  WorldOverviewUpdate,
  LoreCreate, LoreUpdate,
  CharacterCreate, CharacterUpdate,
  ChapterCreate, ChapterUpdate,
  PendingStatus,
  RelationshipCreate, RelationshipUpdate,
} from "./types";
```

- [ ] **Step 2: Extend useAcceptPendingUpdate invalidation**

In `web/lib/queries.ts`, find `useAcceptPendingUpdate`. The current `onSuccess` invalidates `pending-updates`, `pending-count`, `characters`, `lore`, and conditionally `character-states`. Add a conditional for `relationships`:

```typescript
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
      qc.invalidateQueries({ queryKey: ["characters"] });
      qc.invalidateQueries({ queryKey: ["lore"] });
      // M3c-B: character_states target_id is null; invalidate all character-states
      if (data.target_table === "character_states") {
        qc.invalidateQueries({ queryKey: ["character-states"] });
      }
      // M3c-A: relationships target_id is null; invalidate all relationships caches
      if (data.target_table === "relationships") {
        qc.invalidateQueries({ queryKey: ["relationships"] });
        qc.invalidateQueries({ queryKey: ["relationship-history"] });
      }
    },
```

- [ ] **Step 3: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/lib/queries.ts
git commit -m "feat(m3c-a): relationships hooks + accept invalidation"
```

---

## Task 10: ActivityBar 🤝 icon

**Files:**
- Modify: `web/components/layout/ActivityBar.tsx`

- [ ] **Step 1: Add icon to ITEMS array**

In `web/components/layout/ActivityBar.tsx`, insert a new entry in the ITEMS array BETWEEN `characters` and `lore`:

```typescript
const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters", view: "chapters" as const },
  { icon: "👥", label: "人物", path: "characters", view: "characters" as const },
  { icon: "🤝", label: "关系", path: "relationships", view: "relationships" as const },
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
  { icon: "📜", label: "历史", path: "history", view: "history" as const },
  { icon: "📋", label: "待处理", path: "pending", view: "pending" as const },
  { icon: "🔍", label: "搜索", path: "search", view: "search" as const },
];
```

- [ ] **Step 2: Run typecheck + existing tests**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit && npx vitest run 2>&1 | tail -10`
Expected: 0 type errors; all tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/layout/ActivityBar.tsx
git commit -m "feat(m3c-a): add relationships icon to ActivityBar"
```

---

## Task 11: PendingUpdateItem — relationship card

**Files:**
- Modify: `web/components/entities/PendingUpdateItem.tsx`
- Modify: `web/tests/PendingUpdateItem.test.tsx`

- [ ] **Step 1: Write failing test**

Append to `web/tests/PendingUpdateItem.test.tsx`:

```typescript
describe("PendingUpdateItem — relationships", () => {
  const relPending: PendingUpdateRead = {
    ...basePending,
    id: 3,
    update_type: "soft_fact",
    target_table: "relationships",
    entity_name: "李雷 → 韩梅",
    field_name: "",
    proposed_value: "仇人（强度 -0.8）：决心复仇",
    reason: "",
  };

  it("renders relationship card with 🤝 icon and direction", () => {
    renderWithProviders(<PendingUpdateItem pending={relPending} />);
    expect(screen.getByText(/🤝/)).toBeTruthy();
    expect(screen.getByText(/关系变化/)).toBeTruthy();
    expect(screen.getByText(/李雷 → 韩梅/)).toBeTruthy();
    expect(screen.getByText(/仇人（强度 -0.8）/)).toBeTruthy();
  });

  it("does not render 旧值/新值 diff for relationships", () => {
    renderWithProviders(<PendingUpdateItem pending={relPending} />);
    expect(screen.queryByText(/新值：/)).toBeNull();
    expect(screen.queryByText(/旧值：/)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/PendingUpdateItem.test.tsx`
Expected: FAIL — current PendingUpdateItem treats relationships like lore (with 旧值/新值 diff).

- [ ] **Step 3: Update PendingUpdateItem.tsx**

In `web/components/entities/PendingUpdateItem.tsx`, add `isRelationship` branch alongside the existing `isStateChange`:

```typescript
  const isStateChange = pending.target_table === "character_states";
  const isRelationship = pending.target_table === "relationships";
  const isCharacter = pending.target_table === "characters";
  const isLore = pending.target_table === "lore_entries";

  let icon: string;
  let headerLabel: string;
  if (isStateChange) {
    icon = "📝";
    headerLabel = `状态变化 · ${pending.entity_name}`;
  } else if (isRelationship) {
    icon = "🤝";
    headerLabel = `关系变化 · ${pending.entity_name}`;
  } else {
    const entityLabel = isCharacter ? "人物" : "设定";
    const opLabel = pending.operation === "create" ? "新建" : "更新";
    icon = pending.operation === "create" ? "✏️" : "🔄";
    headerLabel = `${opLabel}${entityLabel} · ${pending.entity_name}${
      pending.field_name ? ` · ${pending.field_name}` : ""
    }`;
  }
```

Update the body rendering condition to treat relationships like state_changes (single line, no diff):

```typescript
      <div className="text-xs text-text-muted mb-2 pl-6">
        {isStateChange || isRelationship ? (
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
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/PendingUpdateItem.test.tsx`
Expected: ALL PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/entities/PendingUpdateItem.tsx web/tests/PendingUpdateItem.test.tsx
git commit -m "feat(m3c-a): PendingUpdateItem renders relationship cards"
```

---

## Task 12: RelationshipForm + RelationshipHistoryPanel + page

**Files:**
- Create: `web/components/entities/RelationshipForm.tsx`
- Create: `web/components/entities/RelationshipHistoryPanel.tsx`
- Create: `web/app/projects/[projectId]/relationships/page.tsx`
- Create: `web/tests/RelationshipForm.test.tsx`
- Create: `web/tests/RelationshipHistoryPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `web/tests/RelationshipHistoryPanel.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RelationshipHistoryPanel } from "@/components/entities/RelationshipHistoryPanel";
import type { RelationshipHistoryItem } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useRelationshipHistory: (fromId: number | null, toId: number | null) => ({
    data: fromId === null || toId === null ? [] : MOCK,
    isLoading: false,
  }),
}));

const MOCK: RelationshipHistoryItem[] = [
  {
    version_id: 2, valid_from_chapter: 5, valid_to_chapter: null,
    type: "仇人", strength: -0.8, description: "决心复仇",
    change_summary: "伏击", created_at: "2026-06-20T14:00:00Z",
  },
  {
    version_id: 1, valid_from_chapter: 0, valid_to_chapter: 5,
    type: "旧友", strength: 0.5, description: "童年同伴",
    change_summary: "开章前", created_at: "2026-06-19T10:00:00Z",
  },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("RelationshipHistoryPanel", () => {
  it("renders header with version count", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    expect(screen.getByText(/演变历史.*2/)).toBeTruthy();
  });

  it("is expanded by default (not collapsed)", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    // Versions should be visible without clicking
    expect(screen.getByText("仇人")).toBeTruthy();
    expect(screen.getByText("旧友")).toBeTruthy();
  });

  it("renders chapter range and version metadata", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    expect(screen.getByText(/第 5 章 → 当前/)).toBeTruthy();
    expect(screen.getByText(/第 0 章 → 第 5 章/)).toBeTruthy();
    expect(screen.getByText(/伏击/)).toBeTruthy();
  });

  it("renders empty state when no history", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={null} toId={null} />);
    expect(screen.getByText(/暂无演变历史/)).toBeTruthy();
  });
});
```

Create `web/tests/RelationshipForm.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RelationshipForm } from "@/components/entities/RelationshipForm";
import type { Character, Relationship } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useCharacters: () => ({ data: MOCK_CHARS }),
  useCreateRelationship: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdateRelationship: () => ({ mutate: vi.fn(), isPending: false }),
}));

const MOCK_CHARS: Character[] = [
  { id: 1, project_id: 1, name: "李雷", role: "protagonist",
    personality: {}, speech_style: "", background: "", motivation: "",
    appearance: "", current_state: "", affiliations: [], known_locations: [],
    created_at: "", updated_at: "" },
  { id: 2, project_id: 1, name: "韩梅", role: "supporting",
    personality: {}, speech_style: "", background: "", motivation: "",
    appearance: "", current_state: "", affiliations: [], known_locations: [],
    created_at: "", updated_at: "" },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("RelationshipForm", () => {
  it("renders empty form in create mode", () => {
    renderWithProviders(<RelationshipForm projectId={1} />);
    expect(screen.getByText(/新建关系/)).toBeTruthy();
    expect(screen.getByLabelText(/From/)).toBeTruthy();
    expect(screen.getByLabelText(/To/)).toBeTruthy();
  });

  it("disables valid_from_chapter in edit mode", () => {
    const existing: Relationship = {
      id: 5, project_id: 1,
      from_char_id: 1, from_char_name: "李雷",
      to_char_id: 2, to_char_name: "韩梅",
      type: "旧友", strength: 0.5, description: "x",
      valid_from_chapter: 0, valid_to_chapter: null,
      change_summary: "", extractor_log_id: null, pending_update_id: null,
      created_at: "", updated_at: "",
    };
    renderWithProviders(<RelationshipForm projectId={1} relationship={existing} />);
    // valid_from input should be disabled in edit mode
    const validFromInput = screen.getByLabelText(/生效章/) as HTMLInputElement;
    expect(validFromInput.disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/RelationshipHistoryPanel.test.tsx tests/RelationshipForm.test.tsx`
Expected: FAIL — components don't exist.

- [ ] **Step 3: Create RelationshipHistoryPanel.tsx**

Create `web/components/entities/RelationshipHistoryPanel.tsx`:

```typescript
"use client";

import { useRelationshipHistory } from "@/lib/queries";

export function RelationshipHistoryPanel({
  fromId,
  toId,
}: {
  fromId: number | null;
  toId: number | null;
}) {
  const { data: history = [], isLoading } = useRelationshipHistory(fromId, toId);

  if (fromId === null || toId === null) {
    return (
      <div className="border-t border-line pt-3 mt-4">
        <p className="text-xs text-text-muted">暂无演变历史</p>
      </div>
    );
  }

  return (
    <div className="border-t border-line pt-3 mt-4">
      <div className="text-sm text-text-muted-bright mb-2">
        ▼ 演变历史（{history.length} 版本）
      </div>
      {isLoading ? (
        <p className="text-xs text-text-muted">加载中...</p>
      ) : history.length === 0 ? (
        <p className="text-xs text-text-muted">暂无演变历史</p>
      ) : (
        <div className="space-y-2">
          {history.map((h) => {
            const range = h.valid_to_chapter === null
              ? `第 ${h.valid_from_chapter} 章 → 当前`
              : `第 ${h.valid_from_chapter} 章 → 第 ${h.valid_to_chapter} 章`;
            return (
              <div
                key={h.version_id}
                className="border border-line rounded p-2 bg-input/30"
              >
                <div className="text-xs text-text-dim mb-1">{range}</div>
                <div className="text-sm text-text mb-1">
                  {h.type}（强度 {h.strength}）
                </div>
                {h.description && (
                  <div className="text-xs text-text-muted mb-1">{h.description}</div>
                )}
                {h.change_summary && (
                  <div className="text-xs text-text-muted mb-1">
                    原因：{h.change_summary}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create RelationshipForm.tsx**

Create `web/components/entities/RelationshipForm.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import {
  useCharacters,
  useCreateRelationship,
  useUpdateRelationship,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { Relationship } from "@/lib/types";

export function RelationshipForm({
  projectId,
  relationship,
}: {
  projectId: number;
  relationship?: Relationship;
}) {
  const { data: characters = [] } = useCharacters(projectId);
  const create = useCreateRelationship();
  const update = useUpdateRelationship(relationship?.id ?? 0, projectId);
  const toast = useToast();

  const isEdit = relationship !== undefined;

  const [fromId, setFromId] = useState<number | "">(relationship?.from_char_id ?? "");
  const [toId, setToId] = useState<number | "">(relationship?.to_char_id ?? "");
  const [type, setType] = useState(relationship?.type ?? "");
  const [strength, setStrength] = useState(relationship?.strength ?? 0);
  const [description, setDescription] = useState(relationship?.description ?? "");
  const [validFrom, setValidFrom] = useState(relationship?.valid_from_chapter ?? 0);

  useEffect(() => {
    if (relationship) {
      setFromId(relationship.from_char_id);
      setToId(relationship.to_char_id);
      setType(relationship.type);
      setStrength(relationship.strength);
      setDescription(relationship.description);
      setValidFrom(relationship.valid_from_chapter);
    }
  }, [relationship?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (fromId === "" || toId === "") {
      toast("请选择 From 和 To 人物", "error");
      return;
    }
    if (fromId === toId) {
      toast("From 和 To 不能是同一人物", "error");
      return;
    }
    if (!type.trim()) {
      toast("请填写关系类型", "error");
      return;
    }

    try {
      if (isEdit) {
        await update.mutateAsync({ type, strength, description });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId,
          from_char_id: fromId as number,
          to_char_id: toId as number,
          type,
          strength,
          description,
          valid_from_chapter: validFrom,
        });
        toast("已新建", "success");
      }
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="p-4 space-y-3 max-w-2xl">
      <h2 className="text-lg">
        {isEdit ? `编辑关系：${relationship?.from_char_name} → ${relationship?.to_char_name}` : "新建关系"}
      </h2>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">From</label>
          <select
            aria-label="From"
            value={fromId}
            onChange={(e) => setFromId(Number(e.target.value))}
            disabled={isEdit}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">选择人物...</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">To</label>
          <select
            aria-label="To"
            value={toId}
            onChange={(e) => setToId(Number(e.target.value))}
            disabled={isEdit}
            className="w-full bg-input border border-line rounded p-2 text-text"
          >
            <option value="">选择人物...</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">类型</label>
        <input
          value={type}
          onChange={(e) => setType(e.target.value)}
          placeholder="仇人 / 旧友 / 师徒 / ..."
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">
          强度（{strength.toFixed(2)}）
        </label>
        <input
          type="range"
          min={-1}
          max={1}
          step={0.1}
          value={strength}
          onChange={(e) => setStrength(Number(e.target.value))}
          className="w-full"
        />
        <div className="flex justify-between text-[10px] text-text-dim">
          <span>-1.0 敌对</span>
          <span>0.0 中立</span>
          <span>+1.0 亲密</span>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text"
        />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">生效章</label>
        <input
          aria-label="生效章"
          type="number"
          min={0}
          value={validFrom}
          onChange={(e) => setValidFrom(Number(e.target.value))}
          disabled={isEdit}
          className="w-24 bg-input border border-line rounded p-2 text-text"
        />
        <span className="text-xs text-text-dim ml-2">0 = 开章前</span>
      </div>

      <Button variant="primary" onClick={handleSave} disabled={create.isPending || update.isPending}>
        {isEdit ? "保存修改" : "新建"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 5: Create the page**

Create `web/app/projects/[projectId]/relationships/page.tsx`:

```typescript
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useRelationships } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { RelationshipForm } from "@/components/entities/RelationshipForm";
import { RelationshipHistoryPanel } from "@/components/entities/RelationshipHistoryPanel";

export default function RelationshipsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: relationships, isLoading } = useRelationships(pid);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (relationships ?? []).find((r) => r.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="关系"
          action={
            <Button
              variant="ghost"
              onClick={() => {
                setMode("create");
                setSelectedId(null);
              }}
            >
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : !relationships || relationships.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有关系</p>
          ) : (
            relationships.map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  setMode("list");
                  setSelectedId(r.id);
                }}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === r.id
                    ? "bg-active text-white"
                    : "hover:bg-hover text-text"
                }`}
              >
                {r.from_char_name} → {r.to_char_name}{" "}
                <span className="text-text-muted">
                  · {r.type}（{r.strength}）
                </span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <RelationshipForm projectId={pid} />
          ) : selected ? (
            <div>
              <RelationshipForm projectId={pid} relationship={selected} />
              <RelationshipHistoryPanel
                fromId={selected.from_char_id}
                toId={selected.to_char_id}
              />
            </div>
          ) : (
            <div className="p-4 text-text-muted">请从左侧选择或新建关系</div>
          )}
        </div>
      }
    />
  );
}
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/RelationshipForm.test.tsx tests/RelationshipHistoryPanel.test.tsx`
Expected: ALL tests PASS.

If the form test fails on the "From" label (aria-label vs text), check that the `<label>` and `<select>` use matching `aria-label` or that the label text matches. Adjust as needed.

- [ ] **Step 7: Run full vitest + typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit && npx vitest run 2>&1 | tail -10`
Expected: 0 type errors; all tests pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/bugx/novelAI
git add web/app/projects/\[projectId\]/relationships/ web/components/entities/RelationshipForm.tsx web/components/entities/RelationshipHistoryPanel.tsx web/tests/RelationshipForm.test.tsx web/tests/RelationshipHistoryPanel.test.tsx
git commit -m "feat(m3c-a): relationships page + form + history panel"
```

---

## Task 13: E2E test

**Files:**
- Create: `web/tests/e2e/finalize-relationship.spec.ts`

- [ ] **Step 1: Write the E2E test**

Create `web/tests/e2e/finalize-relationship.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test("manual create + finalize relationship change + accept + history", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + 2 characters
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M3c-A" },
  }).then((r) => r.json());
  const pid = project.id;

  const c1 = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷" },
  }).then((r) => r.json());
  const c2 = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "韩梅" },
  }).then((r) => r.json());

  // 2. Create a chapter (for finalize mock)
  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid, order_index: 1, title: "伏击",
      content: "韩梅伏击李雷。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 3. Mock finalize (no relationship_changes from extractor in this test —
  // we'll manually POST instead to verify CRUD; finalize mock is to avoid
  // hitting the real LLM)
  await page.route(`**/api/chapters/${chId}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId, summary: "x", pending_created: 0, log_id: 999,
      }),
    });
  });

  // 4. Navigate to /relationships → create initial relationship
  await page.goto(`/projects/${pid}/relationships`);
  await page.getByRole("button", { name: /新建/ }).first().click();
  await page.getByLabel("From").selectOption({ label: "李雷" });
  await page.getByLabel("To").selectOption({ label: "韩梅" });
  await page.getByPlaceholder(/仇人/).fill("旧友");
  await page.getByRole("button", { name: /新建/ }).click();
  await expect(page.getByText("已新建")).toBeVisible({ timeout: 10_000 });

  // 5. List now shows 1 current relationship
  await page.goto(`/projects/${pid}/relationships`);
  await expect(page.getByText(/李雷 → 韩梅.*旧友/)).toBeVisible();

  // 6. Click the relationship → history panel shows 1 version
  await page.getByText(/李雷 → 韩梅/).first().click();
  await expect(page.getByText(/演变历史.*1/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/第 0 章 → 当前/)).toBeVisible();

  // 7. Seed a relationship_changes pending via direct API (bypassing extractor)
  // — simulate "finalize produced relationship_changes" by manually creating a pending
  await request.post(`${base}/api/pending-updates`, {
    data: {
      project_id: pid,
      chapter_id: chId,
      update_type: "soft_fact",
      operation: "create",
      target_table: "relationships",
      target_id: null,
      proposed_change: {
        from_character_id: c1.id,
        from_character_name: "李雷",
        to_character_id: c2.id,
        to_character_name: "韩梅",
        type: "仇人",
        strength: -0.8,
        description: "决心复仇",
        change_summary: "伏击",
        valid_from_chapter: chId,
      },
      auto: false,
    },
  });

  // Note: This requires POST /api/pending-updates to accept a body. If it doesn't,
  // remove this seed step and instead mock the finalize response to return
  // pending_created=1 + mock the pending list endpoint.

  // 8. Navigate to /pending → see relationship card → accept
  await page.goto(`/projects/${pid}/pending`);
  await expect(page.getByText(/🤝/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/关系变化.*李雷 → 韩梅/)).toBeVisible();
  await page.getByRole("button", { name: /接受/ }).first().click();
  await expect(page.getByText(/已接受/)).toBeVisible({ timeout: 10_000 });

  // 9. Back to /relationships → list shows 仇人 version
  await page.goto(`/projects/${pid}/relationships`);
  await expect(page.getByText(/李雷 → 韩梅.*仇人/)).toBeVisible();

  // 10. Click → history panel shows 2 versions
  await page.getByText(/李雷 → 韩梅/).first().click();
  await expect(page.getByText(/演变历史.*2/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/第 5 章 → 当前/)).toBeVisible();
  await expect(page.getByText(/第 0 章 → 第 5 章/)).toBeVisible();
});
```

**NOTE on Step 7:** `POST /api/pending-updates` does not exist in the current API (pending_updates are created only by the extractor). Two options to handle this:

**Option A (preferred):** Mock the pending list endpoint and accept endpoint via `page.route()` like the M3c-B E2E does. Replace step 7 with route mocks.

**Option B:** Add a test-only `POST /api/pending-updates` endpoint. Not recommended for production code.

Use Option A. Adjust step 7 to:

```typescript
  // Mock pending list + accept
  await page.route(`**/api/pending-updates*`, (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 50, project_id: pid, chapter_id: chId,
          update_type: "soft_fact", operation: "create",
          target_table: "relationships", target_id: null,
          reason: "", status: "pending",
          entity_name: "李雷 → 韩梅", entity_type: "",
          field_name: "", old_value: "",
          proposed_value: "仇人（强度 -0.8）：决心复仇",
          created_at: "2026-06-20T14:00:00Z",
          updated_at: "2026-06-20T14:00:00Z",
        },
      ]),
    });
  });

  await page.route(`**/api/pending-updates/50/accept`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 50, project_id: pid, chapter_id: chId,
        update_type: "soft_fact", operation: "create",
        target_table: "relationships", target_id: null,
        reason: "", status: "accepted",
        entity_name: "李雷 → 韩梅", entity_type: "",
        field_name: "", old_value: "",
        proposed_value: "仇人（强度 -0.8）：决心复仇",
        created_at: "2026-06-20T14:00:00Z",
        updated_at: "2026-06-20T14:01:00Z",
      }),
    });
  });

  // Mock relationships list to show 仇人 (the accepted version)
  await page.route(`**/api/relationships?*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 2, project_id: pid,
          from_char_id: c1.id, from_char_name: "李雷",
          to_char_id: c2.id, to_char_name: "韩梅",
          type: "仇人", strength: -0.8, description: "决心复仇",
          valid_from_chapter: chId, valid_to_chapter: null,
          change_summary: "伏击",
          extractor_log_id: null, pending_update_id: 50,
          created_at: "2026-06-20T14:01:00Z",
          updated_at: "2026-06-20T14:01:00Z",
        },
      ]),
    });
  });

  // Mock relationships POST (for the initial 旧友 creation in step 4)
  // — must come BEFORE step 4's POST, or unmock the POST path
```

The initial 旧友 creation (step 4) goes to the real backend (no mock). Adjust: register the GET mocks BEFORE step 4 navigation, but let POST fall through. Use `route.request().method() !== "GET"` guards.

This is getting complex — simpler approach: skip the manual 旧友 creation and only verify the accept flow + history panel (history panel shows 1 version after accept, not 2). Adjust the test accordingly:

```typescript
// Simpler E2E: just verify accept flow + history (1 version after accept)
test("finalize relationship change → accept → see in history", async ({ page, request }) => {
  // ... setup project + 2 chars + chapter ...
  // Mock pending list with a relationship_changes pending
  // Mock accept → returns accepted
  // Mock relationships list to show 仇人 version
  // Mock history endpoint to show 1 version
  // Navigate to /pending → accept → navigate to /relationships → see 仇人 → click → see 1 version history
});
```

Implement whichever variant works — the test must pass.

- [ ] **Step 2: Start backend + frontend if not running**

- Backend: `cd /Users/bugx/novelAI && uv run uvicorn app.main:app --port 8005 --reload`
- Frontend: `cd /Users/bugx/novelAI/web && npm run dev`

- [ ] **Step 3: Run the E2E test**

Run: `cd /Users/bugx/novelAI/web && npx playwright test tests/e2e/finalize-relationship.spec.ts`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/tests/e2e/finalize-relationship.spec.ts
git commit -m "test(m3c-a): e2e finalize → accept relationship → see history"
```

---

## Task 14: Full regression + memory update

**Files:** None (verification only, except memory file)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/bugx/novelAI && uv run pytest 2>&1 | tail -20`
Expected: All pass EXCEPT the pre-existing M3b `test_extract_batch_split_for_long_chapter` failure.

- [ ] **Step 2: Run full frontend test suite**

Run: `cd /Users/bugx/novelAI/web && npx vitest run 2>&1 | tail -10`
Expected: ALL pass.

- [ ] **Step 3: Run all E2E**

Run: `cd /Users/bugx/novelAI/web && npx playwright test 2>&1 | tail -20`
Expected: ALL pass (existing + new).

- [ ] **Step 4: Verify Alembic head**

Run: `cd /Users/bugx/novelAI && uv run alembic current`
Expected: new migration hash `(head)`.

- [ ] **Step 5: Update memory file**

Update `/Users/bugx/.claude/projects/-Users-bugx-novelAI/memory/novelai-m2b-status.md`:
- Add M3c-A to the 完成 section with date 2026-06-20
- Brief description: relationships 时序表 + 部分唯一索引 + version-switch accept + retrieval 接入 + /relationships 管理页 + relationship_changes 抽取
- Update "下一步" to reflect M3c-C / M3c-D / M4 as remaining options

Update `/Users/bugx/.claude/projects/-Users-bugx-novelAI/memory/MEMORY.md` index line accordingly.

- [ ] **Step 6: Final commit if any cleanup needed**

```bash
cd /Users/bugx/novelAI
git status
# Memory files live in ~/.claude/, not in repo. If working tree is clean (only
# dev.db / uv.lock untracked pre-existing), nothing to commit.
```

---

## Self-Review Notes

**Spec coverage:**
- §1.1 (6 goals): Tasks 1 (table), 3-4 (extractor), 5 (accept + version switch), 1 (partial unique index), 7 (retrieval), 6 + 12 (manual CRUD) — all covered
- §3.1 schema: Task 1 — covered
- §3.2 Alembic: Task 1 — covered
- §4.1 prompts: Task 3 — covered
- §4.2 LLM response format: Task 4 tests — covered
- §4.3 _build_pending_rows: Task 4 — covered
- §5.2 accept version-switch: Task 5 — covered
- §5.3 _derive_summary_fields: Task 5 — covered
- §5.4-5.9 API endpoints: Task 6 — covered
- §6.1 retrieval: Task 7 — covered
- §7.1 ActivityBar: Task 10 — covered
- §7.2 /relationships page: Task 12 — covered
- §7.3 PendingUpdateItem: Task 11 — covered
- §7.4-7.5 Form + HistoryPanel: Task 12 — covered
- §7.6 hooks: Task 9 — covered
- §8 tests: All tasks have tests
- §9 acceptance: Task 14

**Type consistency:**
- `Relationship` (ORM) ↔ `RelationshipRead` (Pydantic) ↔ `Relationship` (TS) — field names match across layers
- `proposed_change` shape for relationships pending: `{from_character_id, from_character_name, to_character_id, to_character_name, type, strength, description, change_summary, valid_from_chapter}` — consistent in extractor (Task 4) and accept handler (Task 5)
- API path `/api/relationships` matches main.py (Task 6) and frontend api.ts (Task 8)
- `target_table` union widened in TS types (Task 8) to include `"relationships"`
- History endpoint params `from_char_id` / `to_char_id` match across API (Task 6), frontend api.ts (Task 8), and hook (Task 9)

**Known compromises:**
- E2E test (Task 13) heavily mocks endpoints (consistent with M3a/M3b/M3c-B pattern); doesn't exercise real LLM
- Accept handler uses HTTP 500 for "target gone" (matches existing M3a/M3c-B pattern; could be 410 but consistency wins)
- `_to_read` helper in relationships.py does a per-row character lookup (N+1). For project-level list (typically <100 rows), acceptable. If perf becomes issue, batch-fetch characters.
- Manual E2E test (Task 14 step skipped) requires real LLM creds; user runs manually if desired
