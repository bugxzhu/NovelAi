# M4a Reviewer Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户写完章节后能一键 5 维度审稿（人物/关系/情节/伏笔/世界观），Modal 展示 Issue 列表 + TipTap 高亮 location，1 次 LLM 调用合并维度。

**Architecture:** 同步 POST 端点（与 finalize 同模式）；retrieval 新增 `assemble_review_context()`（与写作路径分离，拉更广上下文）；TipTap 自定义 Mark 高亮 location，substring match 失败时优雅降级；Issue 不持久化（仅 generation_logs 审计）。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0；Next.js 15 + TipTap v3 + Zustand + Vitest + Playwright。

**Spec:** `docs/superpowers/specs/2026-06-21-m4a-reviewer-design.md`

**Port conventions:** Backend `http://127.0.0.1:8005`, Frontend `http://localhost:3300`.

---

## File Structure

**Backend new files:**
- `app/models/review.py` — `Issue`, `ReviewResponse` Pydantic schemas
- `app/agents/reviewer.py` — Reviewer Agent orchestrator
- `app/api/chapters_review.py` — POST endpoint
- `app/llm/prompts/reviewer/system.j2` — 5-dimension rules + JSON schema
- `app/llm/prompts/reviewer/user.j2` — context + chapter content
- `tests/test_reviewer_prompts.py`
- `tests/test_assemble_review_context.py`
- `tests/test_reviewer_agent.py`
- `tests/test_chapters_review.py`

**Backend modified files:**
- `app/memory/errors.py` — add `ReviewError`
- `app/memory/retrieval.py` — add `ReviewContextBundle` + `assemble_review_context()`
- `app/main.py` — register chapters_review router

**Frontend new files:**
- `web/components/editor/ReviewButton.tsx`
- `web/components/editor/ReviewModal.tsx`
- `web/components/editor/tiptap/IssueHighlight.ts`
- `web/tests/ReviewButton.test.tsx`
- `web/tests/ReviewModal.test.tsx`
- `web/tests/e2e/review-highlight.spec.ts`

**Frontend modified files:**
- `web/components/editor/extensions.ts` — register IssueHighlight
- `web/components/editor/ChapterEditor.tsx` — pass editor to ReviewModal; render ReviewButton in toolbar
- `web/lib/store.ts` — add review slice (issuesByChapter, modalOpenFor)
- `web/lib/api.ts` — add `reviewChapter`
- `web/lib/types.ts` — add Issue + ReviewResponse

---

## Task 1: ReviewError + Pydantic schemas

**Files:**
- Modify: `app/memory/errors.py` (append `ReviewError` class)
- Create: `app/models/review.py`

- [ ] **Step 1: Add ReviewError to errors.py**

Append to `/Users/bugx/novelAI/app/memory/errors.py`:

```python


class ReviewError(Exception):
    """LLM review failed (invalid JSON, missing issues_by_category, max_tokens, etc.)."""
```

- [ ] **Step 2: Create app/models/review.py**

Create `/Users/bugx/novelAI/app/models/review.py`:

```python
from typing import Literal

from pydantic import BaseModel


Severity = Literal["error", "warn", "info"]
Category = Literal["character", "relationship", "plot", "foreshadow", "worldview"]


class Issue(BaseModel):
    severity: Severity
    category: Category
    location: str          # verbatim quote 10-50 chars, or "" if whole-chapter issue
    description: str
    suggestion: str


class ReviewResponse(BaseModel):
    chapter_id: int
    issues: list[Issue]
    log_id: int            # generation_logs id (audit)
```

- [ ] **Step 3: Verify imports**

Run: `cd /Users/bugx/novelAI && python -c "from app.memory.errors import ReviewError; from app.models.review import Issue, ReviewResponse; print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add app/memory/errors.py app/models/review.py
git commit -m "feat(m4a): ReviewError + Issue/ReviewResponse schemas"
```

---

## Task 2: `assemble_review_context()` in retrieval.py

**Files:**
- Modify: `app/memory/retrieval.py` (append new dataclass + function)
- Create: `tests/test_assemble_review_context.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/bugx/novelAI/tests/test_assemble_review_context.py`:

```python
"""M4a: assemble_review_context() tests."""
import pytest
from app.memory.retrieval import assemble_review_context
from app.memory.schema import (
    Chapter, Character, CharacterState, Event, LoreEntry, Project,
    Relationship, WorldOverview,
)


def _db_session(db_session):
    """The conftest db_session fixture already does the right thing."""
    return db_session


def _seed_full_project(db_session):
    p = Project(title="T", genre="g", premise="p")
    db_session.add(p); db_session.flush()

    wo = WorldOverview(project_id=p.id, setting_era="古代", power_system="魔法")
    db_session.add(wo)

    ch1 = Chapter(project_id=p.id, order_index=1, title="C1", content="第一章正文",
                  summary="第一章摘要", status="final")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2", content="第二章正文",
                  status="draft")
    db_session.add_all([ch1, ch2]); db_session.flush()

    c1 = Character(project_id=p.id, name="李雷", role="protagonist")
    c2 = Character(project_id=p.id, name="韩梅", role="supporting")
    db_session.add_all([c1, c2]); db_session.flush()
    ch2.last_involved_character_ids = [c1.id, c2.id]

    # Character states for c1
    s1 = CharacterState(character_id=c1.id, chapter_id=ch1.id,
                        state_snapshot="警惕", change_summary="初入")
    db_session.add(s1)

    # Relationship: c1→c2 enemies
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.8, valid_from_chapter=ch1.id,
    ))

    # Event in ch1 with foreshadows
    e1 = Event(project_id=p.id, chapter_id=ch1.id,
               title="伏击", description="李雷被伏击",
               foreshadows=[])
    db_session.add(e1); db_session.flush()
    # Event in ch2 that foreshadows e1 (so e1 has payoff_of=[e2.id])
    e2 = Event(project_id=p.id, chapter_id=ch2.id,
               title="复仇", description="李雷复仇",
               foreshadows=[e1.id])
    db_session.add(e2)

    # Lore entries
    db_session.add(LoreEntry(project_id=p.id, type="location", name="残月酒馆"))
    db_session.add(LoreEntry(project_id=p.id, type="faction", name="守夜人"))

    db_session.commit()
    return p, ch1, ch2, c1, c2


def test_assemble_review_context_minimal(db_session):
    """Single chapter, no states/relationships/events — should not raise."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=ch.id)
    assert bundle.chapter.id == ch.id
    assert bundle.characters == []
    assert bundle.character_states_history == {}
    assert bundle.relationships == []
    assert bundle.events == []
    assert bundle.recent_chapter_summaries == []


def test_assemble_review_context_resolves_involved_characters(db_session):
    """Uses chapter.last_involved_character_ids to pick characters."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    names = {c.name for c in bundle.characters}
    assert names == {"李雷", "韩梅"}


def test_assemble_review_context_state_history(db_session):
    """Pulls last N states per character."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    # c1 has 1 state in ch1
    assert c1.id in bundle.character_states_history
    states = bundle.character_states_history[c1.id]
    assert len(states) == 1
    assert states[0].current_state == "警惕"


def test_assemble_review_context_state_history_limit(db_session):
    """state_history_limit caps number of states."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    chapters = []
    for i in range(1, 6):  # 5 chapters
        ch = Chapter(project_id=p.id, order_index=i, title=f"C{i}", content="x")
        db_session.add(ch); chapters.append(ch)
    db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    db_session.add(c1); db_session.flush()
    for ch in chapters:
        db_session.add(CharacterState(
            character_id=c1.id, chapter_id=ch.id,
            state_snapshot=f"state-{ch.order_index}", change_summary="",
        ))
    db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=chapters[-1].id,
                                      state_history_limit=3)
    assert len(bundle.character_states_history[c1.id]) == 3
    # Newest first
    snapshots = [s.current_state for s in bundle.character_states_history[c1.id]]
    assert snapshots == ["state-5", "state-4", "state-3"]


def test_assemble_review_context_includes_all_relationships(db_session):
    """All project relationships, not just involved-pair."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    assert len(bundle.relationships) == 1
    assert bundle.relationships[0].from_name == "李雷"
    assert bundle.relationships[0].to_name == "韩梅"


def test_assemble_review_context_includes_events_with_payoff(db_session):
    """Events have derived payoff_of and is_unpaid."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    by_title = {e.title: e for e in bundle.events}
    # e1 (伏击) is foreshadowed by e2 (复仇) → e1.payoff_of=[e2.id]
    assert by_title["伏击"].payoff_of == [by_title["复仇"].id]
    # e2 (复仇) foreshadows e1 (伏击); e1 has no external payoff → e2.is_unpaid
    assert by_title["复仇"].is_unpaid is True


def test_assemble_review_context_excludes_current_chapter_summary(db_session):
    """recent_chapter_summaries does NOT include the chapter being reviewed."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    # ch2 has no summary anyway, but ch1 should be present
    assert any(s.title == "C1" for s in bundle.recent_chapter_summaries)
    # Reviewing ch1 → ch1's summary should NOT appear
    bundle_ch1 = assemble_review_context(db_session, chapter_id=ch1.id)
    assert not any(s.title == "C1" for s in bundle_ch1.recent_chapter_summaries)


def test_assemble_review_context_includes_lore(db_session):
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    types = {l.type for l in bundle.lore_entries}
    assert types == {"location", "faction"}
```

**Note on `db_session` fixture:** The conftest already provides `db_session`. Use it directly.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_assemble_review_context.py -v 2>&1 | tail -10`
Expected: FAIL with `ImportError: cannot import name 'assemble_review_context'`

- [ ] **Step 3: Add the dataclass + function to retrieval.py**

Append to `/Users/bugx/novelAI/app/memory/retrieval.py`:

```python
@dataclass
class ReviewContextBundle:
    """Richer context for review: includes history (state/relationship/events)
    that writing doesn't need."""
    project: Project
    world_overview: WorldOverview | None
    chapter: Chapter
    characters: list[Character]
    character_states_history: dict[int, list[CharacterStateSnapshot]]
    relationships: list[RelationshipView]
    events: list[Any]  # list[EventRead]; use Any to avoid circular import
    lore_entries: list[LoreEntry]
    recent_chapter_summaries: list[ChapterSummary]


def _target_has_external_payoff(
    payoff_map: dict[int, list[int]], src_id: int, target_id: int
) -> bool:
    """Target is referenced by some event OTHER than src itself.

    Mirrors app/api/events.py logic. Duplicated (not imported) to avoid
    Reviewer depending on events API internals.
    """
    return any(pid != src_id for pid in payoff_map.get(target_id, []))


def assemble_review_context(
    db: Session,
    *,
    chapter_id: int,
    state_history_limit: int = 5,
) -> ReviewContextBundle:
    """Assemble rich context for chapter review.

    Unlike assemble_context (writing-focused, minimal tokens), this pulls:
    - last N character_states per character (for arc analysis)
    - all current relationships (not just involved-pair)
    - all events with derived payoff_of + is_unpaid (for foreshadow integrity)
    - all lore entries (for worldview consistency)
    - all chapter summaries (for plot continuity)

    Raises:
        ChapterNotFoundError: chapter does not exist.
    """
    from app.memory.schema import CharacterState, Event, Relationship
    from app.models.event import EventRead
    from app.models.relationship import RelationshipHistoryItem  # noqa: F401 (kept for clarity)

    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)
    project_id = chapter.project_id

    project = db.get(Project, project_id)
    world_overview = db.scalar(
        select(WorldOverview).where(WorldOverview.project_id == project_id)
    )

    # Resolve involved characters from chapter.last_involved_character_ids
    involved_ids = chapter.last_involved_character_ids or []
    if involved_ids:
        characters = list(db.scalars(
            select(Character).where(Character.id.in_(involved_ids))
        ))
    else:
        characters = list(db.scalars(
            select(Character).where(Character.project_id == project_id)
        ))

    # All project characters (for name resolution in relationships/events)
    all_chars = list(db.scalars(
        select(Character).where(Character.project_id == project_id)
    ))
    all_char_by_id = {c.id: c for c in all_chars}

    # Per-character state history (last N, newest first)
    char_states: dict[int, list[CharacterStateSnapshot]] = {}
    for c in characters:
        states = list(db.scalars(
            select(CharacterState)
            .where(CharacterState.character_id == c.id)
            .join(Chapter, Chapter.id == CharacterState.chapter_id)
            .order_by(Chapter.order_index.desc(), CharacterState.id.desc())
            .limit(state_history_limit)
        ))
        char_states[c.id] = [
            CharacterStateSnapshot(
                current_state=s.state_snapshot,
                change_summary=s.change_summary,
            )
            for s in states
        ]

    # All current-valid relationships in project
    relationships: list[RelationshipView] = []
    rels = list(db.scalars(
        select(Relationship).where(
            Relationship.project_id == project_id,
            Relationship.valid_to_chapter.is_(None),
        )
    ))
    for r in rels:
        from_c = all_char_by_id.get(r.from_char_id)
        to_c = all_char_by_id.get(r.to_char_id)
        if from_c and to_c:
            relationships.append(RelationshipView(
                from_char_id=r.from_char_id, to_char_id=r.to_char_id,
                from_name=from_c.name, to_name=to_c.name,
                type=r.type, strength=r.strength, description=r.description,
            ))

    # All events with derived fields
    all_events_orm = list(db.scalars(
        select(Event).where(Event.project_id == project_id)
    ))
    payoff_map: dict[int, list[int]] = {}
    event_title_by_id = {e.id: e.title for e in all_events_orm}
    for e in all_events_orm:
        for target_id in (e.foreshadows or []):
            payoff_map.setdefault(target_id, []).append(e.id)

    chapters_in_project = list(db.scalars(
        select(Chapter).where(Chapter.project_id == project_id)
    ))
    chapter_by_id = {c.id: c for c in chapters_in_project}

    events_view: list[EventRead] = []
    for e in all_events_orm:
        ch = chapter_by_id.get(e.chapter_id)
        involved_names = [
            all_char_by_id[i].name for i in (e.involved_characters or [])
            if i in all_char_by_id
        ]
        loc = db.get(LoreEntry, e.location_id) if e.location_id else None
        is_unpaid = bool(e.foreshadows) and any(
            not _target_has_external_payoff(payoff_map, e.id, tid)
            for tid in (e.foreshadows or [])
        )
        events_view.append(EventRead(
            id=e.id, project_id=e.project_id, chapter_id=e.chapter_id,
            chapter_title=ch.title if ch else "",
            chapter_order=ch.order_index if ch else 0,
            title=e.title, description=e.description,
            involved_characters=e.involved_characters or [],
            involved_character_names=involved_names,
            location_id=e.location_id,
            location_name=loc.name if loc else "",
            plot_line_id=e.plot_line_id,
            foreshadows=e.foreshadows or [],
            payoff_of=payoff_map.get(e.id, []),
            payoff_of_titles=[
                event_title_by_id.get(pid, "") for pid in payoff_map.get(e.id, [])
            ],
            is_unpaid=is_unpaid,
            extractor_log_id=e.extractor_log_id,
            pending_update_id=e.pending_update_id,
            created_at=e.created_at, updated_at=e.updated_at,
        ))

    # All lore entries
    lore_entries = list(db.scalars(
        select(LoreEntry).where(LoreEntry.project_id == project_id)
    ))

    # All chapter summaries except current
    recent_chapter_summaries = [
        ChapterSummary(c.id, c.order_index, c.title, c.summary)
        for c in chapters_in_project
        if c.id != chapter_id and c.summary
    ]

    return ReviewContextBundle(
        project=project, world_overview=world_overview, chapter=chapter,
        characters=characters, character_states_history=char_states,
        relationships=relationships, events=events_view, lore_entries=lore_entries,
        recent_chapter_summaries=recent_chapter_summaries,
    )
```

**Note:** `EventRead` is imported inside the function (not at module top) to avoid circular import risk between `app/memory/retrieval.py` and `app/models/event.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_assemble_review_context.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Run regression**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_context_assembly.py -v 2>&1 | tail -5`
Expected: ALL PASS (assemble_context unchanged).

- [ ] **Step 6: Commit**

```bash
cd /Users/bugx/novelAI
git add app/memory/retrieval.py tests/test_assemble_review_context.py
git commit -m "feat(m4a): assemble_review_context with rich context for review"
```

---

## Task 3: Reviewer prompts

**Files:**
- Create: `app/llm/prompts/reviewer/system.j2`
- Create: `app/llm/prompts/reviewer/user.j2`
- Create: `tests/test_reviewer_prompts.py`

- [ ] **Step 1: Write the failing tests**

Create `/Users/bugx/novelAI/tests/test_reviewer_prompts.py`:

```python
"""M4a: reviewer prompt rendering tests."""
from types import SimpleNamespace

from app.llm.prompts import render


def _stub_project():
    return SimpleNamespace(title="T", genre="g", main_theme="mt", tone="t", premise="p")


def _stub_chapter():
    return SimpleNamespace(order_index=3, title="C3", content="正文...")


def test_render_reviewer_system():
    """system.j2 contains 5-dimension rules + JSON schema + location constraint."""
    out = render("reviewer/system.j2")
    assert "人物一致性" in out and "character" in out
    assert "关系合理性" in out and "relationship" in out
    assert "情节矛盾" in out and "plot" in out
    assert "伏笔完整性" in out and "foreshadow" in out
    assert "世界观一致性" in out and "worldview" in out
    assert "issues_by_category" in out
    # location constraint
    assert "逐字摘录" in out or "verbatim" in out.lower()


def test_render_reviewer_user_minimal():
    """user.j2 renders with empty context fields (no world_overview, no chars)."""
    out = render(
        "reviewer/user.j2",
        project=_stub_project(),
        world_overview=None,
        chapter=_stub_chapter(),
        characters=[],
        character_states_history={},
        relationships=[],
        events=[],
        lore_entries=[],
        recent_chapter_summaries=[],
    )
    assert "C3" in out
    assert "正文..." in out


def test_render_reviewer_user_full():
    """user.j2 renders all context fields."""
    char = SimpleNamespace(
        id=1, name="李雷", role="protagonist",
        personality={"brave": True}, speech_style="直接",
        motivation="复仇", background="孤儿",
    )
    state = SimpleNamespace(current_state="警惕", change_summary="初入")
    rel = SimpleNamespace(
        from_name="李雷", to_name="韩梅",
        type="仇人", strength=-0.8, description="伏击",
    )
    event = SimpleNamespace(
        chapter_order=1, title="伏击", description="李雷被伏击",
        foreshadows=[], payoff_of=[], payoff_of_titles=[],
        is_unpaid=False,
    )
    lore = SimpleNamespace(type="location", name="残月酒馆", description="酒馆")
    summary = SimpleNamespace(order_index=1, title="C1", summary="摘要")

    wo = SimpleNamespace(
        setting_era="古代", power_system="魔法",
        rules_and_taboos="禁忌", geography_summary="地理",
        culture_summary="文化",
    )

    out = render(
        "reviewer/user.j2",
        project=_stub_project(),
        world_overview=wo,
        chapter=_stub_chapter(),
        characters=[char],
        character_states_history={1: [state]},
        relationships=[rel],
        events=[event],
        lore_entries=[lore],
        recent_chapter_summaries=[summary],
    )
    assert "李雷" in out
    assert "仇人" in out
    assert "伏击" in out
    assert "残月酒馆" in out
    assert "摘要" in out
    assert "魔法" in out  # world_overview.power_system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_reviewer_prompts.py -v 2>&1 | tail -10`
Expected: FAIL — templates don't exist.

- [ ] **Step 3: Create system.j2**

Create `/Users/bugx/novelAI/app/llm/prompts/reviewer/system.j2` with the content from spec §6.1 (full text below):

```
你是一位严格的小说审稿编辑，从 5 个维度审查章节质量。你不修改原文，只产出结构化报告。

# 审查维度

## 1. 人物一致性（character）
- 性格、说话风格、动机是否与档案一致
- 当前情绪/状态是否符合人物轨迹（参考 character_states 历史）
- 是否有不符合背景设定的行为

## 2. 关系合理性（relationship）
- 人物间互动是否符合当前关系（仇人不应友善对话等）
- 关系强度的表现是否合理

## 3. 斄弱环节
- 与前几章情节是否冲突
- 时间线是否连贯
- 角色行为是否符合既定目标

## 4. 伏笔完整性（foreshadow）
- 本章是否兑现了之前的伏笔（参考 events 列表 + is_unpaid 标记）
- 本章新埋的伏笔是否有过早暴露或逻辑漏洞
- 是否有"无铺垫爆发"（payoff_of 为空但描述像兑现）

## 5. 世界观一致性（worldview）
- 能力/魔法/科技是否符合 power_system
- 是否违反 rules_and_taboos
- 地点/势力/物品属性是否与 lore_entries 一致

# 输出格式

严格输出 JSON，按 category 分组。不要输出 JSON 之外的任何内容（包括代码块标记）。

{
  "issues_by_category": {
    "character": [
      {
        "severity": "error|warn|info",
        "location": "原文逐字摘录，10-50 字",
        "description": "问题描述",
        "suggestion": "修改建议"
      }
    ],
    "relationship": [...],
    "plot": [...],
    "foreshadow": [...],
    "worldview": [...]
  }
}

如果某维度无问题，对应数组返回空 []。永远不要省略任何 category 的 key。

# severity 标准

- error：严重矛盾或硬事实违反；必须修改
- warn：可能的问题；建议修改
- info：风格建议或观察；可选修改

# 重要：location 字段

- 必须是从原文**逐字摘录**的片段，10-50 字
- 不允许复述、概括或改写
- 前端会用此字段在原文中高亮定位；不精确会导致定位失败
- 若问题不针对具体文段（如"整章节奏过快"），location 留空字符串 ""

# 输出原则

- 不修改原文，只产出报告
- 宁缺勿滥：不确定的不要报
- 严重问题报 error；边缘问题报 warn；纯观察报 info
- 同一问题不要在多个 category 重复报
```

**IMPORTANT:** In the spec, the third dimension was labeled `## 3. 情节矛盾（plot）`. The above template uses `## 3. 薄弱环节` as the heading but the JSON key remains `plot`. To match the test assertion `assert "情节矛盾" in out`, you must use `## 3. 情节矛盾（plot）` as the heading (not "薄弱环节"). Fix this before saving — the correct heading is:

```
## 3. 情节矛盾（plot）
```

- [ ] **Step 4: Create user.j2**

Create `/Users/bugx/novelAI/app/llm/prompts/reviewer/user.j2` with the content from spec §6.2 (full text):

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

# 待审章节
标题：第 {{ chapter.order_index }} 章 · {{ chapter.title }}

正文：
---
{{ chapter.content }}
---

# 涉及人物档案 + 状态轨迹
{% for c in characters %}
## {{ c.name }}（{{ c.role }}）
- 性格：{{ c.personality | tojson }}
- 说话风格：{{ c.speech_style }}
- 动机：{{ c.motivation }}
- 背景：{{ c.background }}
- 状态轨迹（最近 {{ character_states_history[c.id] | length }} 条，最新在前）：
{% for s in character_states_history[c.id] %}
  - {{ s.current_state }}{% if s.change_summary %}（{{ s.change_summary }}）{% endif %}
{% endfor %}
{% else %}
（无涉及人物档案）
{% endfor %}

# 当前人物关系
{% if relationships %}
{% for r in relationships %}
- {{ r.from_name }} → {{ r.to_name }}：{{ r.type }}（强度 {{ r.strength }}）{% if r.description %} — {{ r.description }}{% endif %}
{% endfor %}
{% else %}
（无）
{% endif %}

# 章节事件 + 伏笔
{% if events %}
{% for e in events %}
- 第 {{ e.chapter_order }} 章 · {{ e.title }}：{{ e.description }}
{% if e.foreshadows %}埋伏笔指向：{% for fid in e.foreshadows %}#{{ fid }} {% endfor %}{% endif %}
{% if e.payoff_of %}兑现了：{% for pid in e.payoff_of_titles %}{{ pid }}、{% endfor %}{% endif %}
{% if e.is_unpaid %}⚠️ 此事件含未兑现伏笔{% endif %}
{% endfor %}
{% else %}
（无）
{% endif %}

# 世界观设定（lore）
{% if lore_entries %}
{% for l in lore_entries %}
- [{{ l.type }}] {{ l.name }}：{{ l.description }}
{% endfor %}
{% else %}
（无）
{% endif %}

# 前情提要
{% if recent_chapter_summaries %}
{% for s in recent_chapter_summaries %}
- 第 {{ s.order_index }} 章 {{ s.title }}：{{ s.summary }}
{% endfor %}
{% else %}
（无前章）
{% endif %}

请按 5 维度审查本章并输出 issues_by_category。
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_reviewer_prompts.py -v`
Expected: ALL 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/bugx/novelAI
git add app/llm/prompts/reviewer/ tests/test_reviewer_prompts.py
git commit -m "feat(m4a): reviewer prompts (system + user)"
```

---

## Task 4: Reviewer agent

**Files:**
- Create: `app/agents/reviewer.py`
- Create: `tests/test_reviewer_agent.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/bugx/novelAI/tests/test_reviewer_agent.py`:

```python
"""M4a: reviewer agent tests (mock LLM)."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.reviewer import review_chapter, ReviewResult
from app.llm.base import LLMResponse
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.schema import Chapter, Project


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


def test_review_chapter_missing_issues_by_category_raises(db_session):
    p, ch = _seed_chapter(db_session)
    fake = _make_router(json.dumps({"something_else": {}}))
    # issues_by_category defaults to {} which is a dict, so NOT raising.
    # But empty dict → empty issues list. Verify behavior:
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
```

The test file's `db_session` fixture is provided by conftest.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_reviewer_agent.py -v 2>&1 | tail -10`
Expected: FAIL — `review_chapter` doesn't exist.

- [ ] **Step 3: Create reviewer.py**

Create `/Users/bugx/novelAI/app/agents/reviewer.py`:

```python
"""Reviewer Agent: 5-dimension chapter review in 1 merged LLM call.

Flow:
    1. assemble_review_context(db, chapter_id) → rich context bundle.
    2. render reviewer/system.j2 + user.j2.
    3. router.complete(request)  # single call.
    4. Parse JSON → list[Issue] (with tolerance).
    5. INSERT generation_logs (model_task='reviewer').

Race contract:
    review_chapter is NOT safe to run concurrently with accept/reject operations
    on the same chapter. The DB transaction only guarantees atomicity on its own
    writes (generation_logs INSERT), not isolation from concurrent mutations to
    related rows.
"""
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.llm.base import LLMRequest
from app.llm.prompts import render
from app.llm.router import ModelRouter, default_router
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.retrieval import assemble_review_context
from app.memory.schema import GenerationLog
from app.models.review import Issue

logger = logging.getLogger(__name__)

ALLOWED_SEVERITIES = {"error", "warn", "info"}
ALLOWED_CATEGORIES = {"character", "relationship", "plot", "foreshadow", "worldview"}


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ReviewResult:
    chapter_id: int
    issues: list[Issue]
    log_id: int


def review_chapter(
    db: Session,
    *,
    chapter_id: int,
    router: ModelRouter = default_router,
) -> ReviewResult:
    """Review a chapter across 5 dimensions. Single LLM call, sync.

    Raises:
        ChapterNotFoundError: chapter does not exist.
        ReviewError: LLM returned non-JSON, hit max_tokens, or returned
            issues_by_category that is not a dict.
    """
    bundle = assemble_review_context(db, chapter_id=chapter_id)

    system_prompt = render("reviewer/system.j2")
    user_prompt = render(
        "reviewer/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        chapter=bundle.chapter,
        characters=bundle.characters,
        character_states_history=bundle.character_states_history,
        relationships=bundle.relationships,
        events=bundle.events,
        lore_entries=bundle.lore_entries,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
    )

    request = LLMRequest(
        model_task="reviewer",
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
        temperature=0.1,
    )

    _, model_name = router.resolve_model("reviewer")
    response = router.complete(request)

    if response.stop_reason == "max_tokens":
        raise ReviewError(
            f"LLM hit max_tokens; output likely truncated. response={response.text[:500]}"
        )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ReviewError(
            f"LLM returned non-JSON: {e}; response={response.text[:500]}"
        )

    issues_by_category = parsed.get("issues_by_category")
    if issues_by_category is None:
        # Missing key → treat as empty (5 dimensions may all be clean)
        issues_by_category = {}
    if not isinstance(issues_by_category, dict):
        raise ReviewError(
            f"issues_by_category must be an object, got {type(issues_by_category).__name__}"
        )

    issues: list[Issue] = []
    for cat, raw_issues in issues_by_category.items():
        if cat not in ALLOWED_CATEGORIES:
            logger.info("reviewer: skipping unknown category %r", cat)
            continue
        if not isinstance(raw_issues, list):
            continue
        for raw in raw_issues:
            if not isinstance(raw, dict):
                continue
            severity = raw.get("severity", "info")
            if severity not in ALLOWED_SEVERITIES:
                severity = "info"
            description = (raw.get("description") or "").strip()
            if not description:
                continue  # 没 description 的 Issue 没意义
            issues.append(Issue(
                severity=severity,
                category=cat,  # type: ignore[arg-type]
                location=(raw.get("location") or "").strip(),
                description=description,
                suggestion=(raw.get("suggestion") or "").strip(),
            ))

    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=bundle.chapter.project_id,
        beat_text="(review)",
        instruction="",
        involved_character_ids=[c.id for c in bundle.characters],
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={
            "characters": len(bundle.characters),
            "relationships": len(bundle.relationships),
            "events": len(bundle.events),
            "lore": len(bundle.lore_entries),
            "summaries": len(bundle.recent_chapter_summaries),
        },
        generated_text=response.text,
        model=model_name,
        model_task="reviewer",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        stop_reason=response.stop_reason,
        status="done",
        started_at=_now(),
        finished_at=_now(),
    )

    try:
        db.add(log)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    return ReviewResult(chapter_id=chapter_id, issues=issues, log_id=log.id)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_reviewer_agent.py -v`
Expected: ALL 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/bugx/novelAI
git add app/agents/reviewer.py tests/test_reviewer_agent.py
git commit -m "feat(m4a): reviewer agent with 5-dimension merged call"
```

---

## Task 5: POST /api/chapters/{id}/review endpoint

**Files:**
- Create: `app/api/chapters_review.py`
- Modify: `app/main.py`
- Create: `tests/test_chapters_review.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/bugx/novelAI/tests/test_chapters_review.py`:

```python
"""M4a: POST /api/chapters/{id}/review endpoint tests."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_review_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"issues_by_category": {}}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_review.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_review_returns_404_unknown_chapter(client):
    r = client.post("/api/chapters/99999/review")
    assert r.status_code == 404


def test_review_success(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"issues_by_category": {
            "character": [
                {"severity": "warn", "location": "x",
                 "description": "y", "suggestion": ""},
            ],
        }}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 200
    data = r.json()
    assert data["chapter_id"] == ch
    assert len(data["issues"]) == 1
    assert data["issues"][0]["category"] == "character"
    assert data["log_id"] > 0


def test_review_llm_failure_returns_502(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(side_effect=RuntimeError("network"))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 502


def test_review_invalid_json_returns_422(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text="not json",
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 422
    assert "review_failed" in str(r.json())


def test_review_max_tokens_returns_422(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text="{truncated",
        input_tokens=10, output_tokens=20, stop_reason="max_tokens",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_chapters_review.py -v 2>&1 | tail -10`
Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Create chapters_review.py**

Create `/Users/bugx/novelAI/app/api/chapters_review.py`:

```python
"""M4a: POST /api/chapters/{id}/review — sync review across 5 dimensions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.reviewer import review_chapter
from app.api.deps import get_db
from app.llm.router import default_router
from app.memory.errors import ChapterNotFoundError, ReviewError
from app.memory.schema import Chapter
from app.models.review import ReviewResponse

router = APIRouter()


@router.post("/{chapter_id}/review", response_model=ReviewResponse)
def review(chapter_id: int, db: Session = Depends(get_db)):
    ch = db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    try:
        result = review_chapter(db, chapter_id=chapter_id, router=default_router)
    except ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="chapter not found")
    except ReviewError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "review_failed", "reason": str(e)[:200]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return ReviewResponse(
        chapter_id=result.chapter_id,
        issues=result.issues,
        log_id=result.log_id,
    )
```

- [ ] **Step 4: Register router in main.py**

In `/Users/bugx/novelAI/app/main.py`, add `chapters_review` to the `from app.api import (...)` block (alphabetical). After `chapters_finalize,`:

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
    projects,
    relationships,
    world,
)
```

After the `chapters_finalize.router` registration in `create_app()`, add:

```python
    app.include_router(chapters_review.router, prefix="/api/chapters",
                       tags=["chapters_review"])
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/bugx/novelAI && uv run pytest tests/test_chapters_review.py -v`
Expected: ALL 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/bugx/novelAI
git add app/api/chapters_review.py app/main.py tests/test_chapters_review.py
git commit -m "feat(m4a): POST /api/chapters/{id}/review endpoint"
```

---

## Task 6: Frontend types + API client

**Files:**
- Modify: `web/lib/types.ts` (add Issue + ReviewResponse)
- Modify: `web/lib/api.ts` (add reviewChapter method)

- [ ] **Step 1: Add types to types.ts**

Append to `/Users/bugx/novelAI/web/lib/types.ts`:

```typescript
// === M4a: Reviewer ===

export type Severity = "error" | "warn" | "info";
export type Category = "character" | "relationship" | "plot" | "foreshadow" | "worldview";

export interface Issue {
  severity: Severity;
  category: Category;
  location: string;
  description: string;
  suggestion: string;
}

export interface ReviewResponse {
  chapter_id: number;
  issues: Issue[];
  log_id: number;
}
```

- [ ] **Step 2: Add api method**

In `/Users/bugx/novelAI/web/lib/api.ts`, add `Issue, ReviewResponse` to the type imports. Inside the `api` object (after `finalizeChapter`), add:

```typescript
  // M4a: Reviewer
  reviewChapter: (chapterId: number) =>
    http<ReviewResponse>(`/api/chapters/${chapterId}/review`, { method: "POST" }),
```

- [ ] **Step 3: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/lib/types.ts web/lib/api.ts
git commit -m "feat(m4a): frontend types + api for review"
```

---

## Task 7: Zustand review slice

**Files:**
- Modify: `web/lib/store.ts` (append new store)

- [ ] **Step 1: Append review store**

In `/Users/bugx/novelAI/web/lib/store.ts`, after the last `create<...>()` call (at end of file), append:

```typescript

// === M4a: Review ===
// Issues are NOT persisted (每次启动从头开始). Tied to current session only.
interface ReviewState {
  issuesByChapter: Record<number, Issue[]>;
  modalOpenFor: number | null;
  setIssues: (chapterId: number, issues: Issue[]) => void;
  openModal: (chapterId: number) => void;
  closeModal: () => void;
  clearIssues: (chapterId: number) => void;
}

export const useReviewStore = create<ReviewState>((set) => ({
  issuesByChapter: {},
  modalOpenFor: null,
  setIssues: (chapterId, issues) =>
    set((s) => ({
      issuesByChapter: { ...s.issuesByChapter, [chapterId]: issues },
      modalOpenFor: chapterId,  // auto-open modal on set
    })),
  openModal: (chapterId) => set({ modalOpenFor: chapterId }),
  closeModal: () => set({ modalOpenFor: null }),
  clearIssues: (chapterId) =>
    set((s) => {
      const next = { ...s.issuesByChapter };
      delete next[chapterId];
      return {
        issuesByChapter: next,
        modalOpenFor: s.modalOpenFor === chapterId ? null : s.modalOpenFor,
      };
    }),
}));
```

Also add `Issue` to the type imports at top of `store.ts`:

```typescript
import type { Issue } from "./types";
```

**Note:** Place the `import type { Issue }` line alongside existing type imports if any; otherwise add it after the existing `import { create }` line.

- [ ] **Step 2: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/bugx/novelAI
git add web/lib/store.ts
git commit -m "feat(m4a): useReviewStore zustand slice (ephemeral)"
```

---

## Task 8: TipTap IssueHighlight Mark

**Files:**
- Create: `web/components/editor/tiptap/IssueHighlight.ts`
- Modify: `web/components/editor/extensions.ts`

- [ ] **Step 1: Create IssueHighlight.ts**

Create `/Users/bugx/novelAI/web/components/editor/tiptap/IssueHighlight.ts`:

```typescript
import { Mark, mergeAttributes } from "@tiptap/core";

export type Severity = "error" | "warn" | "info";

export interface IssueHighlightAttrs {
  issueId: string;
  severity: Severity;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    issueHighlight: {
      setIssueHighlight: (
        attrs: IssueHighlightAttrs,
        from: number,
        to: number,
      ) => ReturnType;
      unsetAllIssueHighlights: () => ReturnType;
    };
  }
}

const SEVERITY_CLASS: Record<Severity, string> = {
  error: "bg-red-300/50",
  warn: "bg-yellow-300/50",
  info: "bg-blue-300/50",
};

export const IssueHighlight = Mark.create({
  name: "issueHighlight",

  inclusive: false,

  addAttributes() {
    return {
      issueId: { default: null },
      severity: { default: "info" },
    };
  },

  parseHTML() {
    return [{ tag: "mark[data-issue-id]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const severity = (HTMLAttributes.severity as Severity) || "info";
    return [
      "mark",
      mergeAttributes(HTMLAttributes, {
        "data-issue-id": HTMLAttributes.issueId,
        class: SEVERITY_CLASS[severity],
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setIssueHighlight:
        (attrs, from, to) =>
        ({ editor }) => {
          editor.commands.setTextSelection({ from, to });
          editor.commands.setMark(this.name, attrs);
          return true;
        },
      unsetAllIssueHighlights:
        () =>
        ({ tr, state }) => {
          const { doc } = state;
          doc.descendants((node, pos) => {
            node.marks.forEach((mark) => {
              if (mark.type.name === this.name) {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            });
            return true;
          });
          return true;
        },
    };
  },
});
```

- [ ] **Step 2: Register in extensions.ts**

In `/Users/bugx/novelAI/web/components/editor/extensions.ts`, add the import + add to array:

```typescript
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import Placeholder from "@tiptap/extension-placeholder";
import CharacterCount from "@tiptap/extension-character-count";
import { IssueHighlight } from "./tiptap/IssueHighlight";

export const extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
  }),
  Markdown.configure({
    html: false,
    breaks: true,
    linkify: false,
    transformPastedText: true,
    transformCopiedText: true,
  }),
  Placeholder.configure({
    placeholder: "开始写作... 或在底部面板点 ⚡ 生成",
  }),
  CharacterCount.configure({
    limit: null,
  }),
  IssueHighlight,
];
```

- [ ] **Step 3: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Run all frontend tests (no regression)**

Run: `cd /Users/bugx/novelAI/web && npx vitest run 2>&1 | tail -5`
Expected: ALL pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/editor/tiptap/IssueHighlight.ts web/components/editor/extensions.ts
git commit -m "feat(m4a): TipTap IssueHighlight Mark extension"
```

---

## Task 9: ReviewButton + ReviewModal

**Files:**
- Create: `web/components/editor/ReviewButton.tsx`
- Create: `web/components/editor/ReviewModal.tsx`
- Create: `web/tests/ReviewButton.test.tsx`
- Create: `web/tests/ReviewModal.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `/Users/bugx/novelAI/web/tests/ReviewButton.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewButton } from "@/components/editor/ReviewButton";
import { useReviewStore } from "@/lib/store";
import type { ReviewResponse } from "@/lib/types";

const mockReviewResponse: ReviewResponse = {
  chapter_id: 5,
  issues: [
    { severity: "warn", category: "character", location: "x",
      description: "y", suggestion: "" },
  ],
  log_id: 1,
};

vi.mock("@/lib/api", () => ({
  api: {
    reviewChapter: vi.fn().mockResolvedValue(mockReviewResponse),
  },
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => vi.fn(),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ReviewButton", () => {
  beforeEach(() => {
    useReviewStore.setState({ issuesByChapter: {}, modalOpenFor: null });
  });

  it("renders idle text", () => {
    renderWithProviders(<ReviewButton chapterId={5} />);
    expect(screen.getByText(/审稿/)).toBeTruthy();
  });

  it("disables during reviewing state", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewButton chapterId={5} />);
    const button = screen.getByRole("button", { name: /审稿/ });
    await user.click(button);
    // After click, the button text changes briefly; let it settle
    await waitFor(() => {
      expect(useReviewStore.getState().issuesByChapter[5]).toBeDefined();
    });
    expect(useReviewStore.getState().issuesByChapter[5]).toHaveLength(1);
    expect(useReviewStore.getState().modalOpenFor).toBe(5);
  });
});
```

Create `/Users/bugx/novelAI/web/tests/ReviewModal.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewModal } from "@/components/editor/ReviewModal";
import { useReviewStore } from "@/lib/store";
import type { Issue } from "@/lib/types";

// Mock editor — we don't test TipTap internals here
const mockEditor = {
  commands: {
    unsetAllIssueHighlights: vi.fn(),
    setIssueHighlight: vi.fn(),
    setTextSelection: vi.fn(),
    scrollIntoView: vi.fn(),
  },
  getText: vi.fn().mockReturnValue("原文 content"),
  state: { doc: { descendants: vi.fn() } },
};

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => vi.fn(),
}));

const issues: Issue[] = [
  { severity: "error", category: "character", location: "原文",
    description: "人物不一致", suggestion: "改" },
  { severity: "warn", category: "plot", location: "",
    description: "节奏过快", suggestion: "" },
];

describe("ReviewModal", () => {
  beforeEach(() => {
    useReviewStore.setState({
      issuesByChapter: { 5: issues },
      modalOpenFor: 5,
    });
  });

  it("renders by category with severity icons", () => {
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    expect(screen.getByText(/人物一致性/)).toBeTruthy();
    expect(screen.getByText(/情节矛盾/)).toBeTruthy();
    expect(screen.getByText(/人物不一致/)).toBeTruthy();
    expect(screen.getByText(/节奏过快/)).toBeTruthy();
  });

  it("shows empty state when no issues", () => {
    useReviewStore.setState({
      issuesByChapter: { 5: [] },
      modalOpenFor: 5,
    });
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    expect(screen.getByText(/未发现问题/)).toBeTruthy();
  });

  it("close button calls closeModal", async () => {
    const user = userEvent.setup();
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    await user.click(screen.getByRole("button", { name: /我知道了/ }));
    expect(useReviewStore.getState().modalOpenFor).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/ReviewButton.test.tsx tests/ReviewModal.test.tsx 2>&1 | tail -10`
Expected: FAIL — components don't exist.

- [ ] **Step 3: Create ReviewButton.tsx**

Create `/Users/bugx/novelAI/web/components/editor/ReviewButton.tsx`:

```typescript
"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useReviewStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";

export function ReviewButton({ chapterId }: { chapterId: number }) {
  const toast = useToast();
  const setIssues = useReviewStore((s) => s.setIssues);
  const [state, setState] = useState<"idle" | "reviewing">("idle");

  const handleReview = async () => {
    setState("reviewing");
    try {
      const r = await api.reviewChapter(chapterId);
      setIssues(chapterId, r.issues);
      toast(`审稿完成：${r.issues.length} 条 Issue`, "success");
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${JSON.stringify(e.body)}`
        : (e as Error).message;
      toast(`审稿失败: ${msg}`, "error");
    } finally {
      setState("idle");
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleReview}
      disabled={state === "reviewing"}
    >
      {state === "reviewing" ? "⏳ 审稿中..." : "🔍 审稿"}
    </Button>
  );
}
```

- [ ] **Step 4: Create ReviewModal.tsx**

Create `/Users/bugx/novelAI/web/components/editor/ReviewModal.tsx`:

```typescript
"use client";

import { useEffect, useRef } from "react";
import type { Editor } from "@tiptap/react";
import { useReviewStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import type { Category, Issue, Severity } from "@/lib/types";

const CATEGORY_LABEL: Record<Category, string> = {
  character: "人物一致性",
  relationship: "关系合理性",
  plot: "情节矛盾",
  foreshadow: "伏笔完整性",
  worldview: "世界观一致性",
};

const CATEGORY_ORDER: Category[] = [
  "character", "relationship", "plot", "foreshadow", "worldview",
];

const SEVERITY_ICON: Record<Severity, string> = {
  error: "🔴",
  warn: "🟡",
  info: "🔵",
};

export function ReviewModal({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  const issues = useReviewStore((s) => s.issuesByChapter[chapterId] || []);
  const isOpen = useReviewStore((s) => s.modalOpenFor === chapterId);
  const close = useReviewStore((s) => s.closeModal);
  const toast = useToast();
  const editorRef = useRef(editor);
  editorRef.current = editor;

  // Apply highlights when issues change
  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;

    ed.commands.unsetAllIssueHighlights();

    if (!issues.length) return;

    const fullText = ed.getText();
    issues.forEach((issue, idx) => {
      if (!issue.location) return;
      const idxInText = fullText.indexOf(issue.location);
      if (idxInText < 0) return;  // graceful degrade
      // NOTE: text offset → ProseMirror pos conversion is approximate.
      // TipTap's getText() concatenates block nodes with newlines; the resulting
      // offset is close to but not exactly the ProseMirror document position.
      // For simple paragraph-based chapters this works well; complex block
      // structures (lists, blockquotes) may shift by a few positions.
      const from = idxInText + 1;  // ProseMirror is 1-indexed
      const to = from + issue.location.length;
      try {
        ed.commands.setIssueHighlight(
          { issueId: `${idx}`, severity: issue.severity },
          from, to,
        );
      } catch {
        // Position out of range; skip silently (graceful degrade)
      }
    });
  }, [issues]);

  if (!isOpen) return null;

  const byCategory = new Map<Category, Issue[]>();
  for (const cat of CATEGORY_ORDER) {
    const items = issues.filter((i) => i.category === cat);
    if (items.length) byCategory.set(cat, items);
  }

  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warnCount = issues.filter((i) => i.severity === "warn").length;
  const infoCount = issues.filter((i) => i.severity === "info").length;

  const handleIssueClick = (issueId: string) => {
    const ed = editorRef.current;
    if (!ed) return;
    let foundPos: number | null = null;
    ed.state.doc.descendants((node, pos) => {
      if (foundPos !== null) return false;
      const mark = node.marks.find((m) =>
        m.type.name === "issueHighlight" && m.attrs.issueId === issueId
      );
      if (mark) {
        foundPos = pos;
        return false;
      }
      return true;
    });
    if (foundPos !== null) {
      ed.commands.setTextSelection(foundPos);
      ed.commands.scrollIntoView();
    }
  };

  const handleCopyAll = () => {
    const text = issues.map((i) =>
      `[${SEVERITY_ICON[i.severity]} ${CATEGORY_LABEL[i.category]}]\n` +
      (i.location ? `位置：${i.location}\n` : "") +
      `问题：${i.description}\n` +
      (i.suggestion ? `建议：${i.suggestion}\n` : "")
    ).join("\n");
    navigator.clipboard.writeText(text).then(
      () => toast("已复制到剪贴板", "success"),
      () => toast("复制失败", "error"),
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-panel border border-line rounded max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">审稿报告</h2>
          <button onClick={close} className="text-text-muted hover:text-text">×</button>
        </div>

        <div className="p-4">
          {issues.length === 0 ? (
            <p className="text-text-muted">✓ 未发现问题</p>
          ) : (
            <>
              <div className="text-sm text-text-muted mb-4">
                共 {issues.length} 条 Issue：🔴 {errorCount} · 🟡 {warnCount} · 🔵 {infoCount}
              </div>
              {Array.from(byCategory.entries()).map(([cat, items]) => (
                <div key={cat} className="mb-4">
                  <h3 className="text-sm text-text-muted-bright mb-2">
                    ▼ {CATEGORY_LABEL[cat]}（{items.length}）
                  </h3>
                  <div className="space-y-2 pl-4">
                    {items.map((issue, idx) => {
                      const issueIdx = issues.indexOf(issue);
                      return (
                        <div
                          key={`${cat}-${idx}`}
                          onClick={() => handleIssueClick(`${issueIdx}`)}
                          className="border border-line rounded p-2 cursor-pointer hover:bg-hover"
                        >
                          <div className="flex items-start gap-2">
                            <span>{SEVERITY_ICON[issue.severity]}</span>
                            <div className="flex-1">
                              <div className="text-sm text-text">
                                {issue.description}
                              </div>
                              {issue.location && (
                                <div className="text-xs text-text-dim mt-1">
                                  位置："{issue.location}"
                                </div>
                              )}
                              {issue.suggestion && (
                                <div className="text-xs text-text-muted mt-1">
                                  建议：{issue.suggestion}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-line">
          <Button variant="ghost" onClick={handleCopyAll}>📋 复制全部</Button>
          <Button variant="primary" onClick={close}>✓ 我知道了</Button>
        </div>
      </div>
    </div>
  );
}
```

**Note:** The "↻ 重新审稿" button is intentionally omitted from the modal footer to keep the implementation simple. Users can re-trigger by clicking the ReviewButton in the toolbar again. This is a YAGNI simplification over the spec mockup.

- [ ] **Step 5: Run tests**

Run: `cd /Users/bugx/novelAI/web && npx vitest run tests/ReviewButton.test.tsx tests/ReviewModal.test.tsx`
Expected: ALL tests PASS.

If the ReviewButton test for "disables during reviewing state" flakes, the click handler runs async; waitFor should cover it. Adjust if needed.

- [ ] **Step 6: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/editor/ReviewButton.tsx web/components/editor/ReviewModal.tsx web/tests/ReviewButton.test.tsx web/tests/ReviewModal.test.tsx
git commit -m "feat(m4a): ReviewButton + ReviewModal components"
```

---

## Task 10: Mount ReviewButton + ReviewModal in ChapterEditor

**Files:**
- Modify: `web/components/editor/ChapterEditor.tsx`
- Create: `tests` (no new test; integration verified via E2E in Task 12)

- [ ] **Step 1: Read ChapterEditor.tsx**

Read `/Users/bugx/novelAI/web/components/editor/ChapterEditor.tsx` to understand the current structure. Find:
- Where `EditorToolbar` is rendered (with `extraActions` prop)
- Where `FinalizeButton` is passed (likely in `extraActions`)
- Where `editor` instance is available

- [ ] **Step 2: Add ReviewButton to extraActions and ReviewModal alongside editor**

In `/Users/bugx/novelAI/web/components/editor/ChapterEditor.tsx`:

1. Add imports at top:

```typescript
import { ReviewButton } from "./ReviewButton";
import { ReviewModal } from "./ReviewModal";
```

2. Find the `EditorToolbar` JSX and add `<ReviewButton chapterId={chapter.id} />` inside the `extraActions` slot, alongside `<FinalizeButton ...>`. For example, if current code is:

```tsx
<EditorToolbar
  editor={editor}
  title={chapter.title}
  charCount={charCount}
  onDelete={...}
  extraActions={<FinalizeButton chapterId={chapter.id} isFinal={chapter.status === "final"} />}
/>
```

Change to:

```tsx
<EditorToolbar
  editor={editor}
  title={chapter.title}
  charCount={charCount}
  onDelete={...}
  extraActions={
    <>
      <FinalizeButton chapterId={chapter.id} isFinal={chapter.status === "final"} />
      <ReviewButton chapterId={chapter.id} />
    </>
  }
/>
```

3. Find where `editor` is rendered (after `</EditorToolbar>` or wherever the editor JSX lives) and add `<ReviewModal chapterId={chapter.id} editor={editor} />` after it (as a sibling):

```tsx
<EditorContent editor={editor} />
<ReviewModal chapterId={chapter.id} editor={editor} />
```

4. Ensure the `editor` variable is accessible at the point where ReviewModal is rendered. If `editor` is null initially (TipTap initialization is async), the modal effect handles null gracefully (returns early).

- [ ] **Step 3: Run typecheck**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Run all frontend tests**

Run: `cd /Users/bugx/novelAI/web && npx vitest run 2>&1 | tail -5`
Expected: ALL pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/editor/ChapterEditor.tsx
git commit -m "feat(m4a): mount ReviewButton + ReviewModal in ChapterEditor"
```

---

## Task 11: Chapter switch cleanup (clearIssues)

**Files:**
- Modify: `web/app/projects/[projectId]/chapters/[chapterId]/page.tsx` or equivalent chapter switch handler

- [ ] **Step 1: Find chapter switch handler**

Search for the chapter selection logic in the chapters page. Likely at `/Users/bugx/novelAI/web/app/projects/[projectId]/chapters/[chapterId]/page.tsx` or in a SidePanel component.

Run: `grep -rn "setSelectedChapter\|chapterId\|router.push.*chapter" web/app/projects/\[projectId\]/chapters/ web/components/ | head -10`

- [ ] **Step 2: Add clearIssues on switch**

In the chapter switch handler (or in a `useEffect` keyed on chapterId in ChapterEditor), call `useReviewStore.getState().clearIssues(oldChapterId)` when leaving a chapter.

The simplest implementation is a `useEffect` in `ChapterEditor`:

```typescript
import { useReviewStore } from "@/lib/store";

// Inside ChapterEditor component:
const clearIssues = useReviewStore((s) => s.clearIssues);
const prevChapterIdRef = useRef<number | null>(null);
useEffect(() => {
  const prev = prevChapterIdRef.current;
  if (prev !== null && prev !== chapter.id) {
    clearIssues(prev);
  }
  prevChapterIdRef.current = chapter.id;
}, [chapter.id, clearIssues]);
```

Place this near the top of the component, alongside other hooks.

- [ ] **Step 3: Run typecheck + tests**

Run: `cd /Users/bugx/novelAI/web && npx tsc --noEmit && npx vitest run 2>&1 | tail -5`
Expected: 0 errors; all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/components/editor/ChapterEditor.tsx
git commit -m "feat(m4a): clear review issues on chapter switch"
```

---

## Task 12: E2E test

**Files:**
- Create: `web/tests/e2e/review-highlight.spec.ts`

- [ ] **Step 1: Write the E2E test**

Create `/Users/bugx/novelAI/web/tests/e2e/review-highlight.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test("review → modal shows issues → close clears", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + chapter via API
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M4a" },
  }).then((r) => r.json());
  const pid = project.id;

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid, order_index: 1, title: "第一章",
      content: "李雷推开了残月酒馆的门，看见了韩梅。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock review endpoint
  await page.route(`**/api/chapters/${chId}/review`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId,
        log_id: 999,
        issues: [
          {
            severity: "warn",
            category: "character",
            location: "李雷推开了残月酒馆的门",
            description: "李雷本章状态突变",
            suggestion: "补充心理转变",
          },
          {
            severity: "info",
            category: "plot",
            location: "",
            description: "整章节奏过快",
            suggestion: "",
          },
        ],
      }),
    });
  });

  // 3. Navigate to chapter editor
  await page.goto(`/projects/${pid}/chapters/${chId}`);

  // 4. Click review button
  await page.getByRole("button", { name: /🔍 审稿/ }).click();

  // 5. Wait for modal
  await expect(page.getByText(/审稿报告/)).toBeVisible({ timeout: 10_000 });

  // 6. Verify issues by category
  await expect(page.getByText(/人物一致性/)).toBeVisible();
  await expect(page.getByText(/情节矛盾/)).toBeVisible();
  await expect(page.getByText(/李雷本章状态突变/)).toBeVisible();
  await expect(page.getByText(/整章节奏过快/)).toBeVisible();

  // 7. Verify highlight applied in editor (mark element with data-issue-id)
  // The first issue has location "李雷推开了残月酒馆的门" which is in the chapter content
  const highlightedMarks = page.locator("mark[data-issue-id]");
  await expect(highlightedMarks.first()).toBeVisible({ timeout: 5_000 });

  // 8. Close modal
  await page.getByRole("button", { name: /我知道了/ }).click();
  await expect(page.getByText(/审稿报告/)).toBeHidden();
});
```

- [ ] **Step 2: Start backend + frontend if not running**

- Backend: `cd /Users/bugx/novelAI && uv run uvicorn app.main:app --port 8005 --reload`
- Frontend: `cd /Users/bugx/novelAI/web && npm run dev`

- [ ] **Step 3: Run the E2E test**

Run: `cd /Users/bugx/novelAI/web && npx playwright test tests/e2e/review-highlight.spec.ts`
Expected: PASS.

If the highlight check (`mark[data-issue-id]`) fails, the text offset → ProseMirror pos conversion may not have hit the right spot. Adjust by:
- Verifying the `editor.getText()` output during the test (add a `console.log` temporarily)
- If conversion is off, document the limitation in the commit message; the modal still works (issues display correctly), highlight is best-effort

- [ ] **Step 4: Commit**

```bash
cd /Users/bugx/novelAI
git add web/tests/e2e/review-highlight.spec.ts
git commit -m "test(m4a): e2e review → modal → close flow"
```

---

## Task 13: Full regression + memory update

**Files:** None (verification only, except memory file)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/bugx/novelAI && uv run pytest 2>&1 | tail -5`
Expected: ALL pass.

- [ ] **Step 2: Run full frontend test suite**

Run: `cd /Users/bugx/novelAI/web && npx vitest run 2>&1 | tail -5`
Expected: ALL pass.

- [ ] **Step 3: Run all E2E**

Run: `cd /Users/bugx/novelAI/web && npx playwright test 2>&1 | tail -10`
Expected: ALL pass (existing 8 + new 1 = 9 total).

- [ ] **Step 4: Verify generation_logs has reviewer entry**

After running the E2E test (which seeded a chapter), check:
```bash
sqlite3 data/novelai.db "SELECT id, model_task, status FROM generation_logs WHERE model_task='reviewer' ORDER BY id DESC LIMIT 3;"
```
Expected: at least 1 row with `model_task='reviewer'` and `status='done'`.

- [ ] **Step 5: Update memory file**

Update `/Users/bugx/.claude/projects/-Users-bugx-novelAI/memory/novelai-m2b-status.md`:
- Add M4a to the 完成 section with date 2026-06-21
- Brief description: Reviewer Agent + 5 维度合并 LLM 调用 + POST /api/chapters/{id}/review + Modal + TipTap IssueHighlight Mark + assemble_review_context + generation_logs 审计
- Mention test counts
- Update "下一步" — M4a done; remaining: M4b (Discuss), M3c-D (plot_lines), M4+ polish

Update `/Users/bugx/.claude/projects/-Users-bugx-novelAI/memory/MEMORY.md` index line accordingly.

- [ ] **Step 6: Final commit if any cleanup needed**

```bash
cd /Users/bugx/novelAI
git status
# Memory files live in ~/.claude/, not in repo. Working tree should be clean.
```

---

## Self-Review Notes

**Spec coverage:**
- §1.1 (7 goals): Task 1 (schemas), Task 2 (retrieval), Tasks 3-4 (agent + prompts), Task 5 (API), Task 9 (Modal), Task 8 (TipTap highlight), Task 4 (audit) — all covered
- §3 Pydantic: Task 1 — covered
- §4 retrieval: Task 2 — covered
- §5 reviewer agent: Task 4 — covered
- §6 prompts: Task 3 — covered
- §7 API: Task 5 — covered
- §8.1 ReviewButton: Task 9 — covered
- §8.2 store: Task 7 — covered
- §8.3 TipTap Mark: Task 8 — covered
- §8.4 highlight logic: Task 9 (in ReviewModal effect) — covered
- §8.5 ReviewModal: Task 9 — covered
- §8.6 click-to-scroll: Task 9 — covered
- §9 tests: All tasks have tests
- §10 acceptance: Task 13

**Type consistency:**
- `Issue` (Pydantic) ↔ `Issue` (TS) — field names match (severity/category/location/description/suggestion)
- `ReviewResponse.chapter_id` / `issues` / `log_id` — consistent across Pydantic + TS + API
- `useReviewStore` API (`setIssues` / `openModal` / `closeModal` / `clearIssues`) — used consistently in ReviewButton + ReviewModal + ChapterEditor
- TipTap Mark name `issueHighlight` consistent in extension + ReviewModal reference

**Known compromises:**
- "↻ 重新审稿" button omitted from modal footer (YAGNI; users re-click toolbar button)
- TipTap text offset → ProseMirror pos conversion is approximate (Task 9 §step 4 documents this); complex block structures may shift
- Chapter switch cleanup uses useEffect ref pattern (Task 11); may miss edge cases if chapter prop changes via unusual paths

**Open follow-ups (M4+):**
- ContextBudget auto-trim for chapter 50+ (token overflow → 502 today)
- Multi-match handling (location appears multiple times → only first highlighted)
- Stale highlight detection (chapter edited after review → highlights may point to changed text)
