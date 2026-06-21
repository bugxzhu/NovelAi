# M3c-D 情节线状态流转（plot_lines）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 plot_lines 表 + CRUD + retrieval 接入（Writer/Reviewer 注入 active 情节线）+ /plot-lines 管理页 + EventForm/ChapterEditor 接线。

**Architecture:** plot_lines 是纯手动管理的 CRUD（无 extraction、无 version-switch）。retrieval 注入仅 active 状态的情节线到 Writer + Reviewer prompt。激活 M1/M2a/M3c-C 已预留的 chapters.plot_line_ids / events.plot_line_id / ContextBundle.plot_lines 字段。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic；Next.js 15 + React + TanStack Query + TipTap + Playwright。

**Spec:** `docs/superpowers/specs/2026-06-21-m3c-d-plot-lines-design.md`

**Port conventions:** Backend `http://127.0.0.1:8005`, Frontend `http://localhost:3300`.

---

## File Structure

**Backend new:**
- `app/models/plot_line.py` — PlotLineRead/Create/Update
- `app/api/plot_lines.py` — CRUD endpoints
- `alembic/versions/<hash>_add_plot_lines.py`
- `tests/test_plot_line_schema.py`
- `tests/test_plot_lines_api.py`

**Backend modified:**
- `app/memory/schema.py` — PlotLine ORM
- `app/memory/retrieval.py` — assemble_context + assemble_review_context fill plot_lines
- `app/main.py` — register router
- `app/llm/prompts/writer/user.j2` — add plot_lines section
- `app/llm/prompts/reviewer/user.j2` — add plot_lines section
- `tests/test_context_assembly.py` — verify plot_lines injection
- `tests/test_assemble_review_context.py` — verify plot_lines injection
- `tests/test_prompts.py` — verify writer/user.j2 renders plot_lines
- `tests/test_reviewer_prompts.py` — verify reviewer/user.j2 renders plot_lines

**Frontend new:**
- `web/app/projects/[projectId]/plot-lines/page.tsx`
- `web/components/entities/PlotLineForm.tsx`
- `web/tests/PlotLineForm.test.tsx`
- `web/tests/e2e/plot-lines-flow.spec.ts`

**Frontend modified:**
- `web/components/layout/ActivityBar.tsx` — 📊 icon
- `web/components/entities/EventForm.tsx` — plot_line dropdown
- `web/components/editor/ChapterEditor.tsx` — plot_line tags (Chip multi-select)
- `web/lib/types.ts` — PlotLine types
- `web/lib/api.ts` — plot-lines endpoints
- `web/lib/queries.ts` — usePlotLines + CRUD hooks

---

## Task 1: PlotLine ORM + migration

**Files:**
- Modify: `app/memory/schema.py` (append PlotLine class)
- Create: `alembic/versions/<hash>_add_plot_lines.py`
- Create: `tests/test_plot_line_schema.py`

- [ ] **Step 1: Write failing schema test**

Create `tests/test_plot_line_schema.py`:

```python
"""M3c-D: plot_lines schema tests."""
from sqlalchemy import inspect, select

from app.memory.schema import PlotLine, Project


def test_plot_line_table_columns(db_session):
    insp = inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns("plot_lines")}
    expected = {
        "id", "project_id", "type", "title", "summary", "description",
        "status", "start_chapter", "end_chapter",
        "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_plot_line_indexes_exist(db_session):
    insp = inspect(db_session.bind)
    index_names = {i["name"] for i in insp.get_indexes("plot_lines")}
    assert "idx_plot_lines_project" in index_names


def test_plot_line_defaults(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    pl = PlotLine(project_id=p.id, title="复仇之路")
    db_session.add(pl); db_session.commit()
    assert pl.type == "sub"
    assert pl.status == "planned"
    assert pl.summary == ""
    assert pl.description == ""


def test_plot_line_cascade_delete_with_project(db_session):
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    pl = PlotLine(project_id=p.id, title="X")
    db_session.add(pl); db_session.commit()
    db_session.delete(p)
    db_session.commit()
    assert list(db_session.scalars(select(PlotLine))) == []
```

Copy `db_session` fixture from `tests/test_event_schema.py` (M3c-C sibling).

- [ ] **Step 2: Run test, verify fail**

Run: `uv run pytest tests/test_plot_line_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'PlotLine'`

- [ ] **Step 3: Add PlotLine ORM**

Append to `app/memory/schema.py`:

```python
class PlotLine(Base):
    """Main or subplot line with status lifecycle. M3c-D: manually managed
    (no extraction, no version-switch). Active plot_lines are injected into
    Writer + Reviewer context."""
    __tablename__ = "plot_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[str] = mapped_column(Text, nullable=False, default="sub")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")

    start_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        Index("idx_plot_lines_project", "project_id", "status"),
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_plot_line_schema.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Generate + apply migration**

Run: `uv run alembic revision --autogenerate -m "add plot_lines"`

If autogenerate produces empty body (known issue when init_db has already created the table), write manually:

```python
def upgrade():
    op.create_table(
        'plot_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False, server_default='sub'),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.Text(), nullable=False, server_default='planned'),
        sa.Column('start_chapter', sa.Integer(), nullable=True),
        sa.Column('end_chapter', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_plot_lines_project', 'plot_lines',
                    ['project_id', 'status'], unique=False)


def downgrade():
    op.drop_index('idx_plot_lines_project', table_name='plot_lines')
    op.drop_table('plot_lines')
```

Set `down_revision = 'e8b2d6d7d6ba'`.

Run: `uv run alembic upgrade head`

- [ ] **Step 6: Commit**

```bash
git add app/memory/schema.py alembic/versions/*_add_plot_lines.py tests/test_plot_line_schema.py
git commit -m "feat(m3c-d): add plot_lines table + migration"
```

---

## Task 2: Pydantic schemas

**Files:**
- Create: `app/models/plot_line.py`

- [ ] **Step 1: Create schemas**

Create `app/models/plot_line.py`:

```python
from typing import Literal

from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


PlotLineType = Literal["main", "sub"]
PlotLineStatus = Literal["planned", "active", "resolved", "abandoned"]


class PlotLineRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    type: PlotLineType
    title: str
    summary: str
    description: str
    status: PlotLineStatus
    start_chapter: int | None
    end_chapter: int | None


class PlotLineCreate(BaseModel):
    project_id: int
    type: PlotLineType = "sub"
    title: str
    summary: str = ""
    description: str = ""
    status: PlotLineStatus = "planned"
    start_chapter: int | None = None
    end_chapter: int | None = None


class PlotLineUpdate(BaseModel):
    type: PlotLineType | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    status: PlotLineStatus | None = None
    start_chapter: int | None = None
    end_chapter: int | None = None
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.models.plot_line import PlotLineRead, PlotLineCreate, PlotLineUpdate; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add app/models/plot_line.py
git commit -m "feat(m3c-d): pydantic schemas for plot_lines"
```

---

## Task 3: /api/plot-lines CRUD

**Files:**
- Create: `app/api/plot_lines.py`
- Modify: `app/main.py`
- Create: `tests/test_plot_lines_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_plot_lines_api.py`:

```python
"""M3c-D: /api/plot-lines CRUD tests."""


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_list_empty(client):
    pid, _ = _seed(client)
    r = client.get(f"/api/plot-lines?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_defaults(client):
    pid, _ = _seed(client)
    r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "复仇之路",
    })
    assert r.status_code == 201
    assert r.json()["type"] == "sub"
    assert r.json()["status"] == "planned"


def test_create_with_all_fields(client):
    pid, ch = _seed(client)
    r = client.post("/api/plot-lines", json={
        "project_id": pid, "type": "main", "title": "主线",
        "summary": "进展", "description": "关于",
        "status": "active", "start_chapter": ch,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "main"
    assert data["status"] == "active"
    assert data["start_chapter"] == ch


def test_list_status_filter(client):
    pid, _ = _seed(client)
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "A", "status": "active",
    })
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "B", "status": "planned",
    })
    r = client.get(f"/api/plot-lines?project_id={pid}&status=active")
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "A"


def test_list_main_before_sub(client):
    """main type sorts before sub."""
    pid, _ = _seed(client)
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "Sub", "type": "sub",
    })
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "Main", "type": "main",
    })
    r = client.get(f"/api/plot-lines?project_id={pid}")
    data = r.json()
    assert data[0]["title"] == "Main"
    assert data[1]["title"] == "Sub"


def test_patch(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.patch(f"/api/plot-lines/{rid}", json={
        "status": "resolved", "summary": "已完结",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["summary"] == "已完结"


def test_delete(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.delete(f"/api/plot-lines/{rid}")
    assert r.status_code == 204
    # Verify gone
    assert client.get(f"/api/plot-lines?project_id={pid}").json() == []


def test_list_requires_project_id(client):
    r = client.get("/api/plot-lines")
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_plot_lines_api.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Create plot_lines.py**

Create `app/api/plot_lines.py`:

```python
"""M3c-D: /api/plot-lines — CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import PlotLine
from app.models.plot_line import PlotLineCreate, PlotLineRead, PlotLineUpdate

router = APIRouter()


@router.get("", response_model=list[PlotLineRead])
def list_plot_lines(
    project_id: int = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = select(PlotLine).where(PlotLine.project_id == project_id)
    if status_filter is not None:
        stmt = stmt.where(PlotLine.status == status_filter)
    # Sort: main before sub, then by id
    stmt = stmt.order_by(
        PlotLine.type.desc(),  # "sub" > "main" alphabetically, so desc puts main first
        PlotLine.id,
    )
    return list(db.scalars(stmt))


@router.post("", response_model=PlotLineRead,
             status_code=status.HTTP_201_CREATED)
def create_plot_line(payload: PlotLineCreate, db: Session = Depends(get_db)):
    pl = PlotLine(**payload.model_dump())
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


@router.patch("/{plot_line_id}", response_model=PlotLineRead)
def update_plot_line(
    plot_line_id: int,
    payload: PlotLineUpdate,
    db: Session = Depends(get_db),
):
    pl = db.get(PlotLine, plot_line_id)
    if pl is None:
        raise HTTPException(status_code=404, detail="plot_line not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pl, field, value)
    db.commit()
    db.refresh(pl)
    return pl


@router.delete("/{plot_line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plot_line(plot_line_id: int, db: Session = Depends(get_db)):
    pl = db.get(PlotLine, plot_line_id)
    if pl is None:
        raise HTTPException(status_code=404, detail="plot_line not found")
    db.delete(pl)
    db.commit()
```

- [ ] **Step 4: Register router in main.py**

In `app/main.py`, add `plot_lines` to the `from app.api import (...)` block (alphabetical, between `pending_updates` and `projects`):

```python
from app.api import (
    chapters,
    chapters_finalize,
    chapters_generate,
    chapters_review,
    characters,
    characters_states,
    deps,
    events,
    generation_logs,
    health,
    llm,
    lore,
    pending_updates,
    plot_lines,
    projects,
    relationships,
    world,
)
```

After the relationships/events router registrations:

```python
    app.include_router(plot_lines.router, prefix="/api/plot-lines",
                       tags=["plot_lines"])
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plot_lines_api.py -v`
Expected: 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/plot_lines.py app/main.py tests/test_plot_lines_api.py
git commit -m "feat(m3c-d): /api/plot-lines CRUD"
```

---

## Task 4: Retrieval wiring (assemble_context + assemble_review_context)

**Files:**
- Modify: `app/memory/retrieval.py`
- Modify: `tests/test_context_assembly.py`
- Modify: `tests/test_assemble_review_context.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_context_assembly.py`:

```python
def test_assemble_context_includes_active_plot_lines(db_session):
    """assemble_context injects active plot_lines into ContextBundle."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, PlotLine, Project

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(PlotLine(project_id=p.id, type="main", title="主线A",
                            status="active", summary="进展"))
    db_session.add(PlotLine(project_id=p.id, type="sub", title="支线B",
                            status="planned", summary=""))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
    )
    titles = {pl.title for pl in bundle.plot_lines}
    assert "主线A" in titles
    assert "支线B" not in titles  # planned, not active


def test_assemble_context_excludes_non_active(db_session):
    """resolved/abandoned/planned plot_lines not injected."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, PlotLine, Project

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    for s in ("planned", "resolved", "abandoned"):
        db_session.add(PlotLine(project_id=p.id, title=f"PL-{s}", status=s))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
    )
    assert bundle.plot_lines == []
```

Append to `tests/test_assemble_review_context.py`:

```python
def test_assemble_review_context_includes_active_plot_lines(db_session):
    """assemble_review_context also injects active plot_lines."""
    from app.memory.retrieval import assemble_review_context
    from app.memory.schema import PlotLine

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(PlotLine(project_id=p.id, type="main", title="主线",
                            status="active", summary="在推进"))
    db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=ch.id)
    titles = {pl.title for pl in bundle.plot_lines}
    assert "主线" in titles
```

- [ ] **Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_context_assembly.py::test_assemble_context_includes_active_plot_lines tests/test_assemble_review_context.py::test_assemble_review_context_includes_active_plot_lines -v`
Expected: FAIL — plot_lines empty in bundles.

- [ ] **Step 3: Wire assemble_context**

In `app/memory/retrieval.py`, add `PlotLine` to imports. Then in `assemble_context`, find `plot_lines=[]` and replace with:

```python
    # M3c-D: inject active plot lines
    active_plot_lines = list(db.scalars(
        select(PlotLine).where(
            PlotLine.project_id == project_id,
            PlotLine.status == "active",
        )
    ))
```

And change the `ContextBundle` construction from `plot_lines=[]` to `plot_lines=active_plot_lines`.

- [ ] **Step 4: Wire assemble_review_context**

In `assemble_review_context`, add `plot_lines` field to `ReviewContextBundle`:

```python
@dataclass
class ReviewContextBundle:
    ...
    plot_lines: list[Any]  # list[PlotLine]; active only
```

Add the same query (active plot_lines) before `return ReviewContextBundle(...)` and pass `plot_lines=active_plot_lines`.

Also add `PlotLine` to the imports inside the function (alongside existing `CharacterState`, `Event`, `Relationship` imports) or at module level.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_context_assembly.py tests/test_assemble_review_context.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add app/memory/retrieval.py tests/test_context_assembly.py tests/test_assemble_review_context.py
git commit -m "feat(m3c-d): retrieval injects active plot_lines into Writer + Reviewer context"
```

---

## Task 5: Writer + Reviewer prompts

**Files:**
- Modify: `app/llm/prompts/writer/user.j2`
- Modify: `app/llm/prompts/reviewer/user.j2`
- Modify: `tests/test_prompts.py`
- Modify: `tests/test_reviewer_prompts.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_prompts.py`:

```python
def test_render_writer_user_has_plot_lines():
    """writer/user.j2 renders plot_lines section."""
    from types import SimpleNamespace
    pl = SimpleNamespace(type="main", title="复仇之路", summary="在推进")
    out = render("writer/user.j2",
                 project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                         tone="t", premise="p"),
                 world_overview=None,
                 characters=[],
                 character_states={},
                 relationships=[],
                 lore_entries=[],
                 faction_lore=[],
                 location_lore=[],
                 plot_lines=[pl],
                 recent_chapter_summaries=[],
                 retrieved_chunks=[])
    assert "当前情节线" in out
    assert "复仇之路" in out
```

Append to `tests/test_reviewer_prompts.py`:

```python
def test_render_reviewer_user_has_plot_lines():
    """reviewer/user.j2 renders plot_lines section."""
    from types import SimpleNamespace
    pl = SimpleNamespace(type="main", title="复仇之路", summary="在推进")
    out = render(
        "reviewer/user.j2",
        project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                tone="t", premise="p"),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[],
        character_states_history={},
        relationships=[],
        events=[],
        lore_entries=[],
        plot_lines=[pl],
        recent_chapter_summaries=[],
    )
    assert "当前情节线" in out
    assert "复仇之路" in out
```

- [ ] **Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_prompts.py::test_render_writer_user_has_plot_lines tests/test_reviewer_prompts.py::test_render_reviewer_user_has_plot_lines -v`
Expected: FAIL — plot_lines not rendered.

- [ ] **Step 3: Update writer/user.j2**

In `app/llm/prompts/writer/user.j2`, after the "当前关系" block and before "场景设定" (or "前情提要"), insert:

```
{% if plot_lines %}
# 当前情节线
{% for pl in plot_lines %}
- [{{ pl.type }}] {{ pl.title }}：{{ pl.summary }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Update reviewer/user.j2**

In `app/llm/prompts/reviewer/user.j2`, after the "当前人物关系" block, insert the same section:

```
{% if plot_lines %}
# 当前情节线
{% for pl in plot_lines %}
- [{{ pl.type }}] {{ pl.title }}：{{ pl.summary }}
{% endfor %}
{% endif %}
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_prompts.py tests/test_reviewer_prompts.py -v`
Expected: ALL PASS.

**IMPORTANT:** Existing prompt tests that call `render("writer/user.j2", ...)` WITHOUT `plot_lines=` will now fail because Jinja2 StrictUndefined requires the variable. Update all existing tests to pass `plot_lines=[]`. Similarly for reviewer tests — add `plot_lines=[]`.

- [ ] **Step 6: Fix existing tests that break**

Search for `render("writer/user.j2"` and `render("reviewer/user.j2"` in tests and add `plot_lines=[]` parameter where missing.

- [ ] **Step 7: Commit**

```bash
git add app/llm/prompts/writer/user.j2 app/llm/prompts/reviewer/user.j2 tests/test_prompts.py tests/test_reviewer_prompts.py
git commit -m "feat(m3c-d): writer + reviewer prompts inject active plot_lines"
```

---

## Task 6: Frontend types + API + hooks

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/queries.ts`

- [ ] **Step 1: Add types**

Append to `web/lib/types.ts`:

```typescript
// === M3c-D: Plot Lines ===

export type PlotLineType = "main" | "sub";
export type PlotLineStatus = "planned" | "active" | "resolved" | "abandoned";

export interface PlotLine {
  id: number;
  project_id: number;
  type: PlotLineType;
  title: string;
  summary: string;
  description: string;
  status: PlotLineStatus;
  start_chapter: number | null;
  end_chapter: number | null;
  created_at: string;
  updated_at: string;
}

export interface PlotLineCreate {
  project_id: number;
  type?: PlotLineType;
  title: string;
  summary?: string;
  description?: string;
  status?: PlotLineStatus;
  start_chapter?: number | null;
  end_chapter?: number | null;
}

export interface PlotLineUpdate {
  type?: PlotLineType;
  title?: string;
  summary?: string;
  description?: string;
  status?: PlotLineStatus;
  start_chapter?: number | null;
  end_chapter?: number | null;
}
```

- [ ] **Step 2: Add API methods**

In `web/lib/api.ts`, add `PlotLine, PlotLineCreate, PlotLineUpdate` to type imports. Inside `api` object:

```typescript
  // M3c-D: Plot Lines
  listPlotLines: (projectId: number, status?: PlotLineStatus) =>
    http<PlotLine[]>(`/api/plot-lines${qs({ project_id: projectId, status })}`),
  createPlotLine: (data: PlotLineCreate) =>
    http<PlotLine>("/api/plot-lines", { method: "POST", body: JSON.stringify(data) }),
  updatePlotLine: (id: number, data: PlotLineUpdate) =>
    http<PlotLine>(`/api/plot-lines/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePlotLine: (id: number) =>
    http<void>(`/api/plot-lines/${id}`, { method: "DELETE" }),
```

- [ ] **Step 3: Add hooks**

In `web/lib/queries.ts`, add imports + hooks:

```typescript
// M3c-D: Plot Lines
export function usePlotLines(projectId: number, status?: PlotLineStatus) {
  return useQuery({
    queryKey: ["plot-lines", projectId, status],
    queryFn: () => api.listPlotLines(projectId, status),
  });
}

export function useCreatePlotLine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlotLineCreate) => api.createPlotLine(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["plot-lines", data.project_id] }),
  });
}

export function useUpdatePlotLine(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlotLineUpdate) => api.updatePlotLine(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plot-lines", projectId] }),
  });
}

export function useDeletePlotLine(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deletePlotLine(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plot-lines", projectId] }),
  });
}
```

Add `PlotLineCreate, PlotLineUpdate, PlotLineStatus` to type imports in queries.ts.

- [ ] **Step 4: typecheck + commit**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit
cd /Users/bugx/novelAI
git add web/lib/types.ts web/lib/api.ts web/lib/queries.ts
git commit -m "feat(m3c-d): frontend types + api + hooks for plot_lines"
```

---

## Task 7: ActivityBar 📊 icon + PlotLineForm + /plot-lines page

**Files:**
- Modify: `web/components/layout/ActivityBar.tsx`
- Create: `web/components/entities/PlotLineForm.tsx`
- Create: `web/app/projects/[projectId]/plot-lines/page.tsx`
- Create: `web/tests/PlotLineForm.test.tsx`

- [ ] **Step 1: Add 📊 icon**

In `web/components/layout/ActivityBar.tsx`, insert between events and lore:

```typescript
  { icon: "🎯", label: "事件", path: "events", view: "events" as const },
  { icon: "📊", label: "情节线", path: "plot-lines", view: "plot-lines" as const },
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
```

- [ ] **Step 2: Write failing test for PlotLineForm**

Create `web/tests/PlotLineForm.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PlotLineForm } from "@/components/entities/PlotLineForm";
import type { PlotLine } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useChapters: () => ({ data: [{ id: 1, project_id: 1, order_index: 1, title: "C1", outline: "", content: "", status: "draft", plot_line_ids: [], summary: "", content_hash: "", last_involved_character_ids: [], last_location_id: null, created_at: "", updated_at: "" }] }),
  useCreatePlotLine: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdatePlotLine: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/components/ui/Toast", () => ({ useToast: () => vi.fn() }));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("PlotLineForm", () => {
  it("renders create mode", () => {
    renderWithProviders(<PlotLineForm projectId={1} />);
    expect(screen.getByText(/新建情节线/)).toBeTruthy();
  });

  it("renders edit mode with existing data", () => {
    const existing: PlotLine = {
      id: 5, project_id: 1, type: "main", title: "复仇",
      summary: "在推进", description: "关于", status: "active",
      start_chapter: 1, end_chapter: null,
      created_at: "", updated_at: "",
    };
    renderWithProviders(<PlotLineForm projectId={1} plotLine={existing} />);
    expect(screen.getByDisplayValue("复仇")).toBeTruthy();
  });
});
```

- [ ] **Step 3: Create PlotLineForm.tsx**

Create `web/components/entities/PlotLineForm.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import {
  useChapters,
  useCreatePlotLine,
  useUpdatePlotLine,
} from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { PlotLine, PlotLineStatus, PlotLineType } from "@/lib/types";

const TYPES: PlotLineType[] = ["main", "sub"];
const STATUSES: PlotLineStatus[] = ["planned", "active", "resolved", "abandoned"];

const TYPE_LABELS: Record<PlotLineType, string> = { main: "主线", sub: "支线" };
const STATUS_LABELS: Record<PlotLineStatus, string> = {
  planned: "计划中", active: "进行中", resolved: "已完结", abandoned: "已废弃",
};

export function PlotLineForm({
  projectId,
  plotLine,
}: {
  projectId: number;
  plotLine?: PlotLine;
}) {
  const { data: chapters = [] } = useChapters(projectId);
  const create = useCreatePlotLine();
  const update = useUpdatePlotLine(plotLine?.id ?? 0, projectId);
  const toast = useToast();

  const isEdit = plotLine !== undefined;

  const [type, setType] = useState<PlotLineType>(plotLine?.type ?? "sub");
  const [title, setTitle] = useState(plotLine?.title ?? "");
  const [summary, setSummary] = useState(plotLine?.summary ?? "");
  const [description, setDescription] = useState(plotLine?.description ?? "");
  const [statusVal, setStatusVal] = useState<PlotLineStatus>(plotLine?.status ?? "planned");
  const [startCh, setStartCh] = useState<number | "">(plotLine?.start_chapter ?? "");
  const [endCh, setEndCh] = useState<number | "">(plotLine?.end_chapter ?? "");

  useEffect(() => {
    if (plotLine) {
      setType(plotLine.type); setTitle(plotLine.title);
      setSummary(plotLine.summary); setDescription(plotLine.description);
      setStatusVal(plotLine.status);
      setStartCh(plotLine.start_chapter ?? "");
      setEndCh(plotLine.end_chapter ?? "");
    }
  }, [plotLine?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (!title.trim()) { toast("请填写标题", "error"); return; }
    try {
      if (isEdit) {
        await update.mutateAsync({
          type, title, summary, description,
          status: statusVal,
          start_chapter: startCh === "" ? null : startCh,
          end_chapter: endCh === "" ? null : endCh,
        });
        toast("已保存", "success");
      } else {
        await create.mutateAsync({
          project_id: projectId, type, title, summary, description,
          status: statusVal,
          start_chapter: startCh === "" ? null : startCh,
          end_chapter: endCh === "" ? null : endCh,
        });
        toast("已新建", "success");
      }
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="p-4 space-y-3 max-w-2xl">
      <h2 className="text-lg">{isEdit ? `编辑：${plotLine?.title}` : "新建情节线"}</h2>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">类型</label>
          <select value={type} onChange={(e) => setType(e.target.value as PlotLineType)}
            className="w-full bg-input border border-line rounded p-2 text-text">
            {TYPES.map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">状态</label>
          <select value={statusVal} onChange={(e) => setStatusVal(e.target.value as PlotLineStatus)}
            className="w-full bg-input border border-line rounded p-2 text-text">
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">标题</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)}
          className="w-full bg-input border border-line rounded p-2 text-text" />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">概述（当前进展）</label>
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text" />
      </div>

      <div>
        <label className="text-xs text-text-muted-bright block mb-1">描述（静态）</label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
          className="w-full bg-input border border-line rounded p-2 text-text" />
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">起始章</label>
          <select value={startCh}
            onChange={(e) => setStartCh(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text">
            <option value="">（未指定）</option>
            {chapters.map((c) => <option key={c.id} value={c.id}>第 {c.order_index} 章 · {c.title}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-text-muted-bright block mb-1">结束章</label>
          <select value={endCh}
            onChange={(e) => setEndCh(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full bg-input border border-line rounded p-2 text-text">
            <option value="">（未结束）</option>
            {chapters.map((c) => <option key={c.id} value={c.id}>第 {c.order_index} 章 · {c.title}</option>)}
          </select>
        </div>
      </div>

      <Button variant="primary" onClick={handleSave}
        disabled={create.isPending || update.isPending}>
        {isEdit ? "保存修改" : "新建"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Create /plot-lines page**

Create `web/app/projects/[projectId]/plot-lines/page.tsx`:

```typescript
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { usePlotLines } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { PlotLineForm } from "@/components/entities/PlotLineForm";

const STATUS_COLORS: Record<string, string> = {
  planned: "text-text-dim",
  active: "text-green-500",
  resolved: "text-blue-500",
  abandoned: "text-red-500",
};

export default function PlotLinesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: plotLines = [], isLoading } = usePlotLines(pid);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (plotLines ?? []).find((pl) => pl.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="情节线"
          action={
            <Button variant="ghost" onClick={() => { setMode("create"); setSelectedId(null); }}>
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : !plotLines || plotLines.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有情节线</p>
          ) : (
            plotLines.map((pl) => (
              <button
                key={pl.id}
                onClick={() => { setMode("list"); setSelectedId(pl.id); }}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === pl.id ? "bg-active text-white" : "hover:bg-hover text-text"
                }`}
              >
                📊 {pl.type === "main" ? "主线" : "支线"} · {pl.title}{" "}
                <span className={STATUS_COLORS[pl.status]}>
                  ({pl.status})
                </span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <PlotLineForm projectId={pid} />
          ) : selected ? (
            <PlotLineForm projectId={pid} plotLine={selected} />
          ) : (
            <div className="p-4 text-text-muted">请从左侧选择或新建情节线</div>
          )}
        </div>
      }
    />
  );
}
```

- [ ] **Step 5: Run tests + typecheck**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit && npx vitest run tests/PlotLineForm.test.tsx
cd /Users/bugx/novelAI
git add web/components/layout/ActivityBar.tsx web/components/entities/PlotLineForm.tsx web/app/projects/\[projectId\]/plot-lines/ web/tests/PlotLineForm.test.tsx
git commit -m "feat(m3c-d): /plot-lines page + PlotLineForm + ActivityBar icon"
```

---

## Task 8: EventForm plot_line dropdown + ChapterEditor plot_line tags

**Files:**
- Modify: `web/components/entities/EventForm.tsx` (add plot_line dropdown)
- Modify: `web/components/editor/ChapterEditor.tsx` (add plot_line tags)

- [ ] **Step 1: Add plot_line dropdown to EventForm**

In `web/components/entities/EventForm.tsx`:
1. Import `usePlotLines` from queries
2. Add state: `const [plotLineId, setPlotLineId] = useState<number | "">(event?.plot_line_id ?? "")`
3. Fetch: `const { data: plotLines = [] } = usePlotLines(projectId)`
4. Add JSX after the "地点" dropdown:

```tsx
<div>
  <label className="text-xs text-text-muted-bright block mb-1">情节线</label>
  <select
    aria-label="情节线"
    value={plotLineId}
    onChange={(e) => setPlotLineId(e.target.value === "" ? "" : Number(e.target.value))}
    className="w-full bg-input border border-line rounded p-2 text-text"
  >
    <option value="">（未归属）</option>
    {plotLines.map((pl) => (
      <option key={pl.id} value={pl.id}>
        {pl.type === "main" ? "主线" : "支线"} · {pl.title}
      </option>
    ))}
  </select>
</div>
```

5. In `handleSave`, add `plot_line_id: plotLineId === "" ? null : plotLineId` to the create/update payload.
6. In the `useEffect` that resets state on event change, add `setPlotLineId(event.plot_line_id ?? "")`.

**Note:** The PATCH endpoint for events (`PATCH /api/events/{id}`) and EventUpdate model need to accept `plot_line_id`. Check if `EventUpdate` in `app/models/event.py` already has `plot_line_id`. If not, add it:

In `app/models/event.py`, add to `EventUpdate`:
```python
    plot_line_id: int | None = None
```

And in `app/api/events.py` `update_event` function, add handling:
```python
    if "plot_line_id" in data:
        e.plot_line_id = data["plot_line_id"]
```

Also update `EventCreate` to include `plot_line_id` if not present, and `create_event` to write it.

- [ ] **Step 2: Add plot_line tags to ChapterEditor**

In `web/components/editor/ChapterEditor.tsx` (or wherever chapter settings are):
1. Import `usePlotLines`
2. Add Chip multi-select for plot_lines (writing to `chapter.plot_line_ids`)
3. Use `useUpdateChapter` to PATCH `plot_line_ids` when user toggles a Chip

The simplest approach: add a small section below the EditorToolbar or in the SidePanel showing:
```tsx
<div>
  <label>情节线</label>
  <div className="flex flex-wrap gap-1">
    {plotLines.map((pl) => (
      <Chip
        key={pl.id}
        selected={(form.plot_line_ids ?? chapter.plot_line_ids ?? []).includes(pl.id)}
        onClick={() => togglePlotLine(pl.id)}
      >
        {pl.title}
      </Chip>
    ))}
  </div>
</div>
```

Since `ChapterUpdate` already supports `plot_line_ids?: number[]`, the PATCH endpoint already handles this.

- [ ] **Step 3: typecheck + tests**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit && npx vitest run 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/entities/EventForm.tsx web/components/editor/ChapterEditor.tsx app/models/event.py app/api/events.py
git commit -m "feat(m3c-d): EventForm plot_line dropdown + ChapterEditor plot_line tags"
```

---

## Task 9: Full regression + memory update

- [ ] **Step 1: Full backend tests**

Run: `uv run pytest 2>&1 | tail -5`

- [ ] **Step 2: Full frontend tests**

Run: `cd web && npx vitest run 2>&1 | tail -5`

- [ ] **Step 3: E2E**

Run: `cd web && npx playwright test 2>&1 | tail -10`

- [ ] **Step 4: Alembic head**

Run: `uv run alembic current`

- [ ] **Step 5: Update memory**

Update `novelai-m2b-status.md`: M3c-D done; M3c fully complete (A/B/C/D). Next: M4b Discuss or manual smoke test.

Update `MEMORY.md` index line.

- [ ] **Step 6: Commit if needed**

```bash
git status
```

---

## Self-Review Notes

**Spec coverage:** All spec sections covered — schema (T1), API (T3), retrieval (T4), prompts (T5), frontend types (T6), page+form (T7), event/chapter wiring (T8), regression (T9).

**Type consistency:** PlotLine fields consistent across ORM/Pydantic/TS. `plot_line_id` on events matches the existing nullable INT from M3c-C. `plot_line_ids` on chapters matches the existing JSON array from M1.

**Known compromises:** 
- EventForm plot_line dropdown requires EventUpdate/EventCreate to accept plot_line_id (may need small backend change in T8)
- ChapterEditor plot_line tags placement is flexible (toolbar vs sidebar)
- No E2E for plot-lines page in this plan (can add in T9 if time permits)
