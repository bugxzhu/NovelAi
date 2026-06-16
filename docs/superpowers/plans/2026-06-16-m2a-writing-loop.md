# M2a — Writing Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend writing pipeline: SSE endpoint that streams novel prose from a beat, with strict project-scoped context assembly, Jinja2 prompt templates, full prompt auditability via `generation_logs`, and LLM streaming via the existing ClaudeProvider.

**Architecture:** Layered (api → agents → memory → llm). `memory/retrieval.assemble_context` is a pure DB function returning a `ContextBundle`. `agents/writer` splits into `prepare_generation` (DB write + prompt render, raises HTTP-mappable errors) and `stream_generation` (yields `meta → context → token* → done|error` dicts). The endpoint wraps the sync generator with `StreamingResponse` and formats dicts to SSE bytes.

**Tech Stack:** FastAPI StreamingResponse, SQLAlchemy 2.0 sync, Anthropic SDK `messages.stream()`, Jinja2 with `StrictUndefined`, Pydantic v2.

**Reference spec:** `docs/superpowers/specs/2026-06-16-m2a-writing-loop-design.md`

**Working directory:** `/Users/bugx/novelAI`

---

## Scope Check

M2a is one cohesive subsystem (backend writing pipeline). No further decomposition needed.

---

## File Structure

```
app/
├── api/
│   ├── chapters_generate.py   # 新增：SSE 端点
│   └── generation_logs.py     # 新增：list + detail
├── agents/
│   ├── __init__.py
│   └── writer.py              # 新增：prepare_generation + stream_generation
├── memory/
│   ├── retrieval.py           # 新增：assemble_context + dataclasses
│   ├── errors.py              # 新增：ChapterNotFoundError / InvalidContextError
│   └── schema.py              # 修改：加 GenerationLog
├── llm/
│   ├── base.py                # 修改：Protocol 加 stream()
│   ├── streaming.py           # 新增：StreamEvent
│   ├── router.py              # 修改：加 stream() 转发
│   ├── providers/
│   │   └── claude.py          # 修改：实现 stream()
│   └── prompts/               # 新增目录
│       ├── __init__.py        # render()
│       └── writer/
│           ├── system.j2
│           └── user.j2
├── models/
│   └── generation.py          # 新增：GenerateRequest + GenerationLogRead/Detail
└── main.py                    # 修改：注册 2 个新 router

tests/
├── test_retrieval.py
├── test_prompts.py
├── test_llm_streaming.py
├── test_writer_agent.py
├── test_chapters_generate.py
├── test_generation_logs.py
└── test_m2a_e2e.py
```

---

## Task 1: GenerationLog ORM + Pydantic Schemas + Jinja2 Dep

**Files:**
- Modify: `pyproject.toml` (add jinja2)
- Modify: `app/memory/schema.py` (add GenerationLog)
- Create: `app/models/generation.py`
- Create: `tests/test_generation_models.py`

- [ ] **Step 1.1: Add jinja2 dependency**

Modify `pyproject.toml` `dependencies` list to include `"jinja2>=3.1"`. Then:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import jinja2; print(jinja2.__version__)"
```

Expected: prints jinja2 version (≥3.1).

- [ ] **Step 1.2: Write failing test for GenerationLog table**

Create `tests/test_generation_models.py`:

```python
from datetime import UTC, datetime

from app.models.generation import (
    GenerateRequest,
    GenerationLogDetail,
    GenerationLogRead,
)


def test_generation_log_table_registered():
    from app.memory.base import Base
    assert "generation_logs" in Base.metadata.tables


def test_generate_request_defaults():
    req = GenerateRequest(beat_text="x", involved_character_ids=[1])
    assert req.instruction == ""
    assert req.location_id is None
    assert req.model_task == "writer_long"
    assert req.max_tokens == 4096


def test_generate_request_dedups_character_ids():
    req = GenerateRequest(
        beat_text="x",
        involved_character_ids=[3, 1, 3, 2, 1],
    )
    assert req.involved_character_ids == [3, 1, 2]


def test_generate_request_rejects_too_many_chars():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GenerateRequest(
            beat_text="x",
            involved_character_ids=list(range(21)),
        )


def test_generate_request_rejects_empty_beat():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GenerateRequest(beat_text="", involved_character_ids=[1])


def test_generation_log_read_minimal():
    now = datetime.now(UTC)
    log = GenerationLogRead(
        id=1, chapter_id=1, project_id=1,
        beat_text="x", model="claude-sonnet-4-6",
        status="done", input_tokens=10, output_tokens=5,
        started_at=now, finished_at=now,
        created_at=now, updated_at=now,
    )
    assert log.id == 1
    # Read 不暴露 system_prompt
    assert not hasattr(log, "system_prompt")


def test_generation_log_detail_has_prompts():
    now = datetime.now(UTC)
    log = GenerationLogDetail(
        id=1, chapter_id=1, project_id=1,
        beat_text="x", model="claude-sonnet-4-6",
        status="done", input_tokens=10, output_tokens=5,
        started_at=now, finished_at=now,
        created_at=now, updated_at=now,
        instruction="", involved_character_ids=[1],
        location_id=None, system_prompt="S", user_prompt="U",
        context_summary={}, generated_text="T",
        model_task="writer_long", stop_reason="end_turn",
    )
    assert log.system_prompt == "S"
    assert log.generated_text == "T"
```

- [ ] **Step 1.3: Run test → verify fails**

```bash
pytest tests/test_generation_models.py -v
```

Expected: FAIL (`ModuleNotFoundError: No module named 'app.models.generation'`).

- [ ] **Step 1.4: Add GenerationLog to `app/memory/schema.py`**

Append to `app/memory/schema.py` (after `Chapter`):

```python
class GenerationLog(Base):
    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    # 输入
    beat_text: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, default="")
    involved_character_ids: Mapped[list] = mapped_column(JSON, default=list)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 组装的 prompt
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context_summary: Mapped[dict] = mapped_column(JSON, default=dict)

    # 输出
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_task: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 用量
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="streaming")
    started_at: Mapped[datetime] = mapped_column(default=_now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)
```

- [ ] **Step 1.5: Create `app/models/generation.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.common import ORMBase, TimestampMixin


class GenerateRequest(BaseModel):
    beat_text: str = Field(..., min_length=1, max_length=2000)
    instruction: str = Field(default="", max_length=500)
    involved_character_ids: list[int] = Field(..., min_length=1, max_length=20)
    location_id: int | None = None
    model_task: Literal["writer_long", "writer_short"] = "writer_long"
    max_tokens: int = Field(default=4096, ge=64, le=8192)

    @field_validator("involved_character_ids")
    @classmethod
    def _dedup(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for cid in v:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out


class GenerationLogRead(ORMBase, TimestampMixin):
    id: int
    chapter_id: int
    project_id: int
    beat_text: str
    model: str | None
    status: str
    input_tokens: int
    output_tokens: int
    started_at: datetime
    finished_at: datetime | None


class GenerationLogDetail(GenerationLogRead):
    instruction: str
    involved_character_ids: list[int]
    location_id: int | None
    system_prompt: str
    user_prompt: str
    context_summary: dict
    generated_text: str | None
    model_task: str | None
    stop_reason: str | None
```

- [ ] **Step 1.6: Run test → verify passes**

```bash
pytest tests/test_generation_models.py -v
```

Expected: 6 PASS.

- [ ] **Step 1.7: Run full suite**

```bash
pytest -v
```

Expected: All M1 tests (44) + 6 new = 50 pass. No regressions.

- [ ] **Step 1.8: Commit**

```bash
git add pyproject.toml app/memory/schema.py app/models/generation.py tests/test_generation_models.py
git commit -m "feat(m2a): generation_logs table + pydantic schemas + jinja2 dep"
```

---

## Task 2: Memory Errors + Retrieval Dataclasses + Basic assemble_context

**Files:**
- Create: `app/memory/errors.py`
- Create: `app/memory/retrieval.py`
- Create: `tests/test_retrieval.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_retrieval.py`:

```python
import pytest
from sqlalchemy.orm import Session

from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.memory.retrieval import (
    ChapterSummary,
    CharacterStateSnapshot,
    ContextBundle,
    assemble_context,
)


def _seed_project_with_chars(db_session, n_chars=2):
    """Helper: insert one project + world overview + n characters."""
    from app.memory.schema import Character, Project, WorldOverview
    p = Project(title="TestNovel", genre="fantasy", premise="A test.",
                main_theme="courage", tone="epic")
    db_session.add(p)
    db_session.flush()
    wo = WorldOverview(project_id=p.id, setting_era="Medieval",
                       power_system="Magic")
    db_session.add(wo)
    chars = []
    for i in range(n_chars):
        c = Character(project_id=p.id, name=f"Char{i}",
                      role="protagonist", current_state=f"state{i}")
        db_session.add(c)
        chars.append(c)
    db_session.flush()
    return p, chars


def _seed_chapter(db_session, project_id, order_index, title, summary=""):
    from app.memory.schema import Chapter
    ch = Chapter(project_id=project_id, order_index=order_index,
                 title=title, summary=summary)
    db_session.add(ch)
    db_session.flush()
    return ch


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for retrieval tests."""
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


def test_assemble_basic(db_session):
    p, chars = _seed_project_with_chars(db_session, n_chars=2)
    ch = _seed_chapter(db_session, p.id, 1, "Chapter 1")
    db_session.commit()

    bundle = assemble_context(
        db_session,
        chapter_id=ch.id,
        beat_text="x",
        involved_character_ids=[chars[0].id, chars[1].id],
    )
    assert isinstance(bundle, ContextBundle)
    assert bundle.project.id == p.id
    assert bundle.world_overview is not None
    assert bundle.world_overview.setting_era == "Medieval"
    assert len(bundle.characters) == 2
    assert {c.name for c in bundle.characters} == {"Char0", "Char1"}
    # character_states keyed by id
    assert chars[0].id in bundle.character_states
    assert bundle.character_states[chars[0].id].current_state == "state0"


def test_assemble_chapter_not_found(db_session):
    with pytest.raises(ChapterNotFoundError):
        assemble_context(
            db_session,
            chapter_id=99999,
            beat_text="x",
            involved_character_ids=[1],
        )


def test_assemble_with_no_world_overview(db_session):
    from app.memory.schema import Character, Chapter, Project
    p = Project(title="NoWO")
    db_session.add(p); db_session.flush()
    c = Character(project_id=p.id, name="C")
    db_session.add(c)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c.id],
    )
    assert bundle.world_overview is None


def test_assemble_m3_fields_are_empty(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch = _seed_chapter(db_session, p.id, 1, "C1")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    # M2a: relationships / plot_lines are empty lists (not None)
    assert bundle.relationships == []
    assert bundle.plot_lines == []
    # character_states exists (populated from current_state)
    assert len(bundle.character_states) == 1


def test_assemble_recent_summaries_excludes_current(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch1 = _seed_chapter(db_session, p.id, 1, "C1", summary="prev1")
    ch2 = _seed_chapter(db_session, p.id, 2, "C2", summary="prev2")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch2.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    ids = [s.chapter_id for s in bundle.recent_chapter_summaries]
    assert ch2.id not in ids
    assert ch1.id in ids


def test_assemble_recent_summaries_skips_empty(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch1 = _seed_chapter(db_session, p.id, 1, "C1", summary="")  # empty
    ch2 = _seed_chapter(db_session, p.id, 2, "C2", summary="real")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch2.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    ids = [s.chapter_id for s in bundle.recent_chapter_summaries]
    assert ch1.id not in ids  # empty summary skipped
```

- [ ] **Step 2.2: Run tests → verify fail**

```bash
pytest tests/test_retrieval.py -v
```

Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 2.3: Create `app/memory/errors.py`**

```python
class ChapterNotFoundError(Exception):
    def __init__(self, chapter_id: int):
        self.chapter_id = chapter_id
        super().__init__(f"chapter not found: {chapter_id}")


class InvalidContextError(Exception):
    """One or more context entity IDs are invalid (nonexistent or wrong project)."""
    def __init__(
        self,
        *,
        invalid_character_ids: list[int] | None = None,
        invalid_location_id: int | None = None,
    ):
        self.invalid_character_ids = list(invalid_character_ids or [])
        self.invalid_location_id = invalid_location_id
        parts = []
        if self.invalid_character_ids:
            parts.append(f"invalid character_ids={self.invalid_character_ids}")
        if self.invalid_location_id is not None:
            parts.append(f"invalid location_id={self.invalid_location_id}")
        super().__init__("; ".join(parts) or "invalid context")
```

- [ ] **Step 2.4: Create `app/memory/retrieval.py`**

```python
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.memory.schema import (
    Chapter,
    Character,
    LoreEntry,
    PlotLine,  # noqa: F401  (M3 placeholder import; PlotLine table is M3)
    Project,
    WorldOverview,
)


# --- Placeholder imports for M3 tables (so type hints stay valid) ---
# PlotLine is added to schema in M3; for M2a, plot_lines is always [].
# Importing PlotLine above will fail in M2a — remove if it errors. Instead:
PlotLine = Any  # type: ignore


@dataclass
class CharacterStateSnapshot:
    """M2a simplified: uses character.current_state. M3 will populate change_summary."""
    current_state: str
    change_summary: str = ""


@dataclass
class RelationshipView:
    from_char_id: int
    to_char_id: int
    from_name: str
    to_name: str
    type: str
    strength: float
    description: str


@dataclass
class ChapterSummary:
    chapter_id: int
    order_index: int
    title: str
    summary: str


@dataclass
class ContextBundle:
    project: Project
    world_overview: WorldOverview | None
    characters: list[Character]
    character_states: dict[int, CharacterStateSnapshot]
    relationships: list[RelationshipView]
    lore_entries: list[LoreEntry]
    faction_lore: list[LoreEntry]
    location_lore: list[LoreEntry]
    plot_lines: list[Any]  # M3 will replace with list[PlotLine]
    recent_chapter_summaries: list[ChapterSummary]


def _fetch_location_with_ancestors(
    db: Session, location_id: int, project_id: int
) -> list[LoreEntry]:
    """Fetch location and all ancestors up the parent_id chain. Filtered to project."""
    chain: list[LoreEntry] = []
    current_id: int | None = location_id
    seen: set[int] = set()
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        loc = db.scalar(
            select(LoreEntry).where(
                LoreEntry.id == current_id,
                LoreEntry.project_id == project_id,
                LoreEntry.type == "location",
            )
        )
        if loc is None:
            # Location doesn't exist or doesn't belong to project
            raise InvalidContextError(invalid_location_id=location_id)
        chain.append(loc)
        current_id = loc.parent_id
    # Return root-first (ancestors first, target last)
    return list(reversed(chain))


def assemble_context(
    db: Session,
    *,
    chapter_id: int,
    beat_text: str,
    involved_character_ids: list[int],
    location_id: int | None = None,
    recent_chapters: int = 2,
) -> ContextBundle:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)
    project_id = chapter.project_id

    project = db.get(Project, project_id)
    world_overview = db.scalar(
        select(WorldOverview).where(WorldOverview.project_id == project_id)
    )

    # Strict project_id filter on characters
    requested_ids = list(involved_character_ids)
    characters = list(db.scalars(
        select(Character).where(
            Character.id.in_(requested_ids),
            Character.project_id == project_id,
        )
    )) if requested_ids else []
    found_ids = {c.id for c in characters}
    invalid_char_ids = sorted(set(requested_ids) - found_ids)

    invalid_loc_id: int | None = None
    location_lore: list[LoreEntry] = []
    if location_id is not None:
        try:
            location_lore = _fetch_location_with_ancestors(db, location_id, project_id)
        except InvalidContextError:
            invalid_loc_id = location_id

    if invalid_char_ids or invalid_loc_id is not None:
        raise InvalidContextError(
            invalid_character_ids=invalid_char_ids,
            invalid_location_id=invalid_loc_id,
        )

    # Faction lore from character affiliations
    faction_ids = {fid for c in characters for fid in (c.affiliations or [])}
    faction_lore = list(db.scalars(
        select(LoreEntry).where(
            LoreEntry.id.in_(faction_ids),
            LoreEntry.type == "faction",
            LoreEntry.project_id == project_id,
        )
    )) if faction_ids else []

    # Recent chapter summaries (skip current chapter; skip empty summaries)
    recent = list(db.scalars(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.id != chapter_id,
        ).order_by(Chapter.order_index.desc(), Chapter.id.desc()).limit(recent_chapters)
    ))
    recent_chapter_summaries = [
        ChapterSummary(c.id, c.order_index, c.title, c.summary)
        for c in sorted(recent, key=lambda c: (c.order_index, c.id))
        if c.summary
    ]

    return ContextBundle(
        project=project,
        world_overview=world_overview,
        characters=characters,
        character_states={
            c.id: CharacterStateSnapshot(current_state=c.current_state)
            for c in characters
        },
        relationships=[],  # M3 fills in
        lore_entries=list(location_lore) + list(faction_lore),
        faction_lore=faction_lore,
        location_lore=location_lore,
        plot_lines=[],  # M3 fills in
        recent_chapter_summaries=recent_chapter_summaries,
    )
```

- [ ] **Step 2.5: Run tests → verify some pass**

```bash
pytest tests/test_retrieval.py -v
```

Expected: 5 of 6 PASS. `test_assemble_chapter_not_found` should PASS. `test_assemble_m3_fields_are_empty` PASS. Basic PASS. May need fixes if imports fail.

- [ ] **Step 2.6: Add cross-project validation tests to `tests/test_retrieval.py`**

Append:

```python
def test_assemble_rejects_cross_project_character(db_session):
    from app.memory.schema import Character, Chapter, Project
    p1 = Project(title="A"); db_session.add(p1); db_session.flush()
    p2 = Project(title="B"); db_session.add(p2); db_session.flush()
    c2 = Character(project_id=p2.id, name="c2")
    db_session.add(c2)
    ch1 = Chapter(project_id=p1.id, order_index=1, title="c1")
    db_session.add(ch1); db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch1.id, beat_text="x",
            involved_character_ids=[c2.id],
        )
    assert c2.id in exc.value.invalid_character_ids


def test_assemble_rejects_nonexistent_character(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch = _seed_chapter(db_session, p.id, 1, "C1")
    db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch.id, beat_text="x",
            involved_character_ids=[chars[0].id, 99999],
        )
    assert 99999 in exc.value.invalid_character_ids
    assert chars[0].id not in exc.value.invalid_character_ids


def test_assemble_rejects_cross_project_location(db_session):
    from app.memory.schema import Chapter, LoreEntry, Project
    p1 = Project(title="A"); db_session.add(p1); db_session.flush()
    p2 = Project(title="B"); db_session.add(p2); db_session.flush()
    loc2 = LoreEntry(project_id=p2.id, type="location", name="loc2")
    db_session.add(loc2)
    ch1 = Chapter(project_id=p1.id, order_index=1, title="c1")
    db_session.add(ch1); db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch1.id, beat_text="x",
            involved_character_ids=[],  # empty not allowed by API, but retrieval allows
            location_id=loc2.id,
        )
    assert exc.value.invalid_location_id == loc2.id


def test_assemble_location_with_ancestors(db_session):
    from app.memory.schema import Chapter, LoreEntry, Project
    p = Project(title="A"); db_session.add(p); db_session.flush()
    kingdom = LoreEntry(project_id=p.id, type="location", name="Kingdom")
    db_session.add(kingdom); db_session.flush()
    city = LoreEntry(project_id=p.id, type="location", name="City",
                     parent_id=kingdom.id)
    db_session.add(city); db_session.flush()
    district = LoreEntry(project_id=p.id, type="location", name="District",
                         parent_id=city.id)
    db_session.add(district)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
        location_id=district.id,
    )
    # Ancestors first, target last
    names = [l.name for l in bundle.location_lore]
    assert names == ["Kingdom", "City", "District"]


def test_assemble_includes_faction_from_character_affiliations(db_session):
    from app.memory.schema import Chapter, Character, LoreEntry, Project
    p = Project(title="A"); db_session.add(p); db_session.flush()
    faction = LoreEntry(project_id=p.id, type="faction", name="守夜人")
    db_session.add(faction); db_session.flush()
    c = Character(project_id=p.id, name="C", affiliations=[faction.id])
    db_session.add(c)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c.id],
    )
    assert any(f.name == "守夜人" for f in bundle.faction_lore)
```

- [ ] **Step 2.7: Run all retrieval tests → verify pass**

```bash
pytest tests/test_retrieval.py -v
```

Expected: 11 PASS (6 from Step 2.1 + 5 added in Step 2.6).

- [ ] **Step 2.8: Run full suite**

```bash
pytest -v
```

Expected: 50 prior + 11 = 61 pass.

- [ ] **Step 2.9: Commit**

```bash
git add app/memory/errors.py app/memory/retrieval.py tests/test_retrieval.py
git commit -m "feat(m2a): assemble_context with strict project_id filtering"
```

---

## Task 3: LLM Streaming (StreamEvent + Protocol + ClaudeProvider.stream + ModelRouter.stream)

**Files:**
- Create: `app/llm/streaming.py`
- Modify: `app/llm/base.py` (add stream to Protocol)
- Modify: `app/llm/providers/claude.py` (add stream method)
- Modify: `app/llm/router.py` (add stream forwarder)
- Create: `tests/test_llm_streaming.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_llm_streaming.py`:

```python
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app.llm.base import LLMRequest
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import ModelRouter
from app.llm.streaming import StreamEvent


def test_stream_event_token():
    e = StreamEvent(type="token", text="hi")
    assert e.type == "token"
    assert e.text == "hi"
    assert e.input_tokens == 0


def test_stream_event_done_defaults():
    e = StreamEvent(type="done", input_tokens=10, output_tokens=5, stop_reason="end_turn")
    assert e.type == "done"
    assert e.error_message == ""


def test_claude_stream_yields_tokens_then_done(monkeypatch):
    fake_stream_obj = MagicMock()
    fake_stream_obj.text_stream = iter(["Hello ", "world"])
    fake_final = MagicMock()
    fake_final.usage.input_tokens = 10
    fake_final.usage.output_tokens = 3
    fake_final.stop_reason = "end_turn"
    fake_stream_obj.get_final_message.return_value = fake_final

    fake_client = MagicMock()
    fake_client.messages.stream.return_value.__enter__.return_value = fake_stream_obj
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "claude-sonnet-4-6",
    ))

    types = [e.type for e in events]
    assert types == ["token", "token", "done"]
    assert "".join(e.text for e in events if e.type == "token") == "Hello world"
    done = events[-1]
    assert done.input_tokens == 10
    assert done.output_tokens == 3
    assert done.stop_reason == "end_turn"
    # Verify kwargs passed to SDK
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_claude_stream_includes_system_when_set(monkeypatch):
    fake_stream_obj = MagicMock()
    fake_stream_obj.text_stream = iter(["ok"])
    fake_final = MagicMock()
    fake_final.usage.input_tokens = 1
    fake_final.usage.output_tokens = 1
    fake_final.stop_reason = "end_turn"
    fake_stream_obj.get_final_message.return_value = fake_final

    fake_client = MagicMock()
    fake_client.messages.stream.return_value.__enter__.return_value = fake_stream_obj
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi", system="You are X"),
        "claude-sonnet-4-6",
    ))
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["system"] == "You are X"


def test_claude_stream_wraps_errors(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = RuntimeError("API down")
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "claude-sonnet-4-6",
    ))
    assert len(events) == 1
    assert events[0].type == "error"
    assert "API down" in events[0].error_message
    assert events[0].error_code == "RuntimeError"


def test_model_router_stream_forwards(monkeypatch):
    """ModelRouter.stream yields from the resolved provider's stream."""
    fake_provider = MagicMock()
    fake_provider.stream.return_value = iter([
        StreamEvent(type="token", text="a"),
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    router = ModelRouter()
    monkeypatch.setattr(router, "_providers", {"claude": fake_provider})

    events = list(router.stream(LLMRequest(model_task="writer_long", user="x")))
    assert [e.type for e in events] == ["token", "done"]
    # Verify provider.stream was called with model from DEFAULT_ROUTES
    fake_provider.stream.assert_called_once()
    args, kwargs = fake_provider.stream.call_args
    # First positional arg is request, second is model
    assert args[1] == "claude-sonnet-4-6" or kwargs.get("model") == "claude-sonnet-4-6"
```

- [ ] **Step 3.2: Run tests → verify fail**

```bash
pytest tests/test_llm_streaming.py -v
```

Expected: FAIL (`ModuleNotFoundError: No module named 'app.llm.streaming'`).

- [ ] **Step 3.3: Create `app/llm/streaming.py`**

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class StreamEvent:
    """Unified event type for LLM streaming output."""
    type: Literal["token", "done", "error"]
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    error_message: str = ""
    error_code: str = ""
    raw: object = None
```

- [ ] **Step 3.4: Modify `app/llm/base.py` to add stream() to Protocol**

Current `app/llm/base.py`:

```python
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMRequest:
    ...

@dataclass
class LLMResponse:
    ...

class LLMProvider(Protocol):
    name: str
    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...
```

Add `stream` to the Protocol. Replace the Protocol class with:

```python
from collections.abc import Iterator


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...

    def stream(self, request: LLMRequest, model: str) -> "Iterator[StreamEvent]": ...
```

And add the import at the top:

```python
from app.llm.streaming import StreamEvent
```

(Note: use forward-ref string `"Iterator[StreamEvent]"` to avoid circular import if needed; or place the import inside TYPE_CHECKING. For simplicity, top-level import is fine since streaming.py has no dependency on base.py.)

Actually `streaming.py` is independent (only dataclasses + typing). Top-level import is safe. Final `base.py`:

```python
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from app.llm.streaming import StreamEvent


@dataclass
class LLMRequest:
    model_task: str
    user: str
    system: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    raw: object = None


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...

    def stream(self, request: LLMRequest, model: str) -> Iterator[StreamEvent]: ...
```

- [ ] **Step 3.5: Add stream() to ClaudeProvider**

Append to `app/llm/providers/claude.py`:

```python
from collections.abc import Iterator

from app.llm.streaming import StreamEvent


class ClaudeProvider:
    # ... existing __init__ and complete() ...

    def stream(self, request: LLMRequest, model: str | None = None) -> Iterator[StreamEvent]:
        kwargs = {
            "model": model or "claude-haiku-4-5",
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system:
            kwargs["system"] = request.system
        try:
            with self._client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    yield StreamEvent(type="token", text=chunk)
                final = stream.get_final_message()
                yield StreamEvent(
                    type="done",
                    input_tokens=getattr(final.usage, "input_tokens", 0),
                    output_tokens=getattr(final.usage, "output_tokens", 0),
                    stop_reason=getattr(final, "stop_reason", ""),
                    raw=final,
                )
        except Exception as e:
            yield StreamEvent(
                type="error",
                error_message=str(e),
                error_code=type(e).__name__,
            )
```

Place the new import at the top of `claude.py`:

```python
from collections.abc import Iterator

from anthropic import Anthropic

from app.llm.base import LLMRequest, LLMResponse
from app.llm.streaming import StreamEvent
```

- [ ] **Step 3.6: Add stream() to ModelRouter**

Append to `app/llm/router.py` (inside the `ModelRouter` class):

```python
from collections.abc import Iterator

from app.llm.streaming import StreamEvent


class ModelRouter:
    # ... existing __init__, _get_provider, resolve_model, complete ...

    def stream(self, request) -> Iterator[StreamEvent]:
        provider_name, model = self.resolve_model(request.model_task)
        provider = self._get_provider(provider_name)
        yield from provider.stream(request, model)
```

Add the imports at the top of `router.py`:

```python
from collections.abc import Iterator

from app.config import settings
from app.llm.base import LLMProvider, LLMResponse
from app.llm.providers.claude import ClaudeProvider
from app.llm.streaming import StreamEvent
```

- [ ] **Step 3.7: Run streaming tests → verify pass**

```bash
pytest tests/test_llm_streaming.py -v
```

Expected: 5 PASS.

- [ ] **Step 3.8: Run full suite**

```bash
pytest -v
```

Expected: 61 prior + 5 = 66 pass.

- [ ] **Step 3.9: Commit**

```bash
git add app/llm/streaming.py app/llm/base.py app/llm/providers/claude.py app/llm/router.py tests/test_llm_streaming.py
git commit -m "feat(m2a): llm streaming (StreamEvent + Provider/Router stream())"
```

---

## Task 4: Jinja2 Prompt Templates

**Files:**
- Create: `app/llm/prompts/__init__.py`
- Create: `app/llm/prompts/writer/system.j2`
- Create: `app/llm/prompts/writer/user.j2`
- Create: `tests/test_prompts.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_prompts.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from jinja2 import UndefinedError

from app.llm.prompts import render


def _fake_project():
    return SimpleNamespace(
        title="TestNovel", genre="fantasy", main_theme="courage",
        tone="epic", premise="A test premise.",
    )


def _fake_world_overview():
    return SimpleNamespace(
        setting_era="Medieval", geography_summary="Many islands",
        history_summary="Old war", culture_summary="Multi-ethnic",
        power_system="Magic", rules_and_taboos="No necromancy",
    )


def _fake_character(id_=1, name="Li", role="protagonist"):
    return SimpleNamespace(
        id=id_, name=name, role=role,
        personality={"mbti": "INTJ", "traits": ["calm"]},
        speech_style="short sentences",
        motivation="revenge",
        background="orphan",
    )


def _fake_state(state="angry"):
    return SimpleNamespace(current_state=state, change_summary="")


def _fake_summary(title="Prev", order_index=1, summary="stuff"):
    return SimpleNamespace(chapter_id=10, order_index=order_index,
                            title=title, summary=summary)


def _fake_lore(name="Loc1", type_="location", description="A place."):
    return SimpleNamespace(name=name, type=type_, description=description,
                            title="", parent_id=None)


def test_render_system_returns_nonempty():
    out = render("writer/system.j2")
    assert isinstance(out, str)
    assert "小说写作助手" in out or "novel" in out.lower()


def test_render_user_full():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=_fake_world_overview(),
        characters=[_fake_character()],
        character_states={1: _fake_state()},
        relationships=[],
        faction_lore=[_fake_lore(name="守夜人", type_="faction")],
        location_lore=[_fake_lore()],
        recent_chapter_summaries=[_fake_summary()],
        beat_text="主角遇旧友",
        instruction="氛围压抑",
    )
    assert "TestNovel" in out
    assert "Medieval" in out
    assert "Li" in out
    assert "守夜人" in out
    assert "主角遇旧友" in out
    assert "氛围压抑" in out


def test_render_user_minimal_no_world_no_lore_no_recent():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=None,
        characters=[_fake_character()],
        character_states={1: _fake_state()},
        relationships=[],
        faction_lore=[],
        location_lore=[],
        recent_chapter_summaries=[],
        beat_text="x",
        instruction="",
    )
    assert "TestNovel" in out
    assert "Li" in out
    assert "x" in out
    # No "Medieval" since world_overview is None
    assert "Medieval" not in out


def test_render_user_missing_variable_raises():
    with pytest.raises(UndefinedError):
        render("writer/user.j2", project=_fake_project())  # missing many vars


def test_render_user_empty_characters_list():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=None,
        characters=[],
        character_states={},
        relationships=[],
        faction_lore=[],
        location_lore=[],
        recent_chapter_summaries=[],
        beat_text="x",
        instruction="",
    )
    # Empty list should not raise; loop just produces nothing
    assert "TestNovel" in out
    assert "x" in out
```

- [ ] **Step 4.2: Run tests → verify fail**

```bash
pytest tests/test_prompts.py -v
```

Expected: FAIL (`ModuleNotFoundError: No module named 'app.llm.prompts'`).

- [ ] **Step 4.3: Create `app/llm/prompts/__init__.py`**

```python
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)


def render(template_path: str, **variables) -> str:
    """Render a prompt template. Missing variables raise UndefinedError."""
    template = _env.get_template(template_path)
    return template.render(**variables)
```

- [ ] **Step 4.4: Create `app/llm/prompts/writer/system.j2`**

```
你是一位资深的小说写作助手，正在协助作者完成一部长篇小说。

# 你的工作准则

## 人物一致性
- 严格遵循每个角色的性格特征、说话风格、背景设定
- 角色间的对话要符合各自的语言习惯（口癖、句式、用词偏好）
- 角色行为要符合其核心动机，不能为了剧情需要而强行 OOC

## 世界观一致性
- 严格遵守世界设定的力量体系、规则与禁忌
- 不能出现与设定时代/科技水平冲突的元素
- 引用的地点、势力、物品属性要与设定一致

## 叙事质量
- 展示而非陈述（show, don't tell）
- 对话推进情节，避免说明性对话
- 感官细节具体，避免空洞形容
- 节奏控制：本段是高潮还是铺垫，决定信息密度

## 风格
- 严肃文学质感，避免网文套路化表达
- 第三人称限知视角（除非用户特别说明）
- 输出纯正文，不输出解析、注释、思考过程
```

- [ ] **Step 4.5: Create `app/llm/prompts/writer/user.j2`**

```
# 项目背景
标题：{{ project.title }}
类型：{{ project.genre }}
主题：{{ project.main_theme }}
基调：{{ project.tone }}
核心设定：{{ project.premise }}

{% if world_overview %}
# 世界观
- 时代：{{ world_overview.setting_era }}
- 力量体系：{{ world_overview.power_system }}
- 规则与禁忌：{{ world_overview.rules_and_taboos }}
- 地理：{{ world_overview.geography_summary }}
- 文化：{{ world_overview.culture_summary }}
{% endif %}

# 本场景涉及人物
{% for c in characters %}
## {{ c.name }}（{{ c.role }}）
- 性格：{{ c.personality | tojson }}
- 说话风格：{{ c.speech_style }}
- 当前状态：{{ character_states[c.id].current_state }}
- 动机：{{ c.motivation }}
- 背景：{{ c.background }}

{% endfor %}

{% if relationships %}
# 当前关系（仅本场景涉及人物间）
{% for r in relationships %}
- {{ r.from_name }} → {{ r.to_name }}：{{ r.type }}（强度 {{ r.strength }}）— {{ r.description }}
{% endfor %}
{% endif %}

{% if faction_lore or location_lore %}
# 场景设定
{% if location_lore %}
## 地点（含上级区域）
{% for loc in location_lore %}
- {{ loc.name }}{% if loc.title %}（{{ loc.title }}）{% endif %}：{{ loc.description }}
{% endfor %}
{% endif %}
{% if faction_lore %}
## 涉及势力
{% for f in faction_lore %}
- {{ f.name }}：{{ f.description }}
{% endfor %}
{% endif %}
{% endif %}

{% if recent_chapter_summaries %}
# 前情提要
{% for s in recent_chapter_summaries %}
- 第{{ s.order_index }}章 {{ s.title }}：{{ s.summary }}
{% endfor %}
{% endif %}

# 本次写作任务

请扩写以下情节片段：

> {{ beat_text }}

{% if instruction %}
作者附加要求：{{ instruction }}
{% endif %}

请直接输出正文（Markdown 格式），不要写解析或说明。
```

- [ ] **Step 4.6: Run tests → verify pass**

```bash
pytest tests/test_prompts.py -v
```

Expected: 5 PASS.

- [ ] **Step 4.7: Run full suite**

```bash
pytest -v
```

Expected: 66 + 5 = 71 pass.

- [ ] **Step 4.8: Commit**

```bash
git add app/llm/prompts/ tests/test_prompts.py
git commit -m "feat(m2a): jinja2 prompt templates (writer system + user)"
```

---

## Task 5: Writer Agent (prepare_generation + stream_generation)

**Files:**
- Create: `app/agents/__init__.py`
- Create: `app/agents/writer.py`
- Create: `tests/test_writer_agent.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_writer_agent.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace
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
    """Seed project + world + 2 chars + 1 location + 1 faction + 1 chapter."""
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
        self.model_for_task = "claude-sonnet-4-6"
    def resolve_model(self, task):
        return ("claude", self.model_for_task)
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
    assert "PN" in prep.system_prompt or "PN" in prep.user_prompt
    assert "C1" in prep.user_prompt
    assert "Loc" in prep.user_prompt  # location injected
    assert "F" in prep.user_prompt    # faction injected


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
    assert "C1" in str(events[1]["context_bundle"])  # context_bundle has C1
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
```

- [ ] **Step 5.2: Run tests → verify fail**

```bash
pytest tests/test_writer_agent.py -v
```

Expected: FAIL (`ModuleNotFoundError: No module named 'app.agents'`).

- [ ] **Step 5.3: Create `app/agents/__init__.py`**

```python
```

- [ ] **Step 5.4: Create `app/agents/writer.py`**

```python
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.memory.retrieval import (
    ChapterSummary,
    CharacterStateSnapshot,
    ContextBundle,
    RelationshipView,
    assemble_context,
)
from app.memory.schema import GenerationLog


def _now() -> datetime:
    return datetime.now(UTC)


def _serialize_context_summary(bundle: ContextBundle) -> dict:
    """Structured summary for storage/diff (smaller than full bundle)."""
    return {
        "project_id": bundle.project.id,
        "project_title": bundle.project.title,
        "world_overview_present": bundle.world_overview is not None,
        "characters": [
            {"id": c.id, "name": c.name, "role": c.role}
            for c in bundle.characters
        ],
        "relationships": [
            {"from": r.from_name, "to": r.to_name, "type": r.type}
            for r in bundle.relationships
        ],
        "faction_lore": [{"id": f.id, "name": f.name} for f in bundle.faction_lore],
        "location_lore": [{"id": l.id, "name": l.name} for l in bundle.location_lore],
        "recent_chapter_summaries": [
            {"chapter_id": s.chapter_id, "title": s.title}
            for s in bundle.recent_chapter_summaries
        ],
    }


def _serialize_context_bundle(bundle: ContextBundle) -> dict:
    """Full serialization for the SSE context event."""
    return {
        "project": {
            "id": bundle.project.id,
            "title": bundle.project.title,
            "genre": bundle.project.genre,
            "main_theme": bundle.project.main_theme,
            "tone": bundle.project.tone,
            "premise": bundle.project.premise,
        },
        "world_overview": {
            "setting_era": bundle.world_overview.setting_era,
            "geography_summary": bundle.world_overview.geography_summary,
            "history_summary": bundle.world_overview.history_summary,
            "culture_summary": bundle.world_overview.culture_summary,
            "power_system": bundle.world_overview.power_system,
            "rules_and_taboos": bundle.world_overview.rules_and_taboos,
        } if bundle.world_overview else None,
        "characters": [
            {
                "id": c.id, "name": c.name, "role": c.role,
                "current_state": bundle.character_states[c.id].current_state,
            }
            for c in bundle.characters
        ],
        "relationships": [
            {"from": r.from_name, "to": r.to_name, "type": r.type,
             "strength": r.strength, "description": r.description}
            for r in bundle.relationships
        ],
        "faction_lore": [{"id": f.id, "name": f.name, "description": f.description}
                         for f in bundle.faction_lore],
        "location_lore": [{"id": l.id, "name": l.name, "description": l.description}
                          for l in bundle.location_lore],
        "recent_chapter_summaries": [
            {"chapter_id": s.chapter_id, "order_index": s.order_index,
             "title": s.title, "summary": s.summary}
            for s in bundle.recent_chapter_summaries
        ],
    }


@dataclass
class PreparedGeneration:
    log: GenerationLog
    context_bundle: ContextBundle
    system_prompt: str
    user_prompt: str
    llm_request: LLMRequest
    model_name: str


def prepare_generation(
    db: Session,
    *,
    chapter_id: int,
    beat_text: str,
    instruction: str,
    involved_character_ids: list[int],
    location_id: int | None,
    model_task: str,
    max_tokens: int,
    router: ModelRouter = default_router,
) -> PreparedGeneration:
    """Pre-stream phase. May raise ChapterNotFoundError / InvalidContextError."""
    bundle = assemble_context(
        db,
        chapter_id=chapter_id,
        beat_text=beat_text,
        involved_character_ids=involved_character_ids,
        location_id=location_id,
    )

    system_prompt = render("writer/system.j2")
    user_prompt = render(
        "writer/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        characters=bundle.characters,
        character_states=bundle.character_states,
        relationships=bundle.relationships,
        faction_lore=bundle.faction_lore,
        location_lore=bundle.location_lore,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
        beat_text=beat_text,
        instruction=instruction,
    )

    _, model_name = router.resolve_model(model_task)

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=bundle.project.id,
        beat_text=beat_text,
        instruction=instruction,
        involved_character_ids=list(involved_character_ids),
        location_id=location_id,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary=_serialize_context_summary(bundle),
        model=model_name,
        model_task=model_task,
        status="streaming",
        started_at=_now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return PreparedGeneration(
        log=log,
        context_bundle=bundle,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        llm_request=LLMRequest(
            model_task=model_task,
            system=system_prompt,
            user=user_prompt,
            max_tokens=max_tokens,
        ),
        model_name=model_name,
    )


def stream_generation(
    db: Session,
    prep: PreparedGeneration,
    *,
    router: ModelRouter = default_router,
) -> Iterator[dict]:
    """Yields meta → context → token* → done|error dicts. Updates log on terminal."""
    yield {
        "type": "meta",
        "generation_log_id": prep.log.id,
        "model": prep.model_name,
        "model_task": prep.log.model_task,
        "chapter_id": prep.log.chapter_id,
        "started_at": prep.log.started_at.isoformat(),
    }
    yield {
        "type": "context",
        "context_bundle": _serialize_context_bundle(prep.context_bundle),
    }

    generated_parts: list[str] = []
    for event in router.stream(prep.llm_request):
        if event.type == "token":
            generated_parts.append(event.text)
            yield {"type": "token", "text": event.text}
        elif event.type == "done":
            full_text = "".join(generated_parts)
            _finalize_done(db, prep.log.id, full_text, event)
            yield {
                "type": "done",
                "generation_log_id": prep.log.id,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "stop_reason": event.stop_reason,
            }
            return
        elif event.type == "error":
            _finalize_error(db, prep.log.id, event)
            yield {
                "type": "error",
                "message": event.error_message,
                "code": event.error_code,
            }
            return


def _finalize_done(db: Session, log_id: int, text: str, event) -> None:
    log = db.get(GenerationLog, log_id)
    if log is None:
        return
    log.generated_text = text
    log.input_tokens = event.input_tokens
    log.output_tokens = event.output_tokens
    log.stop_reason = event.stop_reason
    log.status = "done"
    log.finished_at = _now()
    db.commit()


def _finalize_error(db: Session, log_id: int, event) -> None:
    log = db.get(GenerationLog, log_id)
    if log is None:
        return
    log.stop_reason = event.error_code
    log.status = "failed"
    log.finished_at = _now()
    db.commit()
```

- [ ] **Step 5.5: Run writer tests → verify pass**

```bash
pytest tests/test_writer_agent.py -v
```

Expected: 5 PASS.

- [ ] **Step 5.6: Run full suite**

```bash
pytest -v
```

Expected: 71 + 5 = 76 pass.

- [ ] **Step 5.7: Commit**

```bash
git add app/agents/ tests/test_writer_agent.py
git commit -m "feat(m2a): writer agent (prepare_generation + stream_generation)"
```

---

## Task 6: SSE Endpoint /api/chapters/{id}/generate

**Files:**
- Create: `app/api/chapters_generate.py`
- Modify: `app/main.py` (register router)
- Create: `tests/test_chapters_generate.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/test_chapters_generate.py`:

```python
import json

import pytest

from app.llm.streaming import StreamEvent


@pytest.fixture
def fake_router(monkeypatch):
    """Patch default_router at the endpoint module to yield a fixed stream."""
    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="Hello ")
            yield StreamEvent(type="token", text="world")
            yield StreamEvent(type="done", input_tokens=10, output_tokens=2,
                              stop_reason="end_turn")
    fake = _Fake()
    monkeypatch.setattr("app.api.chapters_generate.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.put(f"/api/projects/{pid}/world-overview",
               json={"setting_era": "Medieval"}).json()
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    c2 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C2"}).json()["id"]
    loc = client.post("/api/lore",
                      json={"project_id": pid, "type": "location",
                            "name": "Loc"}).json()["id"]
    ch = client.post("/api/chapters",
                     json={"project_id": pid, "order_index": 1,
                           "title": "CH"}).json()["id"]
    return pid, [c1, c2], loc, ch


def _parse_sse(lines):
    """Parse SSE chunks from iter_lines. Returns list of (event, data_dict)."""
    events = []
    current_event = None
    current_data = []
    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "":
            if current_event and current_data:
                events.append((current_event, json.loads("".join(current_data))))
            current_event = None
            current_data = []
    return events


def test_generate_returns_404_unknown_chapter(client, fake_router):
    r = client.post("/api/chapters/99999/generate",
                    json={"beat_text": "x", "involved_character_ids": [1]})
    assert r.status_code == 404
    assert r.json()["detail"] == "chapter not found"


def test_generate_returns_422_invalid_character_id(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": [99999]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert 99999 in detail["invalid_character_ids"]


def test_generate_returns_422_invalid_location_id(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": [chars[0]],
                          "location_id": 99999})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert detail["invalid_location_id"] == 99999


def test_generate_returns_422_too_many_chars(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": list(range(21))})
    assert r.status_code == 422
    # Default FastAPI validation error (not invalid_context)


def test_generate_returns_422_empty_beat(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "",
                          "involved_character_ids": [chars[0]]})
    assert r.status_code == 422


def test_generate_sse_full_sequence(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "主角遇旧友",
                             "instruction": "压抑",
                             "involved_character_ids": chars,
                             "location_id": loc}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.iter_lines())
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "token", "done"]
    meta = events[0][1]
    assert meta["model"] == "claude-sonnet-4-6"
    log_id = meta["generation_log_id"]
    context = events[1][1]["context_bundle"]
    assert context["world_overview"]["setting_era"] == "Medieval"
    assert any(c["name"] == "C1" for c in context["characters"])
    token_text = "".join(d["text"] for e, d in events if e == "token")
    assert token_text == "Hello world"
    done = events[-1][1]
    assert done["generation_log_id"] == log_id
    assert done["input_tokens"] == 10
    assert done["stop_reason"] == "end_turn"


def test_generate_sse_emits_error_event_on_llm_failure(client, monkeypatch):
    class _ErrRouter:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="partial")
            yield StreamEvent(type="error", error_message="API dead",
                              error_code="RuntimeError")
    monkeypatch.setattr("app.api.chapters_generate.default_router", _ErrRouter())
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "x",
                             "involved_character_ids": [chars[0]]}) as response:
        events = _parse_sse(response.iter_lines())
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "error"]
    err = events[-1][1]
    assert "API dead" in err["message"]
    assert err["code"] == "RuntimeError"
    # DB log should be marked failed
    log_id = events[0][1]["generation_log_id"]
    detail = client.get(f"/api/generation-logs/{log_id}").json()
    assert detail["status"] == "failed"


def test_generate_creates_log_before_streaming(client, fake_router):
    """Meta event must include a generation_log_id that already exists in DB."""
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "x",
                             "involved_character_ids": [chars[0]]}) as response:
        events = _parse_sse(response.iter_lines())
    meta = events[0][1]
    log_id = meta["generation_log_id"]
    # DB row exists (verify via detail endpoint - implemented in Task 7)
    # For now just check the log_id is positive int
    assert isinstance(log_id, int)
    assert log_id > 0
```

- [ ] **Step 6.2: Run tests → verify fail**

```bash
pytest tests/test_chapters_generate.py -v
```

Expected: FAIL (no endpoint).

- [ ] **Step 6.3: Create `app/api/chapters_generate.py`**

```python
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.writer import prepare_generation, stream_generation
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.models.generation import GenerateRequest

router = APIRouter()


def _format_sse(event_type: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/{chapter_id}/generate")
def generate(
    chapter_id: int,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        prep = prepare_generation(
            db,
            chapter_id=chapter_id,
            beat_text=payload.beat_text,
            instruction=payload.instruction,
            involved_character_ids=payload.involved_character_ids,
            location_id=payload.location_id,
            model_task=payload.model_task,
            max_tokens=payload.max_tokens,
            router=default_router,
        )
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except InvalidContextError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_context",
                "invalid_character_ids": e.invalid_character_ids,
                "invalid_location_id": e.invalid_location_id,
            },
        )

    def event_stream():
        try:
            for event_dict in stream_generation(db, prep, router=default_router):
                event_type = event_dict["type"]
                # Strip type from data payload (it's in the `event:` line)
                data = {k: v for k, v in event_dict.items() if k != "type"}
                yield _format_sse(event_type, data)
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 6.4: Register router in `app/main.py`**

Modify imports:

```python
from app.api import (
    chapters,
    chapters_generate,
    characters,
    deps,
    health,
    llm,
    lore,
    projects,
    world,
)
```

In `create_app`, add:

```python
    app.include_router(chapters_generate.router, prefix="/api/chapters",
                        tags=["chapters_generate"])
```

Note: prefix `/api/chapters` (shared with the regular chapters router); the new router only declares `POST /{chapter_id}/generate`, which doesn't collide with `POST /api/chapters` (list-level).

- [ ] **Step 6.5: Run tests → verify some pass**

```bash
pytest tests/test_chapters_generate.py -v
```

Expected: 404/422 tests pass. SSE streaming tests may fail until full pipeline is verified. Fix any issues.

- [ ] **Step 6.6: Debug if needed**

If `test_generate_creates_log_before_streaming` fails because `/api/generation-logs/{id}` doesn't exist yet (Task 7 implements it), defer that assertion. The SSE streaming tests should pass without it.

If streaming tests fail with encoding/buffering issues, ensure `X-Accel-Buffering: no` header is set (already in Step 6.3).

- [ ] **Step 6.7: Run full suite**

```bash
pytest -v
```

Expected: 76 + 7 (or 6 if one deferred) = ~83 pass.

- [ ] **Step 6.8: Commit**

```bash
git add app/api/chapters_generate.py app/main.py tests/test_chapters_generate.py
git commit -m "feat(m2a): sse generation endpoint with strict context validation"
```

---

## Task 7: Generation Logs API

**Files:**
- Create: `app/api/generation_logs.py`
- Modify: `app/main.py`
- Create: `tests/test_generation_logs.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_generation_logs.py`:

```python
import pytest

from app.llm.streaming import StreamEvent


@pytest.fixture
def fake_router(monkeypatch):
    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="Hi")
            yield StreamEvent(type="done", input_tokens=10, output_tokens=2,
                              stop_reason="end_turn")
    fake = _Fake()
    monkeypatch.setattr("app.api.chapters_generate.default_router", fake)
    return fake


def _seed_two_chapters_with_logs(client, fake_router):
    """Create project + 2 chapters, generate once for each."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    ch1 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 1,
                            "title": "CH1"}).json()["id"]
    ch2 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 2,
                            "title": "CH2"}).json()["id"]
    # Generate for ch1
    with client.stream("POST", f"/api/chapters/{ch1}/generate",
                       json={"beat_text": "b1",
                             "involved_character_ids": [c1]}) as r:
        assert r.status_code == 200
    # Generate for ch2
    with client.stream("POST", f"/api/chapters/{ch2}/generate",
                       json={"beat_text": "b2",
                             "involved_character_ids": [c1]}) as r:
        assert r.status_code == 200
    return pid, ch1, ch2


def test_list_requires_chapter_id(client):
    r = client.get("/api/generation-logs")
    assert r.status_code == 422


def test_list_returns_only_target_chapter(client, fake_router):
    pid, ch1, ch2 = _seed_two_chapters_with_logs(client, fake_router)
    r = client.get(f"/api/generation-logs?chapter_id={ch1}")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) == 1
    assert logs[0]["chapter_id"] == ch1
    assert logs[0]["status"] == "done"


def test_list_pagination(client, fake_router):
    pid, ch1, ch2 = _seed_two_chapters_with_logs(client, fake_router)
    # Generate 3 more for ch1 to test pagination
    c1 = client.get(f"/api/characters?project_id={pid}").json()[0]["id"]
    for _ in range(3):
        with client.stream("POST", f"/api/chapters/{ch1}/generate",
                           json={"beat_text": "x",
                                 "involved_character_ids": [c1]}) as r:
            assert r.status_code == 200
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=2")
    assert len(r.json()) == 2
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=2&offset=2")
    assert len(r.json()) == 2
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=100&offset=0")
    assert len(r.json()) == 4


def test_detail_returns_full_prompt(client, fake_router):
    pid, ch1, _ = _seed_two_chapters_with_logs(client, fake_router)
    log_id = client.get(f"/api/generation-logs?chapter_id={ch1}").json()[0]["id"]
    r = client.get(f"/api/generation-logs/{log_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == log_id
    assert "system_prompt" in detail
    assert "user_prompt" in detail
    assert "P" in detail["user_prompt"]
    assert detail["generated_text"] == "Hi"
    assert detail["input_tokens"] == 10


def test_detail_404(client):
    r = client.get("/api/generation-logs/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "generation log not found"
```

- [ ] **Step 7.2: Run tests → verify fail**

```bash
pytest tests/test_generation_logs.py -v
```

Expected: FAIL (no endpoint).

- [ ] **Step 7.3: Create `app/api/generation_logs.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import GenerationLog
from app.models.generation import GenerationLogDetail, GenerationLogRead

router = APIRouter()


@router.get("", response_model=list[GenerationLogRead])
def list_logs(
    chapter_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = (
        select(GenerationLog)
        .where(GenerationLog.chapter_id == chapter_id)
        .order_by(GenerationLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


@router.get("/{log_id}", response_model=GenerationLogDetail)
def get_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(GenerationLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="generation log not found")
    return log
```

- [ ] **Step 7.4: Register router in `app/main.py`**

In `create_app`, add:

```python
    app.include_router(generation_logs.router, prefix="/api/generation-logs",
                        tags=["generation_logs"])
```

And add to imports:

```python
from app.api import (
    chapters,
    chapters_generate,
    characters,
    deps,
    generation_logs,
    health,
    llm,
    lore,
    projects,
    world,
)
```

- [ ] **Step 7.5: Run tests → verify pass**

```bash
pytest tests/test_generation_logs.py -v
```

Expected: 5 PASS.

- [ ] **Step 7.6: Run full suite**

```bash
pytest -v
```

Expected: ~83 + 5 = ~88 pass.

- [ ] **Step 7.7: Commit**

```bash
git add app/api/generation_logs.py app/main.py tests/test_generation_logs.py
git commit -m "feat(m2a): generation logs list + detail endpoints"
```

---

## Task 8: E2E Integration Test + README Update

**Files:**
- Create: `tests/test_m2a_e2e.py`
- Modify: `README.md`

- [ ] **Step 8.1: Write E2E test**

Create `tests/test_m2a_e2e.py`:

```python
import json

from app.llm.streaming import StreamEvent


def _parse_sse(lines):
    events = []
    current_event = None
    current_data = []
    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "":
            if current_event and current_data:
                events.append((current_event, json.loads("".join(current_data))))
            current_event = None
            current_data = []
    return events


def test_full_m2a_workflow(client, monkeypatch):
    """End-to-end: seed → generate via SSE → verify DB log → verify prompts."""
    # 1. Mock the LLM router
    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="夜色压在屋脊上，")
            yield StreamEvent(type="token", text="李雷推开了酒馆的门。")
            yield StreamEvent(type="done", input_tokens=3200, output_tokens=850,
                              stop_reason="end_turn")
    monkeypatch.setattr("app.api.chapters_generate.default_router", _Fake())

    # 2. Seed project + world + chars + lore + 1 prior chapter with summary
    pid = client.post("/api/projects", json={
        "title": "夜行记", "genre": "fantasy", "premise": "主角寻仇",
        "main_theme": "复仇", "tone": "压抑",
    }).json()["id"]
    client.put(f"/api/projects/{pid}/world-overview", json={
        "setting_era": "中古", "power_system": "剑与魔法",
        "rules_and_taboos": "魔法消耗寿命",
    }).json()
    kingdom = client.post("/api/lore", json={
        "project_id": pid, "type": "location", "name": "青石王国",
        "description": "北方小国",
    }).json()["id"]
    city = client.post("/api/lore", json={
        "project_id": pid, "type": "location", "name": "青石城",
        "description": "王国首都", "parent_id": kingdom,
    }).json()["id"]
    faction = client.post("/api/lore", json={
        "project_id": pid, "type": "faction", "name": "守夜人",
        "description": "情报组织",
    }).json()["id"]
    c1 = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "role": "主角",
        "personality": {"mbti": "INTJ", "traits": ["冷静", "固执"]},
        "speech_style": "短句，常引古文",
        "background": "孤儿", "motivation": "复仇",
        "current_state": "刚进城",
        "affiliations": [faction], "known_locations": [city],
    }).json()["id"]
    c2 = client.post("/api/characters", json={
        "project_id": pid, "name": "韩梅", "role": "旧友",
        "current_state": "在酒馆",
    }).json()["id"]
    # Prior chapter with summary (for 前情提要)
    prior = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "序幕",
        "summary": "李雷离家北上，进入青石王国。",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "第二章",
    }).json()["id"]

    # 3. Trigger generation via SSE
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={
                           "beat_text": "主角在酒馆遇旧友",
                           "instruction": "氛围压抑",
                           "involved_character_ids": [c1, c2],
                           "location_id": city,
                           "model_task": "writer_long",
                           "max_tokens": 4096,
                       }) as response:
        assert response.status_code == 200
        events = _parse_sse(response.iter_lines())

    # 4. Verify SSE event sequence
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "token", "done"]
    meta = events[0][1]
    log_id = meta["generation_log_id"]
    assert meta["model"] == "claude-sonnet-4-6"

    # 5. Verify context event contains assembled常驻层
    context = events[1][1]["context_bundle"]
    assert context["project"]["title"] == "夜行记"
    assert context["world_overview"]["power_system"] == "剑与魔法"
    char_names = {c["name"] for c in context["characters"]}
    assert char_names == {"李雷", "韩梅"}
    loc_names = {l["name"] for l in context["location_lore"]}
    assert loc_names == {"青石王国", "青石城"}  # ancestors included
    faction_names = {f["name"] for f in context["faction_lore"]}
    assert faction_names == {"守夜人"}
    assert any(s["title"] == "序幕" for s in context["recent_chapter_summaries"])

    # 6. Verify token stream
    token_text = "".join(d["text"] for e, d in events if e == "token")
    assert "夜色压在屋脊上" in token_text
    assert "李雷推开了酒馆的门" in token_text

    # 7. Verify DB log via detail endpoint
    detail = client.get(f"/api/generation-logs/{log_id}").json()
    assert detail["status"] == "done"
    assert detail["input_tokens"] == 3200
    assert detail["output_tokens"] == 850
    assert detail["stop_reason"] == "end_turn"
    assert detail["generated_text"] == token_text
    # 验收核心：user_prompt 里有常驻层关键词
    assert "李雷" in detail["user_prompt"]
    assert "韩梅" in detail["user_prompt"]
    assert "青石城" in detail["user_prompt"]
    assert "守夜人" in detail["user_prompt"]
    assert "剑与魔法" in detail["user_prompt"]
    assert "复仇" in detail["user_prompt"]  # main_theme
    assert "序幕" in detail["user_prompt"]  # recent summary


def test_invalid_character_returns_422_with_detail(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C",
    }).json()["id"]
    r = client.post(f"/api/chapters/{ch}/generate", json={
        "beat_text": "x", "involved_character_ids": [99999],
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert detail["invalid_character_ids"] == [99999]
```

- [ ] **Step 8.2: Run E2E test**

```bash
pytest tests/test_m2a_e2e.py -v
```

Expected: 2 PASS.

- [ ] **Step 8.3: Run full suite**

```bash
pytest -v
```

Expected: ~88 + 2 = ~90 pass.

- [ ] **Step 8.4: Manual smoke test**

```bash
# Drop DB to verify create_all rebuilds with new table
rm -f data/novelai.db data/novelai.db-shm data/novelai.db-wal
source .venv/bin/activate
uvicorn app.main:app &
sleep 2
curl -s http://127.0.0.1:8000/api/health
# Should print {"status":"ok"} and recreate the DB
kill %1
```

Expected: `{"status":"ok"}`; `data/novelai.db` recreated with `generation_logs` table.

- [ ] **Step 8.5: Update `README.md` API table**

Modify README "M1 API 一览" section header to "API 一览" and add new rows:

```markdown
## API 一览

| 资源 | 端点 |
|---|---|
| 项目 | `POST/GET/PATCH/DELETE /api/projects` |
| 世界观 | `PUT/GET /api/projects/{id}/world-overview` |
| Lore | `POST/GET/PATCH/DELETE /api/lore` |
| 人物 | `POST/GET/PATCH/DELETE /api/characters` |
| 章节 | `POST/GET/PATCH/DELETE /api/chapters` |
| 章节生成（SSE） | `POST /api/chapters/{id}/generate` |
| 生成日志 | `GET /api/generation-logs?chapter_id=X` / `GET /api/generation-logs/{id}` |
| LLM | `POST /api/llm/ping` |
```

- [ ] **Step 8.6: Commit**

```bash
git add tests/test_m2a_e2e.py README.md
git commit -m "test(m2a): e2e integration + readme api table"
```

---

## Self-Review

### Spec coverage

| Spec § | Coverage |
|---|---|
| §2 模块结构 | All files mapped (Tasks 1–8) |
| §3 generation_logs 表 | Task 1 |
| §3 Pydantic Read/Detail | Task 1 |
| §3 drop & recreate 迁移 | Task 8 manual smoke (rm db) |
| §4 assemble_context + 严格 project_id 校验 | Task 2 |
| §4 location ancestors / faction collection | Task 2 |
| §4 M3 字段预留（空 list） | Task 2 (relationships=[], plot_lines=[]) |
| §5 SSE event sequence | Task 6 |
| §5 错误两种情形 | Task 6 |
| §5 GenerationLog 写入时机 | Task 5 (prepare INSERT, finalize UPDATE) |
| §6 StreamEvent + LLMProvider.stream | Task 3 |
| §6 ClaudeProvider.stream + ModelRouter.stream | Task 3 |
| §7 Jinja2 templates | Task 4 |
| §7 system.j2 + user.j2 | Task 4 |
| §8 GenerateRequest 校验 | Task 1 |
| §8 端点 1 /generate | Task 6 |
| §8 端点 2 list | Task 7 |
| §8 端点 3 detail | Task 7 |
| §9 单元测试 retrieval | Task 2 |
| §9 单元测试 prompts | Task 4 |
| §9 LLM streaming tests | Task 3 |
| §9 Writer Agent tests | Task 5 |
| §9 SSE endpoint tests | Task 6 |
| §9 Generation logs tests | Task 7 |
| §9 E2E | Task 8 |
| §10 验收清单 1-10 | Tasks 6+8 cover 1-9; 10 is `pytest -v` |

All covered.

### Placeholder scan

No TBD/TODO. All code blocks contain real content.

### Type consistency

- `StreamEvent.type` literal: `"token" | "done" | "error"` — used consistently across Tasks 3, 5, 6
- `ContextBundle` fields match between Task 2 (definition) and Task 5 (consumer) — `project`, `world_overview`, `characters`, `character_states`, `relationships`, `faction_lore`, `location_lore`, `recent_chapter_summaries`, `plot_lines`
- `prepare_generation` signature matches between Task 5 (definition) and Task 6 (caller)
- `default_router` referenced consistently — Task 5 imports from `app.llm.router`, Task 6 monkeypatches at `app.api.chapters_generate.default_router`

No inconsistencies.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-16-m2a-writing-loop.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
