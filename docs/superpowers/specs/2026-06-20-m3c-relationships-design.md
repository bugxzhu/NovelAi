# NovelAI M3c-A — 关系演变（relationships）设计文档

- **日期**：2026-06-20
- **状态**：草案（待用户审阅）
- **范围**：M3c-A = 关系时序表 + Extractor 抽取关系变化 + pending_updates 软事实分支 + accept 版本切换 + retrieval 接入常驻层 + 前端关系管理页
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要 + 硬事实）、M3b（向量检索）、M3c-B（人物状态时序，已验证时序+镜像+历史 API 架构）已完成

> M3c 拆分为 4 个独立子项目（**A 关系演变** / B 人物状态时序 ✅ / C 伏笔标注 / D plot_lines）。本文档仅覆盖 **A**。

---

## 1. 目标与非目标

### 1.1 目标

让 AI 能记住人物关系及其演变，支撑 M4 Reviewer 的"关系合理性"维度：

1. Extractor 在 finalize 时，除 M3a/M3c-B 的抽取外，**额外**抽取本章透露的**人物间关系变化**（新建/类型转变/强度变化/破裂）作为软事实
2. 抽取结果写入 `pending_updates` 队列（`auto=false`，用户必须确认）
3. Accept 时事务内：① 把同方向（from→to）旧"当前有效"关系软失效（设 `valid_to_chapter`）；② INSERT 新关系（`valid_from_chapter`=`chapter_id`, `valid_to_chapter`=NULL）
4. 部分唯一索引保证同方向同时只有一条当前有效关系
5. 接入 M2a 已有的 `ContextBundle.relationships` 占位字段——`assemble_context` 拉涉及人物两两的当前有效关系填入
6. 用户可在 `/relationships` 页面手动建关系（开章前初始态）+ 编辑 + 查看演变历史

### 1.2 非目标（M3c-A 不做）

- 伏笔/呼应标注（events 表 + foreshadows/payoff_of）— M3c-C
- plot_lines 状态流转 — M3c-D
- 关系图可视化（力导向图）— M4 之后
- 双向关系聚合 UI（A 单向存储；UI 展示 X→Y 一行，不合并）
- 跨章节关系冲突检测 — M4 Reviewer
- 异步抽取（任务队列）— M3e
- LLM 真实 API 集成测试 — 全部 mock

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 关系方向 | **单向**（from→to） | 与 spec §3.1 一致；支持不对等感情（暗恋、单方面敌意）；部分唯一索引严格保证 |
| 抽取触发 | **diff 式**：仅在显著变化时生成 | 与 M3c-B 一致；pending 面板不爆炸 |
| 软事实性质 | `auto=false`，必须用户 accept | 关系是 LLM 推断，按总 spec §3.3 走软事实路径 |
| 版本切换 | **A：accept 自动软失效旧版 + INSERT 新版** | 一次点击做两件事；M3c-B 风格；部分唯一索引保证不变式 |
| `type` 字段 | **自由文本** | 中文小说关系类型丰富（仇人/旧友/师徒/暗恋/结义兄弟/...），枚举写不完 |
| `strength` 字段 | **保留（-1.0 ~ 1.0）** | spec 原设计；M4 Reviewer 量化"关系强度变化"用得上 |
| `valid_from/to_chapter` 类型 | INTEGER chapter_id（软关联，不加强 FK） | spec 原设计；与 character_states 一致 |
| 部分唯一索引 | `UNIQUE (from_char_id, to_char_id) WHERE valid_to_chapter IS NULL` | SQLite 原生支持；保证同时只有一条当前有效 |
| Extractor prompt 改造 | **方案 A**：扩展一次调用出 summary + entities + state_changes + relationship_changes | 沿用 M3c-B 验证过的模式；0 额外 LLM 成本 |
| `/relationships` 独立页面 | ActivityBar 加 🤝 第 8 图标 | 与 chapters/characters/lore/pending 平级 |
| 前端 UI 范围 | **选项 2**：CRUD + pending 复用 + 历史折叠区 | 选项 1 太薄（accept 后看不到结果）；选项 3（图可视化）留给 M4 |
| retrieval 注入哪些关系 | 仅涉及人物两两的当前有效（valid_to IS NULL） | 控制常驻层 token；不抽全局 |
| 手动 PATCH 能改什么 | 仅 type/strength/description | 不允许通过 PATCH 改 valid_*（破坏时序语义） |
| 手动新建 `valid_from_chapter` 默认 | 0（"开章前"） | 用户在写章节前建初始关系；与 order_index 从 1 开始不冲突 |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   ├── schema.py                       # 修改：加 Relationship ORM + 部分唯一索引
│   └── retrieval.py                    # 修改：populate ContextBundle.relationships
├── agents/
│   └── extractor.py                    # 修改：_build_pending_rows 加 relationship_changes 分支
├── llm/prompts/extractor/
│   ├── system.j2                       # 修改：加 relationship_changes 抽取规则
│   └── user.j2                         # 修改：渲染 existing_relationships 段
├── api/
│   ├── pending_updates.py              # 修改：_derive_summary_fields + accept 加 relationships 分支
│   └── relationships.py                # 新增：CRUD + history + soft-close 端点
├── main.py                             # 修改：注册 relationships router
└── models/
    └── relationship.py                 # 新增：RelationshipRead + RelationshipHistoryItem

alembic/versions/
└── <hash>_add_relationships.py         # 新增

web/
├── app/projects/[projectId]/
│   └── relationships/page.tsx          # 新增：关系管理页
├── components/
│   ├── layout/ActivityBar.tsx          # 修改：加 🤝 第 8 图标
│   └── entities/
│       ├── PendingUpdateItem.tsx       # 修改：🤝 关系卡片
│       ├── RelationshipForm.tsx        # 新增：手动建/编辑关系表单
│       ├── RelationshipList.tsx        # 新增：左侧列表
│       └── RelationshipHistoryPanel.tsx # 新增：演变历史折叠区
└── lib/
    ├── api.ts                          # 修改：加 relationships 端点
    ├── queries.ts                      # 修改：useRelationships 等 hooks
    └── types.ts                        # 修改：加 Relationship 类型

tests/                                  # 后端
├── test_relationship_schema.py         # 新增
├── test_extractor_relationships.py     # 新增
├── test_pending_updates.py             # 修改：relationships accept
├── test_relationships_api.py           # 新增
└── test_context_assembly.py            # 修改：relationships 注入

web/tests/                              # 前端
├── PendingUpdateItem.test.tsx          # 修改
├── RelationshipForm.test.tsx           # 新增
└── e2e/finalize-relationship.spec.ts   # 新增
```

### 2.1 职责边界

- `agents/extractor.py`：M3a/M3c-B 既有 + 新增 `_build_pending_rows` 的 relationship_changes 分支。原子事务不变。
- `api/pending_updates.py`：M3a/M3c-B 既有 + 新增 accept handler 的 `target_table='relationships'` 分支（含版本切换逻辑）。
- `api/relationships.py`：薄包装。CRUD + history JOIN + soft-close。
- `memory/retrieval.py`：M2a 占位字段 `ContextBundle.relationships=[]` 改为查涉及人物两两当前有效关系。
- `RelationshipForm.tsx`：手动新建/编辑。debounce 自动保存（与 CharacterForm 同模式）。
- `RelationshipHistoryPanel.tsx`：纯展示组件。调 `/api/relationships/history`。

### 2.2 依赖方向

沿用 M2a/M3a/M3b/M3c-B 单向依赖：`api → agents → memory → llm → DB`。

---

## 3. 数据库变更

### 3.1 新增表：`relationships`

```sql
CREATE TABLE relationships (
  id INTEGER PRIMARY KEY,

  project_id    INTEGER NOT NULL REFERENCES projects(id)   ON DELETE CASCADE,
  from_char_id  INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
  to_char_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,

  type         TEXT    NOT NULL,                  -- 自由文本：仇人/旧友/师徒/...
  strength     REAL    NOT NULL DEFAULT 0.0,      -- -1.0 ~ 1.0
  description  TEXT    NOT NULL DEFAULT '',

  valid_from_chapter INTEGER NOT NULL,            -- chapter_id（软关联）
  valid_to_chapter   INTEGER,                     -- NULL = 当前有效

  change_summary     TEXT    NOT NULL DEFAULT '', -- "为什么变了"（M3c-B 风格）
  extractor_log_id   INTEGER,                     -- 关联 generation_logs（审计）
  pending_update_id  INTEGER,                     -- 反向追溯 accept 来源（手动建为 null）

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

-- 检索常用：取涉及人物的当前有效关系
CREATE INDEX idx_rel_from_to_current
  ON relationships(from_char_id, to_char_id)
  WHERE valid_to_chapter IS NULL;

-- 项目级列出（关系管理页）
CREATE INDEX idx_rel_project ON relationships(project_id, from_char_id);

-- 不变式：同一对人物同一方向同时只能有一条当前有效关系
CREATE UNIQUE INDEX uq_rel_current
  ON relationships(from_char_id, to_char_id)
  WHERE valid_to_chapter IS NULL;
```

**字段说明：**

| 字段 | 用途 |
|---|---|
| `from_char_id` / `to_char_id` | 关系方向（单向） |
| `type` | 自由文本关系类型 |
| `strength` | -1.0（极度敌对）~ 1.0（极度亲密），0.0 中立 |
| `description` | 关系的具体表现或缘由 |
| `valid_from_chapter` | 关系生效的章节 id；手动建初始态用 0 |
| `valid_to_chapter` | 关系失效的章节 id；NULL = 当前有效 |
| `change_summary` | 触发本章关系变化的事件（M3c-B 风格） |
| `extractor_log_id` / `pending_update_id` | 审计字段（手动建两者皆 null） |

### 3.2 Alembic 迁移

```python
# alembic/versions/<hash>_add_relationships.py
"""add relationships

Revision ID: <hash>
Revises: d9dd1e0c1224   # M3c-B 的 character_states
Create Date: 2026-06-20 ...
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
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
    # 部分索引（含 WHERE 子句）— SQLAlchemy autogenerate 不识别 sqlite_where，手写
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


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_rel_current")
    op.drop_index('idx_rel_project', table_name='relationships')
    op.execute("DROP INDEX IF EXISTS idx_rel_from_to_current")
    op.drop_table('relationships')
```

**down_revision = `'d9dd1e0c1224'`**（M3c-B 的 character_states 迁移）。

**无数据迁移**（新表）。

### 3.3 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| `from_char_id` < `to_char_id` 约束 | **不加** | 单向关系，from/to 不可颠倒排序 |
| 允许 A→B 与 B→A 同时存在 | 是 | 表达不对等感情（X 暗恋 Y，Y 视 X 为朋友） |
| `valid_to = valid_from` 是否合法 | 是 | 边界：瞬间有效（"X 以为 A，立刻发现是 B"） |
| `strength` 越界处理 | 裁剪到 [-1.0, 1.0] | LLM 可能给 1.5 |
| 部分唯一索引手动 SQL | autogenerate 不识别 `sqlite_where` | M3b vec_chunks 已有先例（手写 SQL） |
| `extractor_log_id` / `pending_update_id` 无 FK 约束 | 沿用 M3a/M3c-B 风格（软关联） | 一致性；保留审计数据 |

---

## 4. Extractor Agent 改造

### 4.1 Prompt 改造（方案 A：扩展现有调用）

**`extractor/system.j2` 修改一：JSON 输出格式扩展**

在 `state_changes` 同级加 `relationship_changes`：

```
{
  "summary": "...",
  "entities": { ... },
  "state_changes": [ ... ],
  "relationship_changes": [
    {
      "from_character_name": "已有人物名",
      "to_character_name": "已有人物名",
      "type": "关系类型（自由文本，如 仇人/旧友/师徒/暗恋）",
      "strength": -1.0 ~ 1.0,
      "description": "关系的具体表现或缘由（1-2 句话）",
      "change_summary": "触发本章关系变化的事件（1-2 句话）"
    }
  ]
}
```

**`extractor/system.j2` 修改二：新增节（接 state_changes 准则末尾）**

```
## 软事实：人物关系变化（relationship_changes）

抽取本章透露的**人物间关系变化**。一条关系是单向的（from → to）。

### 何时抽
仅当本章透露了人物间关系的明确变化时才抽：
- 新关系建立（首次相遇、结盟、结仇）
- 关系类型转变（朋友→仇人、陌生人→恋人）
- 关系强度显著变化（信任度大幅升降）
- 关系破裂（决裂、背叛、断绝）
- 关系属性补充（如"原来 X 是 Y 的私生子"——揭示隐藏关系）

### 不抽
- 人物本章只是同框出现但关系无变化
- 描写细节但未透露关系本身

### 字段要求
- `from_character_name`、`to_character_name`：必须是已有人物库中的名字（不要为新人物抽关系——先 accept 新人物再重抽）
- `type`：自由文本，简明描述关系类型
- `strength`：-1.0（极度敌对）~ 1.0（极度亲密）；0.0 为中立
- `description`：1-2 句话，关系的具体表现或缘由
- `change_summary`：1-2 句话，触发本章关系变化的事件

### 重要：方向性
关系是单向的。"李雷暗恋韩梅" 和 "韩梅视李雷为朋友" 是两条独立记录，from/to 不可颠倒。
```

**`extractor/user.j2` 修改：** 新增"现有当前有效关系"段落：

```
## 已有关系（{{ existing_relationships|length }} 条当前有效）
{% for r in existing_relationships %}
- {{ r.from_name }} → {{ r.to_name }}：{{ r.type }}（强度 {{ r.strength }}）{% if r.description %} — {{ r.description }}{% endif %}
{% endfor %}
```

### 4.2 LLM 响应格式扩展

```json
{
  "summary": "...",
  "entities": { ... },
  "state_changes": [ ... ],
  "relationship_changes": [
    {
      "from_character_name": "李雷",
      "to_character_name": "韩梅",
      "type": "仇人",
      "strength": -0.8,
      "description": "李雷决心复仇，视韩梅为背叛者",
      "change_summary": "韩梅在城东伏击李雷导致关系破裂"
    }
  ]
}
```

**容错处理：**

- 缺 `relationship_changes` 字段 → 当作空数组
- `from`/`to` 任一为空 → 跳过
- `from == to`（自指）→ 跳过
- `from`/`to` 任一不在 existing_characters → 跳过（记 warning）
- `type` 为空 → 跳过
- `strength` 越界（>1.0 或 <-1.0）→ 裁剪到 [-1.0, 1.0]
- `strength` 非数字 → 默认 0.0
- `description` / `change_summary` 缺失 → 默认空字符串

### 4.3 `_build_pending_rows` 加 relationship_changes 分支

```python
existing_by_name = {c.name: c for c in existing_characters}

# ... M3a 4 类 + M3c-B state_changes ...

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

    # 强度范围裁剪 + 非数字容错
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
            "valid_from_chapter": chapter_id,  # 本章生效
        },
        reason=(rc.get("reason") or ""),
        auto=False,
        extractor_model=model_name,
        status="pending",
    ))
```

**关键决策：**

- `operation="create"`：每次关系变化都 INSERT 新版本（不是 UPDATE）
- `target_id=None`：accept 时才决定 INSERT 哪一行
- `valid_from_chapter=chapter_id`：pending 携带生效章；accept 时落库
- `char_by_name` 复用 M3c-B 既有字典

### 4.4 generation_logs 审计

不变。抽取调用仍记一条 `generation_logs`，prompt 含新增的 relationship_changes 规则。

---

## 5. API 契约

### 5.1 端点列表

```
# pending_updates（修改）
POST   /api/pending-updates/{id}/accept                # 加 relationships 分支

# relationships（新增）
GET    /api/relationships?project_id=X[&include_history=true]
GET    /api/relationships/history?from_char_id=X&to_char_id=Y
POST   /api/relationships                                # 手动新建
PATCH  /api/relationships/{id}                           # 编辑 type/strength/description
DELETE /api/relationships/{id}                           # 物理删除（管理员）
POST   /api/relationships/{id}/soft-close                # 手动软失效
```

### 5.2 Accept Handler 新分支（版本切换方案 A）

`POST /api/pending-updates/{id}/accept` 在 character_states 分支后追加：

```python
elif p.target_table == "relationships":
    # M3c-A: version-switch semantics
    data = p.proposed_change or {}
    from_id = data.get("from_character_id")
    to_id = data.get("to_character_id")
    if from_id is None or to_id is None:
        raise HTTPException(500, "relationships pending missing from/to")

    # 校验两端人物仍存在
    if db.get(Character, from_id) is None or db.get(Character, to_id) is None:
        raise HTTPException(500, "target character gone")

    new_from_chapter = data.get("valid_from_chapter", p.chapter_id)

    # ① 同方向当前有效关系软失效（事务内）
    db.execute(
        update(Relationship)
        .where(
            Relationship.from_char_id == from_id,
            Relationship.to_char_id == to_id,
            Relationship.valid_to_chapter.is_(None),
        )
        .values(valid_to_chapter=new_from_chapter, updated_at=datetime.now(UTC))
    )

    # ② INSERT 新关系
    rel = Relationship(
        project_id=p.project_id,
        from_char_id=from_id, to_char_id=to_id,
        type=data.get("type", ""),
        strength=data.get("strength", 0.0),
        description=data.get("description", ""),
        valid_from_chapter=new_from_chapter,
        valid_to_chapter=None,  # 当前有效
        change_summary=data.get("change_summary", ""),
        extractor_log_id=p.extractor_log_id,
        pending_update_id=p.id,
    )
    db.add(rel)
```

**事务保证：** UPDATE 旧版 + INSERT 新版 + UPDATE pending.status 三步同一事务；任一失败回滚，部分唯一索引不变式不被破坏。

**部分唯一索引行为：** UPDATE 把旧版 `valid_to` 从 NULL 改为非 NULL 后，UNIQUE 约束不再覆盖它（因为 `WHERE valid_to IS NULL`），INSERT 新版才合法。SQLite 在同一事务内对此支持良好。

**响应：** 200 + `PendingUpdateRead`（status='accepted'）

**错误码：**
- 404 pending 不存在
- 409 已 accept/reject 过
- 500 任一端人物已被删 / from/to 缺失

### 5.3 `_derive_summary_fields` 扩展

`target_table="relationships"` 时：

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
    proposed_value = f"{rtype}（强度 {strength}）：{desc}" if desc else f"{rtype}（强度 {strength}）"
```

### 5.4 `GET /api/relationships`

```
GET /api/relationships?project_id=1&include_history=false&limit=200
```

| Query | 默认 | 说明 |
|---|---|---|
| `project_id` | 必填 | 项目隔离 |
| `include_history` | `false` | true 时返回含 valid_to 非空的历史版本 |
| `limit` | 200 | 最大 500（手动 cap） |

**响应：** `list[RelationshipRead]`

```python
class RelationshipRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    from_char_id: int
    from_char_name: str         # JOIN characters.name
    to_char_id: int
    to_char_name: str           # JOIN characters.name
    type: str
    strength: float
    description: str
    valid_from_chapter: int
    valid_to_chapter: int | None
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None
```

默认（`include_history=false`）：只返回 `valid_to_chapter IS NULL`，按 `(from_char_name, to_char_name)` 排序。

### 5.5 `GET /api/relationships/history`

```
GET /api/relationships/history?from_char_id=1&to_char_id=2
```

| Query | 必填 | 说明 |
|---|---|---|
| `from_char_id` | 是 | 单向：from |
| `to_char_id` | 是 | 单向：to |

**响应：** `list[RelationshipHistoryItem]`

```python
class RelationshipHistoryItem(BaseModel):
    version_id: int             # relationships.id
    valid_from_chapter: int
    valid_to_chapter: int | None
    type: str
    strength: float
    description: str
    change_summary: str
    created_at: datetime
```

按 `valid_from_chapter DESC, created_at DESC` 排序（最新版本在前）。

### 5.6 `POST /api/relationships`（手动新建）

```python
class RelationshipCreate(BaseModel):
    project_id: int
    from_char_id: int
    to_char_id: int
    type: str
    strength: float = 0.0
    description: str = ""
    valid_from_chapter: int = 0  # 默认 0 = 开章前
    change_summary: str = ""     # 手动建可留空
```

**逻辑：**
- 校验 project + from/to 人物存在
- 强度裁剪到 [-1.0, 1.0]
- `from == to` → 422
- 部分唯一索引冲突（同方向已有当前有效）→ 409
- 立即落库（不经过 pending_updates）

**响应：** 201 + `RelationshipRead`

### 5.7 `PATCH /api/relationships/{id}`

```python
class RelationshipUpdate(BaseModel):
    type: str | None = None
    strength: float | None = None
    description: str | None = None
    # 不允许改 valid_from/to_chapter, from/to_char_id, project_id
```

**逻辑：**
- 仅更新提供的字段
- `strength` 提供则裁剪
- 不存在 → 404

### 5.8 `DELETE /api/relationships/{id}`

物理删除（管理员操作，正常使用应走 soft-close）。删除前检查是否为当前有效（如果是，直接删可能丢历史；返回 409 提示用 soft-close）。

**响应：** 204 或 409（如果是当前有效关系）

### 5.9 `POST /api/relationships/{id}/soft-close`

```json
{"valid_to_chapter": 5}
```

把指定关系的 `valid_to_chapter` 设为给定值（必填）。

**响应：** 200 + `RelationshipRead`

### 5.10 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 手动新建立即落库 | 不走 pending | 用户主动操作；不重复审 |
| PATCH 禁止改 valid_*/from/to | 时序语义保护 | 改这些等于改历史 |
| DELETE 拒绝当前有效 | 提示用 soft-close | 保护历史完整性 |
| history 端点必填 from + to | 不接受单参 | 单向关系；查询明确 |
| 手动 POST 冲突返回 409 | 不静默覆盖 | 用户知情 |

---

## 6. Retrieval 接入（M2a 占位填充）

### 6.1 `assemble_context` 改造

`app/memory/retrieval.py:159` 的 `relationships=[]` 替换为实际查询：

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

return ContextBundle(
    ...,
    relationships=relationships,  # 替换原来的 []
    ...
)
```

**`writer/user.j2:28-33` 已经会渲染 relationships 段，无需改动。**

### 6.2 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 只注入涉及人物两两的 | 不抽全局 | 控制 token；常驻层只放本章相关 |
| 只注入当前有效 | 不含历史 | Writer 关心"现在他们是什么关系"，不关心历史 |
| `len(char_id_set) >= 2` 才查 | 单人物无关系 | 优化；避免空查询 |

---

## 7. 前端 UI 与数据流

### 7.1 ActivityBar 加 🤝 第 8 图标

```typescript
const ITEMS = [
  { icon: "🏠", label: "项目列表", path: "__HOME__", isHome: true },
  // — divider —
  { icon: "📚", label: "章节", path: "chapters" },
  { icon: "👥", label: "人物", path: "characters" },
  { icon: "🤝", label: "关系", path: "relationships" },   // 新增
  { icon: "🌍", label: "设定", path: "lore" },
  { icon: "📜", label: "历史", path: "history" },
  { icon: "📋", label: "待处理", path: "pending" },
  { icon: "🔍", label: "搜索", path: "search" },
];
```

### 7.2 `/relationships` 页面（ChapterWorkspaceGrid 布局）

```
┌──────────────────────────────────────────────────────────────────┐
│🤝│  当前关系 (5)                              [+ 新建]            │
│  │──────────────────────────────────────────────────────────────│
│🏠│  李雷 → 韩梅 · 仇人（强度 -0.8）                              │
│📚│  李雷 → 王五 · 师徒（强度 0.6）                               │
│👥│  韩梅 → 赵六 · 主仆（强度 -0.3）                              │
│🤝│  ...                                                         │
│🌍│                                                              │
│📜│  ─────── 右侧：选中关系的详情 + 历史 ───────                  │
│📋│                                                              │
│🔍│  编辑关系：李雷 → 韩梅                                       │
│🌙│  From: [李雷 ▾]   To: [韩梅 ▾]                              │
│  │  类型: [仇人]                                                │
│  │  强度: ▬▬▬▬▬▬◉▬▬▬▬  -0.8                                  │
│  │  描述: [李雷决心复仇，视韩梅为背叛者]                         │
│  │  生效章: 第 5 章（不可改）                                   │
│  │                                                              │
│  │  ▼ 演变历史（2 版本）                                        │
│  │  ┌──────────────────────────────────────────┐               │
│  │  │ 第 5 章 → 当前 · 仇人（强度 -0.8）        │               │
│  │  │ 原因：韩梅在城东伏击李雷                  │               │
│  │  ├──────────────────────────────────────────┤               │
│  │  │ 第 1 章 → 第 5 章 · 旧友（强度 0.5）      │               │
│  │  │ 原因：开章前设定                          │               │
│  │  └──────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────┘
```

### 7.3 PendingUpdateItem 关系卡片

```typescript
const isRelationship = pending.target_table === "relationships";

if (isRelationship) {
  icon = "🤝";
  headerLabel = `关系变化 · ${pending.entity_name}`;  // entity_name = "李雷 → 韩梅"
  // 内容：proposed_value = "仇人（强度 -0.8）：李雷决心复仇..."
  // 单行展示（与 state_changes 一致，不显示 旧值/新值 diff）
}
```

### 7.4 RelationshipForm（手动新建/编辑）

- from/to 人物下拉（项目内人物列表）
- 类型文本输入
- 强度滑块（-1.0 ~ 1.0，显示当前值）
- 描述 textarea
- 编辑模式：禁用 `valid_from_chapter`（不可改——保护时序语义）
- 新建模式：`valid_from_chapter` 显示为数字输入框，默认 0（用户可改为某个已有章节 id 表示"第 N 章起生效"）
- 保存：debounce 自动保存（与 CharacterForm 同模式）

### 7.5 RelationshipHistoryPanel

- 调 `GET /api/relationships/history?from_char_id=X&to_char_id=Y`
- 按章节倒序展示所有版本
- 每条显示：`第 {valid_from} 章 → {valid_to ? "第 N 章" : "当前"} · {type}（强度 {strength}）` + change_summary
- **默认展开**（关系历史查询价值高于 character_states 轨迹）

### 7.6 hooks

```typescript
// lib/queries.ts 新增
export function useRelationships(projectId: number, opts?: { includeHistory?: boolean }) {
  return useQuery({
    queryKey: ["relationships", projectId, opts?.includeHistory ?? false],
    queryFn: () => api.listRelationships(projectId, opts),
  });
}

export function useRelationshipHistory(fromId: number | null, toId: number | null) {
  return useQuery({
    queryKey: ["relationship-history", fromId, toId],
    queryFn: () => api.getRelationshipHistory(fromId!, toId!),
    enabled: fromId != null && toId != null,
  });
}

export function useCreateRelationship() { /* useMutation + invalidate ["relationships"] */ }
export function useUpdateRelationship(id: number) { /* useMutation + invalidate */ }
export function useDeleteRelationship() { /* useMutation + invalidate */ }
export function useSoftCloseRelationship() { /* useMutation + invalidate */ }
```

**accept hook 扩展：**

```typescript
// useAcceptPendingUpdate onSuccess
if (data.target_table === "relationships") {
  qc.invalidateQueries({ queryKey: ["relationships"] });
}
```

### 7.7 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| RelationshipHistoryPanel 默认展开 | 与 CharacterStateTimeline 默认折叠不同 | 关系历史是 M3c-A 核心价值；折叠隐藏主要功能 |
| RelationshipList 只显示当前有效 | 默认参数 include_history=false | 简化主视图；历史在 history 端点查 |
| 强度滑块用原生 input range | 不引入第三方组件 | 与现有 Chip/Button 一致；YAGNI |
| From/To 下拉用项目内全部人物 | 不限"未参与过关系的" | 用户可能要新建任意两人关系 |

---

## 8. 测试策略

### 8.1 后端单元（不调 LLM）

**`tests/test_relationship_schema.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_relationship_table_columns` | 表有所有字段 |
| `test_relationship_indexes_exist` | 3 个索引存在（含部分唯一） |
| `test_relationship_partial_unique_index_enforces_current` | 直接 INSERT 第二条同方向当前有效 → IntegrityError |
| `test_relationship_partial_unique_allows_history` | 同方向已有当前有效时，INSERT valid_to 非空的历史版本 → 不冲突 |
| `test_relationship_cascade_delete_with_character` | 删人物 → 其所有关系级联删除 |

**`tests/test_extractor_prompts.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_system_prompt_has_relationship_section` | system.j2 含 relationship_changes 规则 |
| `test_user_prompt_lists_existing_relationships` | user.j2 渲染 existing_relationships |

**`tests/test_extractor_relationships.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_extract_relationship_changes_creates_soft_fact_pending` | mock LLM → 生成 pending；字段全 |
| `test_extract_relationship_changes_unknown_endpoint_skipped` | from/to 不在 existing → 跳过 |
| `test_extract_relationship_changes_self_reference_skipped` | from==to → 跳过 |
| `test_extract_relationship_changes_empty_type_skipped` | type 为空 → 跳过 |
| `test_extract_relationship_changes_strength_clamped_high` | strength=1.5 → 1.0 |
| `test_extract_relationship_changes_strength_clamped_low` | strength=-2.0 → -1.0 |
| `test_extract_relationship_changes_invalid_strength_defaults_zero` | strength="abc" → 0.0 |
| `test_extract_relationship_changes_missing_field_ok` | 不传 kwarg → 当 [] |
| `test_extract_chapter_writes_relationship_pending` | end-to-end：mock LLM → 落 pending |

**`tests/test_pending_updates.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_accept_relationship_inserts_and_soft_closes_old` | accept → INSERT 新 + UPDATE 旧 valid_to |
| `test_accept_relationship_partial_unique_holds` | accept 后 SELECT 当前有效只 1 条 |
| `test_accept_relationship_target_gone_returns_500` | 任一端人物被删 → 500 |
| `test_reject_relationship_no_db_change` | reject → 无 INSERT/UPDATE |

**`tests/test_relationships_api.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_list_relationships_default_current_only` | 默认 valid_to IS NULL |
| `test_list_relationships_include_history` | include_history=true 含历史 |
| `test_list_relationships_joins_character_names` | 响应含 from/to_char_name |
| `test_relationship_history_endpoint_desc` | /history 按章节倒序 |
| `test_relationship_history_404_when_no_data` | 无数据返回空数组（不是 404） |
| `test_create_relationship_manual_post` | 手动 POST 立即落库；valid_from 默认 0 |
| `test_create_relationship_self_reference_422` | from==to → 422 |
| `test_create_relationship_partial_unique_conflict_409` | 已有当前有效 → 409 |
| `test_update_relationship_only_allowed_fields` | PATCH 改 type/strength/desc；忽略 valid_*/from/to |
| `test_soft_close_relationship_sets_valid_to` | POST /soft-close → valid_to=指定章 |
| `test_delete_current_returns_409` | DELETE 当前有效 → 409 提示用 soft-close |
| `test_delete_history_ok` | DELETE 非当前有效 → 204 |

**`tests/test_context_assembly.py` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_assemble_populates_relationships_for_involved_pair` | 涉及人物 A、B 有当前关系 → bundle.relationships 含之 |
| `test_assemble_excludes_relationships_with_uninvolved` | A-B 当前关系，但 bundle 只涉及 A → 不含 |
| `test_assemble_excludes_history_relationships` | A-B 已软失效关系 → 不含（只查 valid_to IS NULL） |

### 8.2 前端单元

**`tests/PendingUpdateItem.test.tsx` 扩展：**

| 测试 | 验证 |
|---|---|
| `test_relationship_card_renders` | 🤝 + "关系变化 · X → Y" + proposed_value |
| `test_relationship_card_no_diff` | 不显示 旧值/新值 |

**`tests/RelationshipForm.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_form_creates_new` | 填表 → POST |
| `test_form_edit_disables_chapter_field` | 编辑模式 valid_from 禁用 |
| `test_form_strength_slider_updates` | 拖动滑块 → 强度变化 |
| `test_form_self_reference_422_error` | from==to → 错误显示 |

**`tests/RelationshipHistoryPanel.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_panel_default_expanded` | 默认展开 |
| `test_panel_renders_versions` | 展示多个版本 |
| `test_panel_empty_state` | 无历史时显示提示 |

**`tests/ActivityBar.test.tsx` 扩展（若存在）：**

| 测试 | 验证 |
|---|---|
| `test_activity_bar_has_relationship_icon` | 第 8 图标 🤝 |

### 8.3 E2E 测试

**`tests/e2e/finalize-relationship.spec.ts`：**

```
1. 创建项目 + 人物"李雷"、"韩梅"
2. 进 /relationships → 点 "+ 新建" → 建李雷→韩梅 旧友（强度 0.5）→ 列表出现
3. 创建章节"伏击" → mock LLM finalize 返回 relationship_changes（李雷→韩梅 仇人）
4. 进 /pending → 看到 🤝 关系变化卡片 → accept
5. 回 /relationships → 点李雷→韩梅 → 演变历史显示两个版本（旧友 0.5 → 仇人 -0.8）
6. 当前关系列表显示仇人版本（旧友被软失效）
```

### 8.4 YAGNI 不测

- LLM 真实 API
- 关系图可视化
- 跨章节关系冲突检测（→ M4 Reviewer）
- 多用户并发

### 8.5 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/memory/schema.py` (Relationship) | 100% |
| `app/agents/extractor.py` (relationship_changes 分支) | >90% |
| `app/api/pending_updates.py` (relationships accept 分支) | >90% |
| `app/api/relationships.py` | >85% |
| `app/memory/retrieval.py` (relationships 注入) | >85% |
| `app/llm/prompts/extractor/*.j2` | 100%（渲染） |
| 前端 `RelationshipForm` + `RelationshipHistoryPanel` + `PendingUpdateItem` | >85% |

---

## 9. M3c-A 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | finalize 后 `pending_updates` 含 `target_table='relationships'` 记录 | sqlite3 直查 |
| 2 | 生成的 pending `auto=0` | sqlite3 直查 |
| 3 | 重抽覆盖 status='pending' 的旧 relationship_changes | 单测 + 手工 |
| 4 | accept → INSERT 新关系 + UPDATE 旧关系 `valid_to=新关系valid_from`（同事务） | sqlite3 直查 |
| 5 | accept 后部分唯一索引保证同方向只有一条当前有效 | 单测 |
| 6 | reject → 无 DB 变化 | 单测 |
| 7 | LLM 返回缺 relationship_changes → 当作空数组，summary + entities + state_changes 仍写 | 单测 |
| 8 | 任一端人物不在 existing → 跳过 + warning 入 generation_logs | 单测 |
| 9 | `from == to`（自指）→ 跳过 | 单测 |
| 10 | strength 越界 → 裁剪到 [-1.0, 1.0] | 单测 |
| 11 | strength 非数字 → 默认 0.0 | 单测 |
| 12 | `GET /api/relationships?project_id=X` 默认返回当前有效 | curl + 单测 |
| 13 | `GET /api/relationships?include_history=true` 含历史 | curl + 单测 |
| 14 | `GET /api/relationships/history?from=X&to=Y` 按章节倒序 | curl + 单测 |
| 15 | 手动 POST 关系立即落库（valid_from 默认 0） | curl + 单测 |
| 16 | 手动 POST 同方向重复当前有效 → 409 | 单测 |
| 17 | 手动 POST from==to → 422 | 单测 |
| 18 | PATCH 只改 type/strength/description；不允许改 valid_*/from/to | 单测 |
| 19 | soft-close 端点把 valid_to 设为指定章 | 单测 |
| 20 | DELETE 当前有效 → 409；DELETE 历史版本 → 204 | 单测 |
| 21 | assemble_context 把涉及人物两两当前关系填入 ContextBundle | 单测 |
| 22 | assemble_context 不含未涉及人物的关系 | 单测 |
| 23 | writer/user.j2 渲染关系段（M2a 已有，复用） | 手工 + 集成测试 |
| 24 | ActivityBar 🤝 第 8 图标 | 手工 |
| 25 | /relationships 页面：列表 + 新建 + 编辑 + 历史折叠区 | 手工 + E2E |
| 26 | PendingUpdateItem 🤝 关系卡片正确渲染 | 单测 + E2E |
| 27 | accept 后 invalidate `["relationships"]`，UI 刷新 | 手工 |
| 28 | generation_logs 审计记录含完整 prompt（含 relationship_changes 规则） | sqlite3 直查 |
| 29 | 全后端测试通过（除预存 M3b batch 失败） | `pytest -v` |
| 30 | 全前端测试通过 | `npm test` |
| 31 | 全 E2E 通过 | `npm run test:e2e` |

---

## 10. 待定 / 开放问题

1. **同章多对人物关系变化**：LLM 可能一次返回多条 relationship_changes（A→B 仇人 + C→D 联盟）——当前设计：都生成 pending，用户分别 accept/reject。无歧义。

2. **同一对人物同章多次变化**：LLM 可能返回两条 from=A,to=B 的变化（中段决裂 + 结尾和解）——当前设计：两条都生成 pending。Accept 顺序敏感：先 accept 的 INSERT + 软失效现有；第二条 accept 时会再次软失效（刚 INSERT 的那条）+ INSERT 新的。**结果**：第一条 INSERT 的关系 valid_to 被设为第二条的 valid_from，可能等于本章 chapter_id（同章）。这是合法的"瞬间有效"边界情况，部分唯一索引仍能保证不变式。**倾向允许**——append-only 语义。用户可通过 reject 跳过其中一条。

3. **retrieval 注入的 token 预算**：常驻层若涉及 5 个人物（10 对方向），可能注入 10 条关系 ≈ 200-300 tokens。可接受。M3c-C+ 再考虑 ContextBudget 自动裁剪。

4. **手动新建后立即被 Extractor 抽出新变化**：用户先建 A→B 旧友（手动），然后 finalize 第 1 章 LLM 抽出 A→B 仇人——accept 时手动建的关系会被软失效（valid_to=1）。这是预期行为（用户 accept 即同意关系变化）。**倾向当前处理**。

5. **DELETE 当前有效返回 409 是否过严**：用户可能确实想物理删除（误建）。替代方案：DELETE 任何时候都允许，但加 confirm 对话框。**倾向 409**——保护历史完整性，软失效是更安全的选择。

---

## 11. 未来扩展（v2+，不在 M3c-A 范围）

- **M3c-C 伏笔标注**：events 表 + foreshadows/payoff_of 双向 JSON 引用
- **M3c-D plot_lines 状态流转**：plot_lines 表 + 章节关联
- **M3d 否定记忆**：reject 时记签名，下次抽取 prompt 提示"以下已被拒绝"
- **M3e 异步抽取**：finalize 走任务队列 + SSE 进度
- **M4 Reviewer**：基于 relationships 时序检测"关系合理性"冲突（如"第 5 章决裂，第 7 章却和谐如初无解释"）
- **关系图可视化**：独立 `/relationships/graph` 页面，D3/React-flow 力导向图
- **双向关系聚合 UI**：选项 C（存储单向 + UI 合并）的实现
- **关系强度可视化轨迹**：随章节变化的折线图
