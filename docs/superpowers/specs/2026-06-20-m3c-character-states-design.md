# NovelAI M3c-B — 人物状态时序（character_states）设计文档

- **日期**：2026-06-20
- **状态**：草案（待用户审阅）
- **范围**：M3c-B = 人物状态变化抽取 + `character_states` 时序表 + pending_updates 软事实分支 + 人物 modal 状态轨迹折叠区
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要 + 硬事实抽取）、M3b（向量检索层）已完成；Alembic 已引入

> M3c 拆分为 4 个独立子项目（A 关系演变 / **B 人物状态时序** / C 伏笔标注 / D plot_lines）。本文档仅覆盖 **B**。

---

## 1. 目标与非目标

### 1.1 目标

让 AI 能记住人物在每个章节末的状态，使角色弧光可追溯：

1. Extractor 在 finalize 时，**除 M3a 的摘要 + 硬事实外**，额外抽取本章透露的人物**显著状态变化**作为软事实
2. 抽取结果写入 `pending_updates` 队列（`auto=false`，用户必须确认）
3. Accept 时事务内：① INSERT `character_states` 行；② UPDATE `characters.current_state = state_snapshot`（镜像策略 B）
4. 新增 `GET /api/characters/{id}/states` 历史回溯端点
5. 人物编辑 modal 底部加"状态轨迹"折叠区，按章节倒序展示历史

### 1.2 非目标（M3c-B 不做）

- 关系演变（`relationships.valid_from/to_chapter`）— M3c-A
- 伏笔/呼应标注（`events` 表）— M3c-C
- plot_lines 状态流转 — M3c-D
- 弃用或迁移 `characters.current_state` 字段（B 镜像策略下不动）
- 修改常驻层注入逻辑（Writer 继续读 `characters.current_state`）
- 异步抽取（任务队列）— M3e
- 状态结构化字段（mood/location/injury 固定 schema）— 自由文本
- 轨迹冲突检测 — M4 Reviewer

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| `current_state` 与 `character_states` 关系 | **镜像策略 B**：`current_state` 始终 = 最新 `character_states.state_snapshot` | M2a 注入代码 0 改动；M3a 已有 `updated_characters.field="current_state"` 路径天然兼容；无数据迁移 |
| 抽取触发 | **diff 式**：仅在显著变化时生成 | 与 M3a `updated_characters` 语义一致；pending 面板不爆炸；轨迹更清晰 |
| 软事实性质 | `auto=false`，必须用户 accept | 状态/情绪是 LLM 推断，按总 spec §3.3 走软事实路径 |
| `state_snapshot` 内容 | **自由文本**（一段话，≤100 字） | 与 `characters.current_state` 字段类型一致；LLM 抽取最稳；M4 Reviewer 直观易读 |
| Extractor prompt 改造 | **方案 A**：扩展现有调用（一次 LLM 出三类结果） | 0 额外 LLM 成本；finalize 耗时不增；事务语义简单 |
| `character_states` schema | append-only 变化点日志（无 `valid_to_chapter`） | diff 式抽取下没必要记区间；回溯 `ORDER BY chapter_id DESC LIMIT 1` 即可 |
| 前端 UI 范围 | **选项 2**：复用 pending 面板 + 人物 modal 轨迹折叠区 | 选项 1 太薄（accept 后无可视）；选项 3 可视化留给 M4 |
| 常驻层注入逻辑 | **不变**（继续读 `current_state`） | M3c-B 是"额外提供历史回溯"，不是"重写常驻层" |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   └── schema.py                       # 修改：加 CharacterState ORM
├── agents/
│   └── extractor.py                    # 修改：_build_pending_rows 加 state_changes 分支
├── llm/prompts/extractor/
│   ├── system.j2                       # 修改：加"软事实：状态变化"抽取规则
│   └── user.j2                         # 修改：现有的人物列表补 current_state 字段
├── api/
│   ├── pending_updates.py              # 修改：accept handler 加 character_states 分支
│   └── characters_states.py            # 新增：GET /api/characters/{id}/states
└── models/
    ├── pending.py                      # 修改：PendingUpdateRead 摘要字段适配 state_snapshot
    └── character_state.py              # 新增：CharacterStateRead schema

alembic/versions/
└── <hash>_add_character_states.py      # 新增

web/
├── components/
│   └── entities/
│       ├── PendingUpdateItem.tsx       # 修改：character_states 卡片样式
│       └── CharacterStateTimeline.tsx  # 新增：人物 modal 底部折叠区
├── app/projects/[projectId]/
│   └── characters/                     # 修改：人物编辑 modal 注入 timeline
└── lib/
    ├── api.ts                          # 修改：加 listCharacterStates
    ├── queries.ts                      # 修改：useCharacterStates
    └── types.ts                        # 修改：加 CharacterState；PendingUpdate 适配

tests/                                  # 后端
├── test_extractor_agent.py             # 修改：state_changes 抽取用例
├── test_pending_updates.py             # 修改：character_states accept 用例
└── test_characters_states.py           # 新增

web/tests/                              # 前端
├── PendingUpdateItem.test.tsx          # 修改
└── CharacterStateTimeline.test.tsx     # 新增
```

### 2.1 职责边界

- `agents/extractor.py`：M3a 既有 + 新增 `_build_pending_rows` 的 state_changes 分支。仍然原子事务（重抽覆盖 status='pending' 的旧记录）。
- `api/pending_updates.py`：M3a 既有 + 新增 accept handler 的 `target_table='character_states'` 分支。
- `api/characters_states.py`：薄包装。校验 character 存在 → JOIN chapters → 倒序列出 states。
- `PendingUpdateItem.tsx`：M3a 既有 + 新增 state-change 卡片渲染分支。
- `CharacterStateTimeline.tsx`：纯展示组件，从 `useCharacterStates` 拉数据。

### 2.2 依赖方向

沿用 M2a/M3a/M3b 单向依赖：`api → agents → memory → llm → DB`。

---

## 3. 数据库变更

### 3.1 新增表：`character_states`

```sql
CREATE TABLE character_states (
  id INTEGER PRIMARY KEY,

  character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
  chapter_id   INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,

  state_snapshot  TEXT NOT NULL,                  -- 本章末状态描述（一段话，≤100 字）
  change_summary  TEXT NOT NULL DEFAULT '',       -- "为什么变了"（1-2 句话）

  extractor_log_id  INTEGER,                      -- 关联 generation_logs（审计）
  pending_update_id INTEGER,                      -- 反向追溯 accept 来源（可空，未来人工建的 state 无）

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX idx_char_state_char_chapter ON character_states(character_id, chapter_id);
CREATE INDEX idx_char_state_chapter      ON character_states(chapter_id);
```

**字段说明：**

| 字段 | 用途 |
|---|---|
| `state_snapshot` | 本章末该人物的状态描述（情绪/处境/身体状况/目标等），与 `characters.current_state` 同类型 |
| `change_summary` | 触发本章状态变化的事件简述；初始态或无变化时可为空字符串 |
| `extractor_log_id` | 审计：可追溯到生成该 state 的 LLM 调用 |
| `pending_update_id` | 审计：可追溯到用户 accept 的那条 pending；未来支持手工建 state 时为 null |

**无 `valid_to_chapter` / `recorded_at` 字段**（与原 spec §3.1 略有出入）——diff 式抽取下 `character_states` 是 append-only 变化点日志，不是区间有效记录；回溯用 `ORDER BY chapter_id DESC LIMIT 1`，时间用 `created_at`。

### 3.2 `pending_updates` 表

**结构不变。** M3a 已预留 `update_type='soft_fact'`、`auto=false`。M3c-B 只是新增一种 `target_table='character_states'` 的用法。

### 3.3 Alembic 迁移

```python
# alembic/versions/<hash>_add_character_states.py
"""add character_states

Revision ID: <hash>
Revises: f3a6512d59c3   # M3b 的 chunk_meta + vec_chunks
Create Date: 2026-06-20 ...
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
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


def downgrade():
    op.drop_index('idx_char_state_chapter', table_name='character_states')
    op.drop_index('idx_char_state_char_chapter', table_name='character_states')
    op.drop_table('character_states')
```

**无数据迁移。** B 镜像策略下 `characters.current_state` 字段保持不变；M3c-B 上线后新 accept 的 state_changes 才会开始往 `character_states` 写历史。

### 3.4 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| append-only 日志 | 不允许 UPDATE / DELETE | 历史完整性；删除人物时级联（FK ondelete cascade） |
| 不加 UNIQUE(character_id, chapter_id) | 允许同章多条 state | 同一章人物状态可能多次转变；与 pending_updates 一对多关系 |
| `pending_update_id` 反向外键不加 FK 约束 | 软关联（仅存 ID） | pending 可能被清理（未来）；state 历史应保留 |
| `extractor_log_id` 不加 FK 约束 | 沿用 M3a/M3b 风格（generation_logs 关联均无 FK） | 一致性 |

---

## 4. Extractor Agent 改造

### 4.1 Prompt 改造（方案 A：扩展现有调用）

**`extractor/system.j2` 修改一：M3a 既有 updated_characters 段落移除 `current_state`**

M3a 原 prompt 中 updated_characters 的 field 枚举为 `background|motivation|appearance|current_state`。M3c-B 起，**`current_state` 从该枚举中移除**（统一交给 state_changes），改为 `background|motivation|appearance`。

**`extractor/system.j2` 修改二：新增节（接现有 prompt 末尾）**

```
## 软事实：人物状态变化（state_changes）

除上述硬事实外，还要抽取本章透露的**人物状态变化**。

# 抽取准则

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
- **`current_state` 字段的变化一律走 `state_changes`，不再走 `updated_characters`**
- `updated_characters` 仅用于 background / motivation / appearance / 其他档案类字段的补充
- 这避免同一人物的同一变化被两条 pending 重复抽取（accept 顺序敏感问题）

## 字段要求
- `state_snapshot`：一段话，覆盖情绪/处境/身体状况/当前目标等，≤100 字
- `change_summary`：1-2 句话，说明触发本章状态变化的具体事件

# 输出格式扩展

在 `summary` 和 `entities` 同级，增加 `state_changes` 数组。如果本章无任何人物状态变化，返回空数组 `[]`。永远不要省略该字段。

{
  "summary": "...",
  "entities": { ... },
  "state_changes": [
    {
      "character_name": "李雷",
      "state_snapshot": "愤怒且受伤；左臂中刀未愈；决心向韩梅复仇",
      "change_summary": "韩梅在城东伏击李雷，导致其受伤并彻底决裂"
    }
  ]
}
```

**`extractor/user.j2` 修改：** 在已有"已有人物"列表的每行补上 `current_state`（作为 LLM 判断变化的基线）：

```
## 已有人物（{{ existing_characters|length }} 个）
{% for c in existing_characters %}
- {{ c.name }}（{{ c.role }}）：背景={{ c.background }} | 现状={{ c.current_state or "(未记录)" }}
{% endfor %}
```

### 4.2 LLM 响应格式（M3a 扩展）

```json
{
  "summary": "李雷推开残月酒馆的门...",
  "entities": {
    "new_characters": [...],
    "updated_characters": [...],
    "new_lore": [...],
    "updated_lore": [...]
  },
  "state_changes": [
    {
      "character_name": "李雷",
      "state_snapshot": "愤怒且受伤；左臂中刀未愈；决心向韩梅复仇",
      "change_summary": "韩梅在城东伏击李雷"
    }
  ]
}
```

**容错处理（与 M3a 风格一致）：**

- JSON parse 错 → 抛 `ExtractionError`（M3a 既有逻辑不变）
- 缺 `state_changes` 字段 → 当作空数组（容错；summary + entities 仍保留）
- `character_name` 为空 → 跳过该条
- `state_snapshot` 为空 → 跳过该条
- `character_name` 不在 existing_characters → 跳过该条（LLM 幻觉），记 warning
- `change_summary` 缺失 → 默认空字符串

### 4.3 `_build_pending_rows` 加 state_changes 分支

```python
existing_by_name = {c.name: c for c in existing_characters}

# ... M3a 既有 4 类分支 ...

# M3c-B 新增：state_changes → soft_fact pending
for sc in parsed.get("state_changes", []):
    name = (sc.get("character_name") or "").strip()
    snapshot = (sc.get("state_snapshot") or "").strip()
    if not name or not snapshot:
        continue  # 容错：跳过空字段

    char = existing_by_name.get(name)
    if char is None:
        # LLM 幻觉：状态变化指向不存在的人物（不在 existing_characters 列表中）
        # M3a 的 new_characters 可能含同名人？——按 M3a 既有逻辑，new_characters 是
        # 项目库里没有的新人物，状态变化针对新人物也算有效（用户 accept create 后
        # 该人物存在，再 accept state 时 char 已存在）。但本批 pending 尚未 accept，
        # 故此处跳过，记 warning；用户可以先 accept 新人物 create，再重抽。
        skipped_unknown_state_targets.append(name)
        continue

    rows.append(PendingUpdate(
        project_id=project_id,
        chapter_id=chapter_id,
        update_type="soft_fact",
        operation="create",
        target_table="character_states",
        target_id=None,  # 时序表 append-only，永远是 create
        proposed_change={
            "character_id": char.id,
            "character_name": char.name,
            "state_snapshot": snapshot,
            "change_summary": (sc.get("change_summary") or "").strip(),
        },
        reason=f"第 {chapter.order_index} 章状态变化",
        auto=False,  # 软事实：需用户确认
        extractor_model=model_name,
        status="pending",
    ))
```

**关键决策：**

- **`target_id=None`**：时序表 append-only，accept 时才 INSERT 新行，不需要预先指向某行
- **`auto=False`**：软事实必须用户确认
- **重抽覆盖规则沿用 M3a**：DELETE 同章 status='pending' 的旧记录（含 state_changes），character_states pending 自动覆盖；accepted/rejected 的保留

### 4.4 generation_logs 审计

M3a 既有逻辑不变。抽取调用仍记一条 `generation_logs`（`model_task='extractor'`），prompt 包含新增的 state_changes 规则，response 含完整 JSON。`extractor_log_id` 在 INSERT character_states 时回填。

---

## 5. API 契约

### 5.1 端点列表

```
POST   /api/chapters/{chapter_id}/finalize               # 不变（M3a）
GET    /api/pending-updates?...                           # 不变（M3a）
GET    /api/pending-updates/{id}                          # 不变（M3a）
POST   /api/pending-updates/{id}/accept                   # 修改：加 character_states 分支
POST   /api/pending-updates/{id}/reject                   # 不变
GET    /api/characters/{character_id}/states              # 新增
```

### 5.2 Accept Handler 新分支

`POST /api/pending-updates/{id}/accept` 在现有 characters/lore_entries 分支后追加：

```python
if pending.target_table == "character_states":
    data = pending.proposed_change
    char_id = data["character_id"]

    char = db.get(Character, char_id)
    if char is None:
        raise HTTPException(500, "target character gone")

    # ① INSERT 时序行
    state = CharacterState(
        character_id=char_id,
        chapter_id=pending.chapter_id,
        state_snapshot=data["state_snapshot"],
        change_summary=data.get("change_summary", ""),
        extractor_log_id=pending.extractor_log_id,
        pending_update_id=pending.id,
    )
    db.add(state)
    db.flush()  # 拿 state.id（用于审计）

    # ② 镜像策略 B：同步更新 characters.current_state
    char.current_state = data["state_snapshot"]

    pending.status = "accepted"
    pending.decided_at = datetime.now(UTC)
    db.commit()
    return PendingUpdateRead.from_orm(pending)
```

**响应：** 200 + `PendingUpdateRead`（status='accepted'）

**错误码（与 M3a 一致）：**

- 404 pending 不存在
- 409 已 accept/reject 过
- 500 target character 已被删

**事务性：** INSERT state + UPDATE characters.current_state + UPDATE pending.status 三步同一事务，任一失败回滚。

### 5.3 PendingUpdateRead 摘要字段适配

`entity_name` / `proposed_value` 等摘要字段从 `proposed_change` JSON 提取的逻辑加一条分支：

| target_table | entity_name | entity_type | field_name | old_value | proposed_value |
|---|---|---|---|---|---|
| `characters`（create） | name | "" | "" | "" | description |
| `characters`（update） | name | "" | field | old_value | new_value |
| `lore_entries`（create） | name | type | "" | "" | description |
| `lore_entries`（update） | name | "" | field | old_value | new_value |
| **`character_states`（create）** | **character_name** | **""** | **"state_snapshot"** | **""** | **state_snapshot** |

### 5.4 新端点：`GET /api/characters/{id}/states`

```
GET /api/characters/{character_id}/states?limit=20&order=desc
```

| Query | 默认 | 说明 |
|---|---|---|
| `limit` | 20 | 最大 100 |
| `order` | `desc` | `desc`（最新在前）/ `asc`（最早在前） |

**响应：** `list[CharacterStateRead]`

```python
class CharacterStateRead(ORMBase):
    id: int
    character_id: int
    chapter_id: int
    chapter_title: str         # JOIN chapters.title
    chapter_order: int         # JOIN chapters.order_index
    state_snapshot: str
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None
    created_at: datetime
```

**错误码：** 404 character 不存在。

**排序：** 按 `chapter_order`（不是 `created_at`）排，保证章节逻辑顺序与 `order_index` 一致。同章多条按 `created_at` 二级排序。

### 5.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| accept 双写（INSERT state + UPDATE current_state） | 同事务 | 镜像策略 B 的核心保证；失败回滚 |
| Reject 不动 target | 沿用 M3a | character_states 不会被 INSERT；current_state 不变 |
| states 端点按 `chapter_order` 排 | 不按 `created_at` | 章节逻辑顺序优先；重抽会改变 created_at 但不应改变展示顺序 |
| states 端点 limit 默认 20 | 单人物轨迹通常 ≤ 50 条 | UI 折叠区不需要分页 |

---

## 6. 前端 UI 与数据流

### 6.1 PendingUpdateItem 适配（最小改动）

在现有卡片渲染逻辑加一个分支：

```typescript
const isStateChange =
  pending.operation === "create" && pending.target_table === "character_states";

// 渲染：
// header：📝 状态变化 · {character_name}
// 内容：
//   状态：{state_snapshot}
//   原因：{change_summary}  ← 仅当非空时显示
// 按钮：✓ 接受 / ✗ 拒绝（与现有 pending 卡片一致）
```

完整卡片示意：

```
┌────────────────────────────────────────────────────────┐
│ 📝 状态变化 · 李雷                                       │
│   状态：愤怒且受伤；左臂中刀未愈；决心向韩梅复仇          │
│   原因：韩梅在城东伏击李雷，导致其受伤并彻底决裂          │
│   理由：第 5 章状态变化                                  │
│   [✓ 接受]  [✗ 拒绝]                                    │
└────────────────────────────────────────────────────────┘
```

### 6.2 CharacterStateTimeline 折叠区（新增组件）

放在人物编辑 modal 底部，默认折叠：

```
┌──────────────────────────────────────────────┐
│ 编辑人物：李雷                                │
│ ────────────────────────────────────────────│
│ 名字：[李雷]   角色：[主角 ▾]                │
│ ...（现有字段）                              │
│                                              │
│ ▼ 状态轨迹（3 条）                           │
│ ┌──────────────────────────────────────────┐│
│ │ 第 5 章 · 残月重逢                       ││
│ │ 状态：愤怒且受伤；左臂中刀未愈...        ││
│ │ 原因：韩梅在城东伏击李雷                 ││
│ │ 抽取于 2026-06-20 14:30                  ││
│ ├──────────────────────────────────────────┤│
│ │ 第 3 章 · 入城                           ││
│ │ 状态：警惕；初入青石城...                ││
│ │ 原因：初到陌生大城市                     ││
│ └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

**空状态：** 无轨迹时显示 "暂无状态轨迹记录。完成章节后 Extractor 会自动抽取显著状态变化。"

**折叠状态：** 默认折叠（`▼ 状态轨迹（3 条）`），点击展开。

### 6.3 hooks

```typescript
// lib/queries.ts 新增
export function useCharacterStates(characterId: number | null) {
  return useQuery({
    queryKey: ["character-states", characterId],
    queryFn: () => api.listCharacterStates(characterId!),
    enabled: characterId != null,
  });
}
```

**accept 一条 state_changes pending 后的 invalidate：**

```typescript
// useAcceptPendingUpdate 的 onSuccess 扩展
qc.invalidateQueries({ queryKey: ["pending-updates"] });
qc.invalidateQueries({ queryKey: ["pending-count"] });
qc.invalidateQueries({ queryKey: ["characters"] });
// M3c-B 新增：character_states 的 target_id 是 null，需从 proposed_change 取 character_id
if (accepted.target_table === "character_states") {
  const charId = accepted.proposed_change?.character_id;
  if (charId != null) {
    qc.invalidateQueries({ queryKey: ["character-states", charId] });
  }
}
```

### 6.4 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| Timeline 默认折叠 | 点击展开 | 多数时候用户只编辑档案字段，不需要看轨迹 |
| Timeline 不分页 | limit=20 一次拉 | 单人物轨迹量小；超过 20 条用户应考虑拆人物 |
| Timeline 空状态文案 | 解释何时会有数据 | 引导用户去 finalize 章节 |
| accept 后自动展开 Timeline | 不自动 | 用户可能在 batch accept 多条；保持当前 UI 状态 |
| PendingUpdateItem 卡片样式 | 复用现有 + 加 📝 图标 | 视觉一致 |

---

## 7. 测试策略

### 7.1 测试金字塔

```
                ┌─────────────────┐
                │ Playwright E2E  │  1 个，覆盖 finalize → accept → 看轨迹
                └─────────────────┘
            ┌─────────────────────────┐
            │ Agent + API 集成测试    │  mock LLM，验抽取 + accept + states 端点
            └─────────────────────────┘
        ┌───────────────────────────┐
        │ 单元测试（prompt + 组件） │
        └───────────────────────────┘
```

### 7.2 后端单元测试（不调 LLM）

**`tests/test_extractor_prompts.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_render_extractor_system_has_state_changes_section` | system.j2 含 state_changes 抽取规则 |
| `test_render_extractor_user_shows_current_state` | user.j2 渲染涉及人物的 current_state 字段 |
| `test_render_extractor_user_handles_empty_current_state` | current_state 为空时显示 "(未记录)" |

### 7.3 Agent 集成测试（mock LLMProvider）

**`tests/test_extractor_agent.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_extract_state_changes_creates_soft_fact_pending` | mock LLM 返回 state_changes → 生成 `update_type='soft_fact'` + `target_table='character_states'` pending |
| `test_extract_state_changes_unknown_character_skipped` | character_name 不在 existing → 跳过 |
| `test_extract_state_changes_empty_snapshot_skipped` | state_snapshot 为空 → 跳过 |
| `test_extract_state_changes_empty_name_skipped` | character_name 为空 → 跳过 |
| `test_extract_no_state_changes_field_ok` | LLM 返回缺 state_changes → 当作空数组；summary + entities 仍写 |
| `test_extract_state_changes_pending_has_auto_false` | 生成的 pending `auto=False` |
| `test_extract_rerun_deletes_old_state_pending` | 重抽覆盖 status='pending' 的 state_changes；accepted 保留 |
| `test_extract_state_changes_logs_warning_for_unknown` | skipped_unknown_state_targets 记入 generation_logs.context_summary |

### 7.4 API 测试

**`tests/test_pending_updates.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_accept_character_state_inserts_row` | accept → character_states 新增行（字段含 extractor_log_id / pending_update_id） |
| `test_accept_character_state_mirrors_current_state` | accept → characters.current_state = state_snapshot |
| `test_accept_character_state_target_gone_returns_500` | character 已删 → 500 |
| `test_accept_character_state_already_decided_returns_409` | 二次 accept → 409 |
| `test_reject_character_state_no_db_change` | reject → 无 character_states INSERT；current_state 不变 |
| `test_list_pending_includes_state_changes` | list 端点返回 state_changes 类型的 pending；摘要字段（entity_name / proposed_value）正确 |

**`tests/test_characters_states.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_list_states_default_desc` | 默认按 chapter_order 倒序 |
| `test_list_states_explicit_asc` | order=asc 按章节升序 |
| `test_list_states_includes_chapter_join` | 响应含 chapter_title / chapter_order |
| `test_list_states_404_unknown_character` | character 不存在 → 404 |
| `test_list_states_empty` | 无历史时返回空数组 |
| `test_list_states_limit_cap` | limit=200 → 截断到 100 |

### 7.5 前端单元测试

**`tests/PendingUpdateItem.test.tsx` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_state_change_card_renders` | 显示 "📝 状态变化 · 李雷" + state_snapshot |
| `test_state_change_card_hides_reason_when_empty` | change_summary 为空时不渲染"原因："行 |
| `test_state_change_card_accept_calls_mutation` | 点击 ✓ → 调 accept API |

**`tests/CharacterStateTimeline.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_timeline_collapsed_by_default` | 默认折叠 |
| `test_timeline_expand_on_click` | 点击 ▼ 展开 |
| `test_timeline_renders_states` | 展开后渲染各章 state 卡片 |
| `test_timeline_empty_state` | 无数据时显示"暂无状态轨迹记录" |
| `test_timeline_shows_chapter_title` | 每条 state 含"第 N 章 · {title}" |

### 7.6 E2E 测试

**`tests/e2e/finalize-character-state.spec.ts`：**

```
1. 创建项目 + 人物"李雷"（current_state="警惕"）+ 章节正文（"李雷被韩梅伏击受伤，决心复仇..."）
2. 进入章节 → 点 "完成本章"
3. 等待 toast "已抽取 N 条新事实"
4. 切到 📋 待处理 → 看到 📝 状态变化 · 李雷 卡片
5. accept → 状态变 "已接受"
6. 切到 👥 人物 → 点李雷 → 展开"状态轨迹"
7. 看到第 1 章状态卡片，含 snapshot "愤怒且受伤..." + 原因
8. 关闭 modal → 重新打开 → 人物列表的"现状"列也显示 "愤怒且受伤..."（镜像生效）
```

### 7.7 不测什么（YAGNI）

- LLM 真实 API（全部 mock）
- 抽取内容质量（人工验收范畴）
- 跨章"轨迹冲突"检测（→ M4 Reviewer）
- 并发 accept（假设单用户单请求）
- 轨迹分页（数据量小）

### 7.8 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/memory/schema.py` (CharacterState) | 100% |
| `app/agents/extractor.py` (state_changes 分支) | >90% |
| `app/api/pending_updates.py` (character_states accept 分支) | >90% |
| `app/api/characters_states.py` | >85% |
| `app/llm/prompts/extractor/*.j2` | 100%（渲染） |
| 前端 `PendingUpdateItem` + `CharacterStateTimeline` | >85% |

---

## 8. M3c-B 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | finalize 后 `pending_updates` 含 `update_type='soft_fact'` + `target_table='character_states'` 记录 | sqlite3 直查 |
| 2 | 生成的 pending `auto=0`（false） | sqlite3 直查 |
| 3 | 重抽覆盖 status='pending' 的旧 state_changes；accepted/rejected 保留 | 单测 + 手工 |
| 4 | accept → `character_states` 新增行（字段含 extractor_log_id / pending_update_id） | sqlite3 直查 |
| 5 | accept → 同事务 UPDATE `characters.current_state = state_snapshot` | sqlite3 直查 |
| 6 | reject → 无 DB 变化（character_states 无新行；current_state 不变） | 单测 |
| 7 | LLM 返回非 JSON → 422 + chapter 不变（沿用 M3a） | 单测 |
| 8 | LLM 返回缺 state_changes → 当作空数组，summary + entities 仍写 | 单测 |
| 9 | character_name 不在 existing → 跳过 + warning 入 generation_logs | 单测 |
| 10 | `GET /api/characters/{id}/states` 返回倒序轨迹 + JOIN chapter 字段 | 单测 + curl |
| 11 | ActivityBar 📋 badge 包含 state_changes pending 数 | 手工 |
| 12 | PendingUpdateItem 正确渲染 📝 状态变化卡片 | 单测 + 手工 |
| 13 | 人物编辑 modal 含状态轨迹折叠区，默认折叠 | 手工 |
| 14 | 折叠区展开后显示各章 state，含 chapter_title | E2E |
| 15 | accept 后 invalidate `["character-states"]`，UI 自动刷新 | 手工 |
| 16 | generation_logs 记录抽取调用（含 state_changes prompt + response） | sqlite3 直查 |
| 17 | 全后端测试通过 | `pytest -v` |
| 18 | 全前端测试通过 | `npm test` |
| 19 | 全 E2E 通过 | `npm run test:e2e` |

---

## 9. 待定 / 开放问题

1. **新人物 + 其状态变化在同章出现时的处理顺序**：
   - 场景：本章首次出场"韩梅"（new_character），同时她"被伏击受伤"（state_change for 韩梅）
   - 当前处理：state_change 的 `character_name=韩梅` 不在 existing_characters（项目库里还没有）→ 跳过，记 warning
   - 用户恢复路径：① 进 pending 面板 accept 韩梅的 create 人物 pending；② 回到该章节重新点"完成本章"触发重抽；③ 重抽时韩梅已在 existing_characters 列表中，state_changes 能匹配到，重新生成一条 state_changes pending
   - 替代方案：在 `_build_pending_rows` 内先把 new_characters 视为"准 existing"，state_changes 能匹配到 → 但 accept 顺序约束复杂（必须先 accept create 再 accept state，否则 state.accept 时 char 仍不存在）
   - **倾向当前处理（跳过）**：简单；恢复路径虽然要重抽但用户可理解；后续优化可放在 M3c-D 之后

2. **同章同人物多条 state_changes**：
   - 场景：LLM 返回李雷在本章两条状态变化（中段 + 结尾）
   - 当前处理：都生成 pending（一对多）；用户可分别 accept/reject
   - `character_states` 表无 UNIQUE 约束，允许同章同人物多条
   - 回溯 API 默认倒序，最新在前
   - **倾向允许**：符合 append-only 语义

3. **抽取 prompt 中"显著变化"的判断标准**：
   - LLM 判断"是否显著"非确定性
   - temperature=0.1 已经尽力稳；用户 reject 错抽的、accept 对的
   - M3d 否定记忆会进一步减少重复抽错

4. **常驻层注入是否需要"上一章状态"**：
   - 当前：Writer 读 `characters.current_state`（最新镜像）
   - 替代：注入"涉及人物在上一章末的状态"（从 character_states 时序取）——语义相同，但绕一层
   - **倾向不改**：镜像策略下 `current_state` 就是"最新已知状态"，与"上一章末"在 finalize 流程下等价

5. **未来支持用户手工建 state**：
   - 当前 `pending_update_id` 字段允许 null，预留手工建的入口
   - M3c-B 不实现手工建（YAGNI）；M4 之后如有需要再加 `POST /api/characters/{id}/states` 端点

---

## 10. 未来扩展（v2+，不在 M3c-B 范围）

- **M3c-A 关系演变**：`relationships.valid_from/to_chapter` + 部分唯一索引 + 时序回溯
- **M3c-C 伏笔标注**：`events` 表 + `foreshadows/payoff_of` 双向 JSON 引用
- **M3c-D plot_lines 状态流转**：`plot_lines` 表 + 章节关联
- **M3d 否定记忆**：reject 时记签名，下次抽取 prompt 提示"以下已被拒绝"
- **M3e 异步抽取**：finalize 走任务队列 + SSE 进度
- **M4 Reviewer**：基于 character_states 时序检测"人物一致性"冲突（如"第 5 章李雷决心复仇，第 7 章却突然与韩梅和好如初"）
- **轨迹可视化**：独立 `/characters/[id]` 详情页，时间线图表
