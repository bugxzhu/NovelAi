# NovelAI M3c-C — 伏笔标注（events + foreshadows）设计文档

- **日期**：2026-06-21
- **状态**：草案（待用户审阅）
- **范围**：M3c-C = events 时序表 + Extractor 抽取章节显著事件（硬事实）+ 用户手动标 foreshadows 跨章链接 + 事件管理页 + 孤儿伏笔视图
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要 + 硬事实）、M3b（向量检索）、M3c-A（relationships，已验证单向存储模式）、M3c-B（character_states，已验证时序+accept 模式）已完成

> M3c 拆分为 4 个独立子项目（A 关系演变 ✅ / B 人物状态时序 ✅ / **C 伏笔标注** / D plot_lines）。本文档仅覆盖 **C**。

---

## 1. 目标与非目标

### 1.1 目标

让 AI/用户能记录章节里的"显著事件"，并标注事件间的伏笔/兑现关系，为 M4 Reviewer 的"伏笔完整性"维度提供数据基础：

1. Extractor 在 finalize 时抽取本章透露的**显著事件**作为硬事实（`update_type='hard_fact'`, `auto=true`）
2. 抽取结果写入 `pending_updates` 队列，用户 accept 后入 events 表
3. 用户在 `/events` 页面：手动 CRUD 事件 + 通过多选下拉标 foreshadows 跨章链接
4. 派生 `payoff_of` 视图（不存字段，API 计算）
5. "未兑现伏笔"过滤视图：高亮 foreshadows 数组里有 event_id 没被任何事件兑现的事件
6. 删除事件时清理所有指向它的 foreshadows 悬挂引用

### 1.2 非目标（M3c-C 不做）

- 自动抽取 foreshadows 链接（LLM 跨章推理不可靠；链接由用户标；M4 Reviewer 才是自动检测合适场景）
- 伏笔拓扑可视化（→ M4+）
- 检测"无铺垫爆发"（→ M4 Reviewer）
- 接入 Writer 常驻层（events 不进 prompt；M3b 向量检索已能召回相关场景）
- plot_lines 状态流转 — M3c-D
- 异步抽取 — M3e
- LLM 真实 API 集成测试 — 全部 mock

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 双向引用存储 | **单向（仅 foreshadows）+ API 派生 payoff_of** | 单一数据源；无双写同步 bug；foreshadows 主动语态清晰 |
| 抽取触发 | Extractor 抽事件本身（hard_fact, auto=true）；用户手动标 foreshadows 链接 | 事件是客观发生（硬事实）；跨章链接 LLM 不可靠 |
| 事件粒度 | 一章 0..N 个事件 | 用户/LLM 自由判断"显著" |
| 事件 append-only | 无 version-switch（不像 relationships）；无 upsert（不像 character_states 同章去重） | 事件是独立事实，不"演变"；同章多事件是合法且常见的 |
| plot_line_id | nullable INT 预留 | M3c-D 不做但 schema 不动；前向兼容 |
| UI 范围 | **选项 2**：CRUD + foreshadow multiselect + 孤儿伏笔过滤 | 选项 1 太薄（JSON 输入）；选项 3 留给 M4 |
| PendingUpdateItem 卡片 | 🎯 新事件分支（同 M3a 硬事实风格） | 用户在 pending 面板预览抽取结果 |
| ActivityBar | 🎯 第 9 图标（events） | 与 chapters/characters/relationships/lore/pending 平级 |
| retrieval 接入 | **不接入**（events 不进常驻层） | 常驻层 token 已紧；events 非写作必需；M3b 向量检索够用 |
| 字段必填性 | title/description 必填；其余可选 | 最少字段保证可识别 |
| 涉及人物/地点容错 | 名字解析失败 → 跳过该项但 event 仍生成 | 事件本身比其关联更重要；不能因 LLM 漏名字废掉整条 |
| 删除事件级联清理 | DELETE → 扫描全项目 events.foreshadows 移除引用 | 防止悬挂引用 |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   └── schema.py                       # 修改：加 Event ORM
├── agents/
│   └── extractor.py                    # 修改：_build_pending_rows 加 events 分支
├── llm/prompts/extractor/
│   ├── system.j2                       # 修改：加 events JSON schema + 抽取规则
│   └── user.j2                         # 不变
├── api/
│   ├── pending_updates.py              # 修改：_derive_summary_fields + accept 加 events 分支
│   └── events.py                       # 新增：CRUD + filter + payoff-of 端点
├── main.py                             # 修改：注册 events router
└── models/
    └── event.py                        # 新增：EventRead + EventCreate + EventUpdate

alembic/versions/
└── <hash>_add_events.py                # 新增

web/
├── app/projects/[projectId]/
│   └── events/page.tsx                 # 新增：事件管理页
├── components/
│   ├── layout/ActivityBar.tsx          # 修改：加 🎯 第 9 图标
│   └── entities/
│       ├── PendingUpdateItem.tsx       # 修改：🎯 事件卡片分支
│       ├── EventForm.tsx               # 新增：手动建/编辑事件表单
│       ├── EventList.tsx               # 新增：列表 + 过滤标签
│       └── ForeshadowMultiselect.tsx   # 新增：foreshadows 字段多选下拉
└── lib/
    ├── api.ts                          # 修改：加 events 端点
    ├── queries.ts                      # 修改：useEvents 等 hooks
    └── types.ts                        # 修改：加 Event 类型

tests/                                  # 后端
├── test_event_schema.py                # 新增
├── test_extractor_events.py            # 新增
├── test_pending_updates.py             # 修改：events accept
└── test_events_api.py                  # 新增

web/tests/                              # 前端
├── PendingUpdateItem.test.tsx          # 修改
├── EventForm.test.tsx                  # 新增
├── ForeshadowMultiselect.test.tsx      # 新增
└── e2e/finalize-event.spec.ts          # 新增
```

### 2.1 职责边界

- `agents/extractor.py`：M3a/M3c-B/M3c-A 既有 + 新增 `_build_pending_rows` 的 events 分支。原子事务不变。
- `api/pending_updates.py`：M3a/M3c-B/M3c-A 既有 + 新增 accept handler 的 `target_table='events'` 分支。
- `api/events.py`：CRUD + filter + payoff-of 派生视图。删除时清理悬挂 foreshadows 引用。
- `EventForm.tsx`：手动新建/编辑事件。debounce 自动保存（与 CharacterForm/RelationshipForm 同模式）。
- `ForeshadowMultiselect.tsx`：核心组件。处理 foreshadows 字段的双向显示（可编辑正向，只读反向）。
- `EventList.tsx`：列表 + 4 个过滤标签（全部/未兑现/已兑现/无伏笔链接）。

### 2.2 依赖方向

沿用 M2a/M3a/M3b/M3c-B/M3c-A 单向依赖：`api → agents → memory → llm → DB`。

---

## 3. 数据库变更

### 3.1 新增表：`events`

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,

  project_id  INTEGER NOT NULL REFERENCES projects(id)  ON DELETE CASCADE,
  chapter_id  INTEGER NOT NULL REFERENCES chapters(id)  ON DELETE CASCADE,

  title        TEXT NOT NULL,
  description  TEXT NOT NULL,

  involved_characters  JSON NOT NULL DEFAULT '[]',   -- [character.id, ...]
  location_id          INTEGER,                       -- nullable; lore_entries.id (type=location)
  plot_line_id         INTEGER,                       -- nullable; M3c-D 预留，不加 FK

  foreshadows  JSON NOT NULL DEFAULT '[]',            -- [event.id, ...] 单向存储

  extractor_log_id    INTEGER,                        -- 关联 generation_logs（审计）
  pending_update_id   INTEGER,                        -- 反向追溯 accept 来源（手动建为 null）

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX idx_events_project  ON events(project_id, chapter_id);
CREATE INDEX idx_events_chapter  ON events(chapter_id);
-- foreshadows JSON 数组查询靠 json_each()，无需专门索引（数据量小）
```

**字段说明：**

| 字段 | 用途 |
|---|---|
| `title` | ≤20 字简明概括，用于 UI 列表/下拉显示 |
| `description` | 1-3 句话客观叙述 |
| `involved_characters` | JSON 数组 `[character.id, ...]`；可为空 |
| `location_id` | nullable；指向 `lore_entries.id` (type=location)；不加 FK（lore 删除时此字段置空由应用层处理） |
| `plot_line_id` | nullable；M3c-D 预留；M3c-C 不读不写 |
| `foreshadows` | JSON 数组 `[event.id, ...]`；单向存储，反向通过 API 派生 |
| `extractor_log_id` / `pending_update_id` | 审计字段（手动建两者皆 null） |

**`payoff_of` 不存字段**——API 层计算：

```python
# 对事件 E：
# payoff_of = SELECT id FROM events WHERE E.id IN (SELECT value FROM json_each(events.foreshadows))
```

### 3.2 Alembic 迁移

```python
# alembic/versions/<hash>_add_events.py
"""add events

Revision ID: <hash>
Revises: 716543ecde93   # M3c-A 的 relationships
Create Date: 2026-06-21 ...
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('involved_characters', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('plot_line_id', sa.Integer(), nullable=True),
        sa.Column('foreshadows', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_events_project', 'events',
                    ['project_id', 'chapter_id'], unique=False)
    op.create_index('idx_events_chapter', 'events',
                    ['chapter_id'], unique=False)


def downgrade():
    op.drop_index('idx_events_chapter', table_name='events')
    op.drop_index('idx_events_project', table_name='events')
    op.drop_table('events')
```

**down_revision = `'716543ecde93'`**（M3c-A 的 relationships 迁移）。

**无数据迁移**（新表）。

### 3.3 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| `location_id` 不加 FK 约束 | lore 删除时此字段置空（应用层处理） | 与现有 chapter.last_location_id 同模式（M2a 已用） |
| `plot_line_id` 不加 FK | M3c-D 未做 | 预留字段，M3c-C 完全不读不写 |
| `involved_characters` / `foreshadows` 用 JSON 数组 | 与 personality/tags/affiliations 一致 | M1 已有模式 |
| 无 UNIQUE 约束 | 同章可多条独立事件 | 事件是独立事实，无"同一事件"概念 |
| 无 version-switch | append-only | 事件不"演变"（不像 relationships） |
| 无 upsert | 同 (chapter, title) 允许多条 | 同名事件可能在不同语境发生；强制去重弊大于利 |

---

## 4. Extractor Agent 改造

### 4.1 Prompt 改造（方案 A：扩展现有调用）

**`extractor/system.j2` 修改一：JSON 输出格式扩展**

在 `relationship_changes` 同级加 `events` 数组：

```
{
  "summary": "...",
  "entities": { ... },
  "state_changes": [ ... ],
  "relationship_changes": [ ... ],
  "events": [
    {
      "title": "事件名（≤20 字）",
      "description": "事件描述（1-3 句话）",
      "involved_character_names": ["人物名", ...],
      "location_name": "地点名"
    }
  ]
}
```

更新"不要省略字段"行加上 events：

```
如果某类抽取为空，对应数组返回空 []。永远不要省略字段（包括 state_changes、relationship_changes 和 events）。
```

**`extractor/system.j2` 修改二：新增节（接 relationship_changes 准则末尾）**

```
# 硬事实：章节事件（events）

抽取本章发生的**显著事件**——能影响后续情节走向的关键节点。

## 何时抽
本章发生且符合以下任一：
- 人物关系发生重大变化（结盟/决裂/背叛/相认）
- 关键物品/能力/秘密被揭示或获得
- 重要战斗/死亡/受伤/转折
- 角色做出影响后续的决定
- 揭示世界观的重大信息

## 不抽
- 日常对话、场景过渡、纯描写段落
- 同一事件的多个细节（抽一条主事件即可）

## 字段要求
- `title`：≤20 字，简明概括（如"残月酒馆伏击"、"李雷获得玄铁剑"）
- `description`：1-3 句话，第三人称客观叙述
- `involved_character_names`：人物名数组（必须已在人物库；空数组表示无具体人物参与，如"地震发生"）
- `location_name`：地点名（必须已在 lore_entries 中 type=location；不填表示无明确地点）

## 不要标 foreshadows 链接
跨章伏笔/呼应关系由用户在事件管理页手动标注——LLM 跨章推理不可靠。
```

**`extractor/user.j2` 不变**——events 抽取不需要 existing 上下文（不像 relationships 需要"现有关系"避免重复）。

### 4.2 LLM 响应格式扩展

```json
{
  "summary": "...",
  "entities": { ... },
  "state_changes": [ ... ],
  "relationship_changes": [ ... ],
  "events": [
    {
      "title": "残月酒馆伏击",
      "description": "韩梅在残月酒馆设伏袭击李雷，致其左臂中刀负伤逃离。",
      "involved_character_names": ["李雷", "韩梅"],
      "location_name": "残月酒馆"
    }
  ]
}
```

**容错处理：**

- 缺 `events` 字段 → 当作空数组
- `title` 或 `description` 为空 → 跳过该条
- `involved_character_names` 含不存在的名字 → 跳过该项名字但 event 仍生成（不像 state_changes 整条跳过）
- `location_name` 不存在 → `location_id=None`，event 仍生成
- `involved_character_names` / `location_name` 缺失 → 当作空数组/空字符串

### 4.3 `_build_pending_rows` 加 events 分支

```python
existing_by_name = {c.name: c for c in existing_characters}
location_by_name = {l.name: l for l in existing_lore if l.type == "location"}

# ... M3a 4 类 + M3c-B state_changes + M3c-A relationship_changes ...

# M3c-C: events → hard_fact pending (target_table='events')
# Append-only (no version switch, no upsert). Foreshadow links added by user post-accept.
for ev in (events or []):
    title = (ev.get("title") or "").strip()
    description = (ev.get("description") or "").strip()
    if not title or not description:
        logger.info(
            "extractor: skipping event — empty title/description "
            "(chapter_id=%s); entry=%r", chapter_id, ev,
        )
        continue

    # Resolve involved character names → IDs (tolerate unknown names)
    involved_ids: list[int] = []
    for name in (ev.get("involved_character_names") or []):
        n = (name or "").strip()
        if not n:
            continue
        c = char_by_name.get(n)
        if c is not None:
            involved_ids.append(c.id)
        else:
            logger.info(
                "extractor: event %r — unknown character %r skipped "
                "(chapter_id=%s)", title, n, chapter_id,
            )

    # Resolve location name → ID (tolerate unknown)
    loc_name = (ev.get("location_name") or "").strip()
    location_id: int | None = None
    if loc_name:
        loc = location_by_name.get(loc_name)
        if loc is not None:
            location_id = loc.id
        else:
            logger.info(
                "extractor: event %r — unknown location %r skipped "
                "(chapter_id=%s)", title, loc_name, chapter_id,
            )

    # UI-friendly names mirror (accept handler ignores these, reads IDs only)
    involved_names = [existing_by_name[i].name for i in involved_ids]

    rows.append(PendingUpdate(
        project_id=project_id, chapter_id=chapter_id,
        update_type="hard_fact", operation="create",
        target_table="events", target_id=None,
        proposed_change={
            "title": title,
            "description": description,
            "involved_character_ids": involved_ids,
            "involved_character_names": involved_names,
            "location_id": location_id,
            "location_name": loc_name if location_id else "",
        },
        reason="",
        auto=True,  # 硬事实
        extractor_model=model_name,
        status="pending",
    ))
```

**关键决策：**

- `auto=True`：硬事实与 M3a new_characters/new_lore 同类（pending_updates 表仍走，用户可 reject）
- 容错粒度：单条 event 内的"未知人物/地点"被跳过；不像 state_changes 整条跳过——因为事件本身比关联更重要
- `involved_character_names` / `location_name` 写入 proposed_change 仅用于 UI 显示（PendingUpdateItem 卡片预览），accept handler 不读这些字段，只读 IDs

### 4.4 generation_logs 审计

不变。抽取调用仍记一条 `generation_logs`，prompt 含新增的 events 规则。

---

## 5. API 契约

### 5.1 端点列表

```
# pending_updates（修改）
POST   /api/pending-updates/{id}/accept                # 加 events 分支

# events（新增）
GET    /api/events?project_id=X[&chapter_id=Y][&filter=all|unpaid|paid]
GET    /api/events/{id}
POST   /api/events                                     # 手动新建
PATCH  /api/events/{id}                                # 编辑（含 foreshadows 链接）
DELETE /api/events/{id}                                # 删除（级联清理悬挂引用）
```

### 5.2 Accept Handler 新分支

`POST /api/pending-updates/{id}/accept` 在 character_states/relationships 分支后追加：

```python
elif p.target_table == "events":
    # M3c-C: append-only event (no version switch, no upsert)
    data = p.proposed_change or {}
    title = data.get("title", "")
    description = data.get("description", "")
    if not title or not description:
        raise HTTPException(500, "events pending missing title/description")

    # Validate location_id (if specified)
    location_id = data.get("location_id")
    if location_id is not None:
        loc = db.get(LoreEntry, location_id)
        if loc is None or loc.type != "location":
            raise HTTPException(500, "target location gone or not a location")

    # Filter involved_character_ids (drop deleted chars)
    raw_involved = data.get("involved_character_ids") or []
    involved_ids = [i for i in raw_involved if db.get(Character, i) is not None]

    event = Event(
        project_id=p.project_id,
        chapter_id=p.chapter_id,
        title=title,
        description=description,
        involved_characters=involved_ids,
        location_id=location_id,
        foreshadows=[],  # Extractor doesn't emit links; user adds them post-accept
        extractor_log_id=p.extractor_log_id,
        pending_update_id=p.id,
    )
    db.add(event)
```

**事务保证：** INSERT event + UPDATE pending.status 同一事务；任一失败回滚。

**响应：** 200 + `PendingUpdateRead`（status='accepted'）

**错误码：**
- 404 pending 不存在
- 409 已 accept/reject 过
- 500 title/description 缺失 / location 不存在或非 location 类型

### 5.3 `_derive_summary_fields` 扩展

`target_table="events"` 时：

```python
elif target_table == "events":
    entity_type = ""
    entity_name = proposed_change.get("title", "")
    field_name = ""
    old_value = ""
    # Show description, optionally prefixed with involved characters/location
    desc = proposed_change.get("description", "")
    names = proposed_change.get("involved_character_names") or []
    loc = proposed_change.get("location_name") or ""
    prefix_parts = []
    if names:
        prefix_parts.append("、".join(names))
    if loc:
        prefix_parts.append(f"@{loc}")
    prefix = f"[{' | '.join(prefix_parts)}] " if prefix_parts else ""
    proposed_value = f"{prefix}{desc}"
```

### 5.4 `GET /api/events`

```
GET /api/events?project_id=1&chapter_id=5&filter=all&limit=200
```

| Query | 默认 | 说明 |
|---|---|---|
| `project_id` | 必填 | 项目隔离 |
| `chapter_id` | 可选 | 按章节过滤 |
| `filter` | `all` | `all` / `unpaid` / `paid` |
| `limit` | 200 | 最大 500（`Query(le=500)`，对齐 M3c-A relationships 风格） |
| `offset` | 0 | 分页 |

**响应：** `list[EventRead]`

```python
class EventRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    chapter_id: int
    chapter_title: str          # JOIN chapters.title
    chapter_order: int          # JOIN chapters.order_index
    title: str
    description: str
    involved_characters: list[int]   # [character.id, ...]
    involved_character_names: list[str]  # JOIN-derived, UI-friendly
    location_id: int | None
    location_name: str          # JOIN-derived if location_id set, else ""
    plot_line_id: int | None    # always None in M3c-C
    foreshadows: list[int]      # [event.id, ...] this event foreshadows
    payoff_of: list[int]        # derived: [event.id, ...] that foreshadow this event
    payoff_of_titles: list[str] # derived, UI-friendly
    extractor_log_id: int | None
    pending_update_id: int | None
```

**filter 实现：**

```python
# All events for project
all_events = list(db.scalars(select(Event).where(Event.project_id == project_id)))

# Build reverse map: event_id → set of events that foreshadow it
payoff_map: dict[int, list[int]] = {}
for e in all_events:
    for target_id in (e.foreshadows or []):
        payoff_map.setdefault(target_id, []).append(e.id)

# Apply filter
if filter == "unpaid":
    # Events that foreshadow at least one event, AND at least one of those targets has no payoff
    result = [
        e for e in all_events
        if e.foreshadows and any(
            not payoff_map.get(target_id) for target_id in e.foreshadows
        )
    ]
elif filter == "paid":
    # Events that foreshadow at least one event, AND all targets have payoff
    result = [
        e for e in all_events
        if e.foreshadows and all(
            payoff_map.get(target_id) for target_id in e.foreshadows
        )
    ]
else:  # all
    result = all_events
```

排序：按 `chapter_order` asc, `id` asc（故事发展顺序）。

### 5.5 `POST /api/events`（手动新建）

```python
class EventCreate(BaseModel):
    project_id: int
    chapter_id: int
    title: str
    description: str
    involved_characters: list[int] = []   # character IDs
    location_id: int | None = None
    foreshadows: list[int] = []           # event IDs (can be set at creation)
```

**逻辑：**
- 校验 project/chapter 存在
- 校验 involved_characters 都存在
- 校验 location_id 存在且 type=location（如果指定）
- 校验 foreshadows 里的 event_id 都存在（如果指定）
- 立即落库（不经过 pending_updates）

**响应：** 201 + `EventRead`

### 5.6 `PATCH /api/events/{id}`

```python
class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    involved_characters: list[int] | None = None
    location_id: int | None = None
    foreshadows: list[int] | None = None
    # chapter_id / project_id 不可改（事件归属固定）
    # plot_line_id M3c-C 不允许改
```

**foreshadows PATCH 语义：** 整个数组替换（前端发完整新数组）。如当前 `[1, 2]`，用户加 3，PATCH `foreshadows: [1, 2, 3]`。

**校验：** foreshadows 里的 event_id 必须存在；不能自指（不能 foreshadows 自己）。

### 5.7 `DELETE /api/events/{id}`

**级联清理：** 删除 event X 前，扫描所有 events 的 foreshadows JSON 数组，移除 X 的引用：

```python
# Find all events referencing X in their foreshadows
 referencing = list(db.execute(
     select(Event).where(
         Event.project_id == project_id,
         text(f":x_id IN (SELECT value FROM json_each(events.foreshadows))")
     ).params(x_id=x_id)
 ))
 for r in referencing:
     r.foreshadows = [i for i in (r.foreshadows or []) if i != x_id]

 db.delete(x)
 db.commit()
```

**响应：** 204

### 5.8 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 手动新建立即落库 | 不走 pending | 用户主动操作；不重复审 |
| PATCH foreshadows 全数组替换 | 不增量加/减 | 简单；前端发完整状态；幂等 |
| DELETE 级联清理 foreshadows | 应用层扫全项目 | 防悬挂引用；数据量小 |
| `payoff_of` 不存字段 | API 派生 | 单向存储不变式 |
| `payoff_of_titles` 写入响应 | UI 友好 | 避免前端 N+1 |
| `involved_character_names` JOIN 进响应 | UI 友好 | 同上 |
| filter 在 API 层而非 SQL 层 | 派生字段需 Python 计算 | 数据量小（单项目通常 <500 事件），可接受 |

---

## 6. 前端 UI 与数据流

### 6.1 ActivityBar 加 🎯 第 9 图标

```typescript
const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters", view: "chapters" as const },
  { icon: "👥", label: "人物", path: "characters", view: "characters" as const },
  { icon: "🤝", label: "关系", path: "relationships", view: "relationships" as const },
  { icon: "🎯", label: "事件", path: "events", view: "events" as const },   // 新增
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
  { icon: "📜", label: "历史", path: "history", view: "history" as const },
  { icon: "📋", label: "待处理", path: "pending", view: "pending" as const },
  { icon: "🔍", label: "搜索", path: "search", view: "search" as const },
];
```

### 6.2 `/events` 页面（ChapterWorkspaceGrid 布局）

```
┌──────────────────────────────────────────────────────────────────┐
│🎯│  事件 (12)                  [全部 ▾] [+ 新建]                  │
│  │──────────────────────────────────────────────────────────────│
│🏠│  第 1 章 · 残月重逢                                            │
│📚│  ┌────────────────────────────────────────────────────────┐ │
│👥│  │ 🎯 残月酒馆相遇（未兑现伏笔 ⚠️）                          │ │  ← 左侧列表
│🤝│  │   李雷、韩梅 · 残月酒馆                                   │ │
│🎯│  └────────────────────────────────────────────────────────┘ │
│🌍│  第 2 章 · 入城                                              │
│📜│  ┌────────────────────────────────────────────────────────┐ │
│📋│  │ 🎯 城门冲突（已兑现 ✓）                                   │ │
│🔍│  └────────────────────────────────────────────────────────┘ │
│🌙│                                                              │
│  │  ─── 右侧：选中事件 ───                                      │
│  │  编辑事件：残月酒馆相遇                                       │  ← EventForm
│  │  标题：[残月酒馆相遇]                                         │
│  │  描述：[李雷在残月酒馆与韩梅重逢...]                          │
│  │  涉及人物：[李雷] [韩梅] +                                    │
│  │  地点：[残月酒馆 ▾]                                          │
│  │                                                              │
│  │  ▼ 伏笔链接                                                  │  ← ForeshadowMultiselect
│  │  此事件是以下事件的伏笔：                                     │
│  │  [城门冲突 ✗]  [真相揭露 ✗]                                  │
│  │  + 添加目标事件                                              │
│  │                                                              │
│  │  此事件兑现了以下伏笔：                                       │  ← 只读，派生
│  │  （无）                                                      │
│  └──────────────────────────────────────────────────────────────┘
```

### 6.3 PendingUpdateItem 事件卡片

```typescript
const isEvent = pending.target_table === "events";
if (isEvent) {
  icon = "🎯";
  headerLabel = `新事件 · ${pending.entity_name}`;
  // 内容：proposed_value = description（单行）；UI 隐含显示涉及人物/地点（已在 proposed_value 前缀）
}
```

与 state_changes / relationships 同模式：单行 proposed_value，无 旧值/新值 diff。

### 6.4 EventForm（手动新建/编辑）

- title 输入
- description textarea
- 涉及人物：Chip 多选（项目内人物）
- 地点：下拉（项目内 type=location 的 lore）
- 编辑模式：禁用 chapter_id（与 RelationshipForm 同模式）
- 新建模式：chapter_id 必填（默认从 URL query 或当前选中章）
- 保存：debounce 自动保存（与 CharacterForm/RelationshipForm 同模式）

### 6.5 ForeshadowMultiselect（核心组件）

**输入：** 当前 event_id、项目内全部 events 列表
**输出：** `number[]`（选中的目标 event_id 数组）

**UI 结构：**

```
▼ 伏笔链接

此事件是以下事件的伏笔：
  [第 5 章 · 城门冲突 ✗]  [第 8 章 · 真相揭露 ✗]
  [+ 添加目标事件]  ← 触发下拉搜索

此事件兑现了以下伏笔：  ← 只读，派生自其他事件的 foreshadows
  [第 2 章 · 神秘预言]  ← 来自 event #5 的 foreshadows 含当前 event
```

**交互：**
- 点 ✗ 移除：PATCH 当前事件 foreshadows（去掉该 id）
- 点 + 添加：弹出搜索下拉，按章节分组，选中后 PATCH foreshadows（加上该 id）
- 反向 payoff_of 区域只读（数据来自 EventRead.payoff_of 字段）

### 6.6 过滤标签（EventList 顶部）

- `全部 (12)` / `未兑现伏笔 ⚠️ (3)` / `已兑现 ✓ (5)` / `无伏笔链接 (4)`
- 默认显示"全部"
- 切换时调 `?filter=unpaid` 等
- 视觉：未兑现的 event 卡片左侧加 ⚠️ 图标

### 6.7 hooks

```typescript
// lib/queries.ts 新增
export function useEvents(projectId: number, opts?: { chapterId?: number; filter?: "all" | "unpaid" | "paid" }) {
  return useQuery({
    queryKey: ["events", projectId, opts?.chapterId, opts?.filter ?? "all"],
    queryFn: () => api.listEvents(projectId, opts),
  });
}

// No separate useEventPayoffOf hook — EventRead already includes payoff_of/payoff_of_titles
// as derived fields, refreshed automatically when ["events"] is invalidated.

export function useCreateEvent() { /* useMutation + invalidate ["events"] */ }
export function useUpdateEvent(id: number, projectId: number) { /* + invalidate */ }
export function useDeleteEvent(projectId: number) { /* + invalidate */ }
```

**accept hook 扩展：**

```typescript
// useAcceptPendingUpdate onSuccess
if (data.target_table === "events") {
  qc.invalidateQueries({ queryKey: ["events"] });
}
```

### 6.8 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| foreshadow 多选用自定义组件（非原生 select multiple） | 搜索 + 按章分组 + 选中态展示 | 项目内事件可能很多，原生 select 体验差 |
| payoff_of 区域只读 | 数据来自其他事件的 foreshadows | 单向存储不变式；用户不能直接改 |
| EventList 按章节分组 | 故事发展顺序直观 | 与 character_states timeline 同模式 |
| 未兑现 ⚠️ 标记显示在列表卡片左侧 | 用户扫描时高优先级 | M4 Reviewer 的核心信号 |
| 新建事件 chapter_id 必填 | 事件必须归属某章 | 与 extractor 抽取的 chapter_id 一致 |

---

## 7. 测试策略

### 7.1 后端单元（不调 LLM）

**`tests/test_event_schema.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_event_table_columns` | 表有所有字段 |
| `test_event_indexes_exist` | 2 个索引存在 |
| `test_event_cascade_delete_with_chapter` | 删章节 → events 级联删 |
| `test_event_cascade_delete_with_project` | 删项目 → events 级联删 |
| `test_event_involved_characters_default_empty_array` | 默认 `[]` |
| `test_event_foreshadows_default_empty_array` | 默认 `[]` |

**`tests/test_extractor_prompts.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_system_prompt_has_events_section` | system.j2 含 events 抽取规则 |

**`tests/test_extractor_events.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_extract_events_creates_hard_fact_pending` | mock LLM → 生成 pending；auto=true |
| `test_extract_events_unknown_character_skipped` | involved_character_names 含不存在 → 跳过该项但 event 仍生成 |
| `test_extract_events_unknown_location_skipped` | location_name 不存在 → location_id=None 但 event 仍生成 |
| `test_extract_events_empty_title_skipped` | title 空 → 跳过 |
| `test_extract_events_empty_description_skipped` | description 空 → 跳过 |
| `test_extract_events_missing_kwarg_ok` | 不传 events kwarg → 当 [] |
| `test_extract_events_multiple_per_chapter` | 同章多事件 → 多条 pending |
| `test_extract_chapter_writes_events_pending` | end-to-end：mock LLM → 落 pending |

**`tests/test_pending_updates.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_accept_event_inserts_row` | accept → events 新增行 |
| `test_accept_event_target_location_gone_500` | location 被删 → 500 |
| `test_accept_event_invalid_location_type_500` | location_id 指向非 location lore → 500 |
| `test_accept_event_filters_deleted_characters` | accept 时过滤已删人物 |
| `test_accept_event_missing_title_500` | title 缺失 → 500 |
| `test_reject_event_no_db_change` | reject → 无 INSERT |

**`tests/test_events_api.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_list_events_default_all` | 默认返回所有 |
| `test_list_events_chapter_filter` | chapter_id 过滤 |
| `test_list_events_filter_unpaid` | 只返回有未兑现伏笔的事件 |
| `test_list_events_filter_paid` | 只返回伏笔全已兑现的事件 |
| `test_list_events_payoff_of_derived` | 响应含派生 payoff_of（A foreshadows B → B.payoff_of 含 A） |
| `test_list_events_involved_character_names_join` | 响应含 JOIN 人物名 |
| `test_list_events_location_name_join` | 响应含 JOIN 地点名 |
| `test_create_event_manual_post` | 手动 POST 立即落库 |
| `test_create_event_invalid_character_422` | involved_characters 含不存在 → 422 |
| `test_create_event_invalid_location_422` | location_id 不存在 → 422 |
| `test_create_event_invalid_location_type_422` | location_id 非 location 类型 → 422 |
| `test_create_event_self_foreshadow_422` | foreshadows 含自己 → 422 |
| `test_patch_event_add_foreshadow` | PATCH 加 foreshadows 链接 |
| `test_patch_event_remove_foreshadow` | PATCH 移除链接 |
| `test_patch_event_replace_foreshadows` | PATCH 全数组替换 |
| `test_delete_event_cleans_dangling_foreshadows` | 删 event X → 其他 events 的 foreshadows 不再含 X |

### 7.2 前端单元

**`tests/PendingUpdateItem.test.tsx` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_event_card_renders` | 🎯 + "新事件 · title" + description |
| `test_event_card_no_diff` | 不显示 旧值/新值 |

**`tests/EventForm.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_form_creates_new` | 填表 → POST |
| `test_form_edit_disables_chapter` | 编辑模式 chapter_id 禁用 |
| `test_form_involved_characters_chip_select` | Chip 多选 |

**`tests/ForeshadowMultiselect.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_multiselect_renders_selected` | 显示已选中的目标事件 |
| `test_multiselect_remove_calls_patch` | 点 ✗ → 调 PATCH |
| `test_multiselect_add_opens_dropdown` | 点 + → 弹下拉 |
| `test_multiselect_payoff_of_readonly` | 反向 payoff_of 只读 |
| `test_multiselect_no_self_option` | 下拉不显示当前事件自己 |

**`tests/EventList.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_list_filter_tabs` | 切换过滤标签 |
| `test_list_unpaid_warning_icon` | 未兑现事件显示 ⚠️ |
| `test_list_grouped_by_chapter` | 按章节分组 |

### 7.3 E2E 测试

**`tests/e2e/finalize-event.spec.ts`：**

```
1. 创建项目 + 章节带正文（"李雷在残月酒馆与韩梅重逢..."）
2. mock LLM finalize 返回 events 数组（含 1 个事件"残月酒馆相遇"）
3. 进 /pending → 看到 🎯 新事件卡片 → accept
4. 进 /events → 看到事件 + ⚠️ 未兑现标记（因为 foreshadows 为空但...实际未兑现需要 foreshadows 非空）
   (修正：新建事件默认 foreshadows=[]，filter=unpaid 要求 foreshadows 非空且至少一个目标未兑现。
    所以测试要：手动建第二个事件 + 在第一个上标 foreshadows 指向第二个 → 第一个未兑现 ⚠️)
5. 手动建第二个事件"真相揭露"
6. 在第一个事件上点 + 添加目标事件 → 选第二个事件
7. 第一个事件 ⚠️ 标记出现（埋了未兑现）；第二个事件的 payoff_of 显示第一个
8. 在第二个事件上... 等等，第二个事件没 foreshadows 任何东西，所以它不会进入 unpaid 列表。
   要让第一个的 ⚠️ 消失，需要某个事件 foreshadows 第一个的目标（即第二个）。
   实际：第 6 步后，第一个 foreshadows [2]。要 paid，需要事件 foreshadows 包含 2。再建第三个事件 foreshadows 2 → 第一个变 paid。
```

E2E 可简化为：建事件 → 标 foreshadow → 看到 ⚠️ 出现/消失。

### 7.4 YAGNI 不测

- LLM 真实 API
- 伏笔拓扑可视化
- 自动 foreshadow 链接抽取（M3c-C 不做）
- 跨章节 foreshadow 冲突检测（→ M4 Reviewer）

### 7.5 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/memory/schema.py` (Event) | 100% |
| `app/agents/extractor.py` (events 分支) | >90% |
| `app/api/pending_updates.py` (events accept 分支) | >90% |
| `app/api/events.py` | >85% |
| `app/llm/prompts/extractor/*.j2` | 100%（渲染） |
| 前端 `EventForm` + `ForeshadowMultiselect` + `EventList` + `PendingUpdateItem` | >85% |

---

## 8. M3c-C 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | finalize 后 `pending_updates` 含 `target_table='events'` + `auto=true` 记录 | sqlite3 直查 |
| 2 | 重抽覆盖 status='pending' 的旧 events pending | 单测 |
| 3 | accept → events 新增行（involved_characters/location_id 写入） | sqlite3 直查 |
| 4 | accept 过滤已删人物；location 不存在或非 location 类型 → 500 | 单测 |
| 5 | reject → 无 DB 变化 | 单测 |
| 6 | LLM 返回缺 events → 当作空数组，summary + entities + state_changes + relationship_changes 仍写 | 单测 |
| 7 | 涉及人物/地点名字解析失败 → 跳过该项但 event 仍生成 | 单测 |
| 8 | `GET /api/events?project_id=X` 默认返回所有事件 + 派生 payoff_of | curl + 单测 |
| 9 | `?filter=unpaid` 只返回有未兑现伏笔的事件 | 单测 |
| 10 | `?filter=paid` 只返回伏笔全已兑现的事件 | 单测 |
| 11 | 手动 POST 立即落库 | curl + 单测 |
| 12 | 手动 POST invalid character/location/self-foreshadow → 422 | 单测 |
| 13 | PATCH 加/移除 foreshadows 链接 | 单测 |
| 14 | PATCH foreshadows 全数组替换语义 | 单测 |
| 15 | DELETE event → 清理其他 events 的 foreshadows 悬挂引用 | 单测 |
| 16 | ActivityBar 🎯 第 9 图标 | 手工 |
| 17 | /events 页面：列表 + 过滤 + 新建 + 编辑 + foreshadow multiselect | 手工 + E2E |
| 18 | PendingUpdateItem 🎯 事件卡片正确渲染 | 单测 + E2E |
| 19 | 未兑现伏笔 ⚠️ 标记显示 | 单测 + 手工 |
| 20 | 反向 payoff_of 在 UI 只读显示 | 单测 + 手工 |
| 21 | accept 后 invalidate `["events"]`，UI 刷新 | 手工 |
| 22 | generation_logs 审计记录含 events prompt | sqlite3 直查 |
| 23 | 全后端测试通过 | `pytest -v` |
| 24 | 全前端测试通过 | `npm test` |
| 25 | 全 E2E 通过 | `npm run test:e2e` |

---

## 9. 待定 / 开放问题

1. **filter=unpaid 的精确定义**：当前定义是"foreshadows 非空且至少一个 target 没被任何事件 foreshadows"。但实际"兑现"的语义可能更宽松——比如某事件 B 被另一个事件 C 描述了"兑现 B 的伏笔"，但 C 可能没在 events 表登记。M3c-C 假设：所有"兑现"都必须以 events 登记。M4 Reviewer 可以补充"语义兑现"（向量检索找到段落里描述的兑现）。

2. **involved_characters 数组上限**：当前无限制。LLM 可能返回 10+ 人物，UI Chip 显示拥挤。倾向不限制（用户判断），如真有问题再加 UI 滚动。

3. **同章同名事件**：当前允许（无 UNIQUE）。LLM 在重抽时可能产出相似但略不同的 title（"残月酒馆相遇" vs "残月酒馆重逢"）。用户判断是否合并/删除。

4. **plot_line_id 字段死代码？**：M3c-C 完全不读不写此字段，仅 schema 预留。M3c-D 完成时此字段开始使用。在此之前 ORM 会接受任意 INT 但应用层不验证。

5. **跨项目事件引用**：foreshadows 数组允许任意 event_id。应用层不强制同 project。但 UI 只显示同项目事件，跨项目引用理论上不会发生（用户不会跨项目选）。倾向不加校验，YAGNI。

6. **删除事件时的用户确认**：UI 应弹"删除此事件将同时移除其他 N 个事件对它的 foreshadow 引用，确认？"——M3c-C 实现细节，前端责任。

---

## 10. 未来扩展（v2+，不在 M3c-C 范围）

- **M3c-D plot_lines 状态流转**：plot_lines 表 + 章节关联；event.plot_line_id 开始使用
- **M4 Reviewer "伏笔完整性"维度**：基于 events.foreshadows + payoff_of 检测"埋了没收"（孤儿伏笔）和"无铺垫爆发"（payoff_of 为空但描述像兑现）
- **M4+ 伏笔拓扑可视化**：D3 力导向图，事件为节点，foreshadow 链接为有向边，孤儿节点高亮
- **自动 foreshadow 链接建议**：基于章节摘要 + 向量检索，建议"这个事件可能是某前章事件的兑现"（仍是用户确认，不是自动应用）
- **跨项目事件模板**：常用事件类型（"相遇"、"背叛"、"获宝"）作为模板库
