# NovelAI M3a — 章节摘要 + 硬事实抽取设计文档

- **日期**：2026-06-19
- **状态**：草案（待用户审阅）
- **范围**：M3a = 章节摘要生成 + 新实体/描述补充抽取 + pending_updates 面板
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）已完成

---

## 1. 目标与非目标

### 1.1 目标

让 AI 能"记住"章节里**首次出现的新实体**和**对已有实体的细节补充**。具体：

1. 用户在章节工作区点 **"完成本章"** 按钮触发 Extractor Agent
2. 一次 LLM 调用同时返回：**章节摘要**（200-400 字）+ **抽取的实体变更**（结构化 JSON）
3. 抽取结果写入 `pending_updates` 队列（不直接落库）
4. 用户在 `/projects/[id]/pending` 面板逐条 **accept / reject**
5. accept 时按变更类型 INSERT 新实体或 PATCH 已有实体；reject 仅标记 status

### 1.2 非目标（M3a 不做）

- 软事实抽取（关系演变、情绪变化、状态时序）— M3c
- 向量检索 / 语义搜索 — M3b
- 伏笔/呼应自动标注 — M3c
- 异步任务队列（Celery / Background tasks）— 同步等几秒
- LLM 真实 API 集成测试 — 全部 mock
- `pending_updates` 表的 Alembic 迁移 — drop & recreate（沿用 M2a/M2b 策略）

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 触发方式 | 手动"完成本章"按钮 | 与原 spec §4.4 一致；用户控制成本 |
| 抽取粒度 | 名字 + 类型 + 一句话描述 | 平衡信息量与 prompt 复杂度 |
| LLM 模型 | 复用现有 `extractor` task 路由（env 配置） | router 已预留 task 位置 |
| 抽取范围 | 新实体 + 已有实体的描述补充（CREATE + UPDATE 两种 pending_update 类型） | 让 accept 后立即可用 |
| UI 位置 | 新页面 `/projects/[id]/pending` + ActivityBar 加 📋 第 7 图标 | 与现有项目内页面一致 |
| 状态流转 | 任意 status 可点；重抽覆盖 status='pending' 的旧记录 | 不引入中间态，简单 |
| LLM 调用粒度 | 一次调用同时返回 summary + entities | 便宜快；解析失败则整个回滚 |
| Finalize 同步性 | 同步（客户端等几秒） | 不引入任务队列 |
| `pending_updates` 表 | 独立表，不直接改 characters/lore | reject 时无副作用 |
| 复用 generation_logs | 抽取调用也写 generation_logs（model_task='extractor'） | 沿用 M2a 审计表 |

---

## 2. 模块划分与文件结构

```
app/
├── api/
│   ├── chapters_finalize.py        # 新增：POST /api/chapters/{id}/finalize（同步触发抽取）
│   └── pending_updates.py          # 新增：GET list / GET detail / POST accept / POST reject
├── agents/
│   └── extractor.py                # 新增：Extractor Agent 编排
├── memory/
│   ├── schema.py                   # 修改：加 PendingUpdate 表
│   └── errors.py                   # 新增：ExtractionError
├── llm/
│   └── prompts/
│       └── extractor/
│           ├── system.j2           # 新增：抽取 system prompt
│           └── user.j2             # 新增：抽取 user prompt（含现有实体上下文）
└── models/
    ├── chapter.py                  # 不变（status/summary/content_hash 字段已存在）
    └── pending.py                  # 新增：PendingUpdate Pydantic schemas

web/
├── app/projects/[projectId]/
│   └── pending/page.tsx            # 新增：pending_updates 面板页
├── components/
│   ├── layout/ActivityBar.tsx      # 修改：加 📋 第 7 个图标 + pending 数量 badge
│   ├── entities/
│   │   └── PendingUpdateItem.tsx   # 新增：单条 pending 卡片（自包含 accept/reject）
│   └── editor/
│       ├── FinalizeButton.tsx      # 新增：章节顶部"完成本章"按钮 + 抽取进度
│       └── EditorToolbar.tsx       # 修改：加 extraActions slot
└── lib/
    ├── api.ts                      # 修改：加 list/detail/accept/reject 端点
    ├── queries.ts                  # 修改：加 usePendingUpdates / useAcceptPending / useRejectPending
    └── types.ts                    # 修改：加 PendingUpdate / PendingUpdateRead / PendingUpdateDetail

tests/（后端）
├── test_extractor_prompts.py
├── test_extractor_agent.py
├── test_chapters_finalize.py
└── test_pending_updates.py

web/tests/（前端）
├── FinalizeButton.test.tsx
├── PendingUpdateItem.test.tsx
└── e2e/
    ├── finalize-pending.spec.ts
    └── refinalize-overwrites.spec.ts
```

### 2.1 职责边界

- `agents/extractor.py`：编排器。组装 prompt（含现有实体上下文）→ 调 `default_router.complete` → 解析 JSON → 写 chapter.summary + 批量 INSERT pending_updates（事务）
- `api/chapters_finalize.py`：薄包装。校验 chapter 存在 → 调 extractor → 把异常映射到 HTTP 状态
- `api/pending_updates.py`：list + detail + accept（按 target_table INSERT 或 PATCH）+ reject（status 改 rejected）

### 2.2 依赖方向

沿用 M2a 单向依赖：`api → agents → memory → llm → DB`。

---

## 3. 数据库变更

### 3.1 新增表：`pending_updates`

```sql
pending_updates(
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,

  -- 变更类型
  update_type VARCHAR(20) NOT NULL,    -- 'hard_fact'（M3a 全是这种；预留 soft_fact/foreshadow 给 M3c）
  operation VARCHAR(10) NOT NULL,      -- 'create' / 'update'
  target_table VARCHAR(50) NOT NULL,   -- 'characters' / 'lore_entries'
  target_id INTEGER,                   -- null=新建；非 null=更新已有实体

  -- 变更内容（JSON）
  proposed_change JSON NOT NULL,       -- 见下方"proposed_change 结构"
  reason TEXT DEFAULT '',              -- AI 给出的抽取理由（"出现在第 3 段，与李雷对话"）

  -- 抽取元数据
  auto BOOLEAN DEFAULT TRUE,           -- M3a 全是 auto=true（硬事实）
  extractor_model VARCHAR(100),        -- 抽取时用的模型（审计）
  extractor_log_id INTEGER,            -- 关联 generation_logs（可空，复用审计表）

  -- 状态
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- pending / accepted / rejected

  -- 用户操作记录
  decided_at DATETIME,
  decision_note TEXT DEFAULT '',        -- 用户 reject 时的备注（可空）

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
)

-- 索引：按项目 + 状态查（pending_updates 面板常用）
CREATE INDEX idx_pending_project_status ON pending_updates(project_id, status);
CREATE INDEX idx_pending_chapter ON pending_updates(chapter_id);
```

### 3.2 `proposed_change` JSON 结构

按 `operation` + `target_table` 组合，固定 4 种 shape：

**`{operation: 'create', target_table: 'characters'}`：**
```json
{
  "name": "韩梅",
  "role": "supporting",
  "description": "李雷旧友，酒馆老板娘，约 30 岁"
}
```

**`{operation: 'update', target_table: 'characters'}`：**
```json
{
  "name": "李雷",
  "field": "background",
  "old_value": "南方孤儿",
  "new_value": "南方孤儿，曾在青石城守夜人服役"
}
```

**`{operation: 'create', target_table: 'lore_entries'}`：**
```json
{
  "type": "location",
  "name": "残月酒馆",
  "description": "青石城南门附近的小酒馆，韩梅经营"
}
```

**`{operation: 'update', target_table: 'lore_entries'}`：**
```json
{
  "name": "青石城",
  "field": "description",
  "old_value": "王国首都",
  "new_value": "王国首都，城墙青黑色，南门临近商队区"
}
```

### 3.3 Chapter 字段

M3a 不动 Chapter schema。复用现有字段：
- `status`：'draft' / 'writing' / 'final'（"完成本章"按钮把任意状态改为 'final'）
- `summary`：抽取时 UPDATE 这个字段
- `content_hash`：抽取前算一次 SHA-256(content) 存入，便于 M3b 检测定稿后是否被改动

### 3.4 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| `pending_updates` 独立表 | 不直接写 characters / lore_entries | 用户必须显式 accept；reject 时无副作用 |
| `target_id` 可空 | null 表示 create | 同一表统一存储 create/update |
| 重抽覆盖 | finalize 前 DELETE 该 chapter 所有 status='pending' 的记录 | 用户已 accept/reject 的保留（status 不是 pending） |
| `proposed_change` JSON | 4 种 shape 由 `operation`+`target_table` 决定 | 类型安全；accept 时按 shape 决定 INSERT/PATCH |
| `extractor_log_id` 关联 generation_logs | 复用 M2a 审计表 | 抽取也是 LLM 调用，应可审计；prompt + response 都进 generation_logs |
| `decision_note` | 用户 reject 时可选填理由 | 为 M3c "否定记忆"做准备（M3a 不读这个字段） |
| 迁移策略 | drop & recreate（沿用 M2a/M2b 策略） | 本地无生产数据；Alembic 留到首次需要保留数据时 |

---

## 4. Extractor Agent 设计

### 4.1 接口契约

```python
# app/agents/extractor.py

@dataclass
class ExtractionResult:
    chapter_id: int
    summary: str                    # 写入 chapter.summary
    pending_created: int            # 写入 pending_updates 的条数
    log_id: int                     # generation_logs 记录 ID（审计）

def extract_chapter(
    db: Session,
    *,
    chapter_id: int,
    router: ModelRouter = default_router,
) -> ExtractionResult:
    """
    触发抽取。原子事务：
    1. 加载 chapter + project + 现有 entities（characters + lore_entries）
    2. 渲染 extractor prompt
    3. 调 LLM（extractor task）
    4. 解析 JSON（失败抛 ExtractionError）
    5. 事务内：
       a. DELETE 该 chapter 旧 status='pending' 的 pending_updates
       b. UPDATE chapter.summary + content_hash + status='final'
       c. INSERT 新 pending_updates
       d. INSERT generation_logs（审计）
    6. 提交事务

    任一步失败 → 整个事务回滚。chapter.summary / status 都不变。
    """
```

### 4.2 LLM 响应格式

要求 LLM 严格输出以下 JSON（system prompt 强约束 + 示例）：

```json
{
  "summary": "李雷推开残月酒馆的门，遇见多年未见的韩梅...",
  "entities": {
    "new_characters": [
      {"name": "韩梅", "role": "supporting", "description": "李雷旧友，酒馆老板娘"}
    ],
    "updated_characters": [
      {"name": "李雷", "field": "background", "new_value": "南方孤儿，曾在守夜人服役"}
    ],
    "new_lore": [
      {"type": "location", "name": "残月酒馆", "description": "青石城南门小酒馆"}
    ],
    "updated_lore": [
      {"name": "青石城", "field": "description", "new_value": "王国首都，城墙青黑色"}
    ]
  }
}
```

**解析失败处理：**

- JSON parse 错 → 抛 `ExtractionError("invalid JSON from LLM: ...")`
- 缺 `summary` 字段 → 抛 `ExtractionError`
- 缺 `entities` → 当作空 entities（容错，summary 仍保留）
- `role` 不在 `protagonist/supporting/antagonist/extra` 枚举 → 默认 `extra`
- `type` 不在 LoreType 枚举 → 跳过该条
- 名字为空字符串 → 跳过该条

### 4.3 Prompt 模板

**`extractor/system.j2`：**

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
严格输出 JSON，结构如下。不要输出任何 JSON 之外的内容。

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

**`extractor/user.j2`：**

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

### 4.4 调用流程

```python
def extract_chapter(db, *, chapter_id, router=default_router):
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
        temperature=0.1,   # 抽取要稳定
    )

    # 同步调用（不是 stream）
    provider_name, model_name = router.resolve_model("extractor")
    response = router.complete(request)

    # 解析 JSON
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"LLM 返回非 JSON: {e}; response={response.text[:500]}")

    summary = parsed.get("summary", "").strip()
    if not summary:
        raise ExtractionError("LLM 返回缺 summary 字段")

    # 写 generation_logs（审计）
    log = GenerationLog(
        chapter_id=chapter_id,
        project_id=chapter.project_id,
        beat_text="(extraction)",
        instruction="",
        involved_character_ids=[],
        location_id=None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_summary={"existing_chars": len(existing_characters), "existing_lore": len(existing_lore)},
        generated_text=response.text,
        model=model_name,
        model_task="extractor",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        stop_reason=response.stop_reason,
        status="done",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )

    # 计算新的 content_hash
    new_hash = hashlib.sha256(chapter.content.encode()).hexdigest()

    # 解析 entities → pending_updates
    pending_rows = _build_pending_rows(
        parsed.get("entities", {}),
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        model_name=model_name,
    )

    # 事务
    try:
        # 1. 写 log（拿 ID）
        db.add(log)
        db.flush()
        for p in pending_rows:
            p.extractor_log_id = log.id

        # 2. 删旧 pending
        db.execute(delete(PendingUpdate).where(
            PendingUpdate.chapter_id == chapter_id,
            PendingUpdate.status == "pending",
        ))

        # 3. 写新 pending
        for p in pending_rows:
            db.add(p)

        # 4. 更新 chapter
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

### 4.5 `_build_pending_rows` 逻辑

把 LLM 返回的 4 类实体转成 PendingUpdate ORM 行：

| LLM 返回 | operation | target_table | target_id | proposed_change |
|---|---|---|---|---|
| new_characters | create | characters | null | `{name, role, description}` |
| updated_characters | update | characters | 按名字查 existing | `{name, field, old_value, new_value}` |
| new_lore | create | lore_entries | null | `{type, name, description}` |
| updated_lore | update | lore_entries | 按名字查 existing | `{name, field, old_value, new_value}` |

**查不到已有实体（按名字）**：

- updated_characters/updated_lore 中的 name 不在 existing → 跳过（LLM 幻觉）
- 不报错，记 warning 到 generation_logs.context_summary 后续字段

### 4.6 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| `temperature=0.1` | 抽取要稳 | 减少非确定性；重抽时减少差异 |
| `max_tokens=4096` | 输出限制 | 长 chapter + 多 entities 可能 2-3k tokens |
| 单次 LLM 调用 | 不分 summary + entities 两次 | 便宜快；失败时整体回滚（接受这个权衡） |
| 容忍解析错误 | unknown role → 'extra'；unknown type → 跳过；empty name → 跳过 | 不让单条错误废掉整批 |
| 复用 `generation_logs` | `beat_text="(extraction)"` 标记 | 沿用 M2a 表，不加新表 |

---

## 5. API 契约

### 5.1 端点列表

```
POST   /api/chapters/{chapter_id}/finalize              # 触发抽取（同步）
GET    /api/pending-updates?project_id=X&status=pending  # 列表
GET    /api/pending-updates/{id}                         # 详情
POST   /api/pending-updates/{id}/accept                  # 应用变更到 DB
POST   /api/pending-updates/{id}/reject                  # 标记拒绝
```

### 5.2 Finalize 请求/响应

**请求：**

```
POST /api/chapters/42/finalize
Content-Type: application/json

{}  # 无 body 参数；保留以便未来扩展
```

**响应矩阵：**

| 情形 | HTTP | Body |
|---|---|---|
| 成功 | 200 | `{"chapter_id": 42, "summary": "李雷推开...", "pending_created": 5, "log_id": 78}` |
| 章节不存在 | 404 | `{"detail": "chapter not found"}` |
| LLM 调用失败 | 502 | `{"detail": "llm call failed: ..."}` |
| JSON 解析失败 | 422 | `{"detail": {"error": "extraction_failed", "reason": "invalid JSON", "raw": "..."}}` |
| 抽取异常（DB 等） | 500 | `{"detail": "internal error"}` |

**关键决策：**

- **同步**：客户端等 LLM 完成（~3-8s）。不用任务队列。
- **idempotent**：重复 finalize 同一章节 → 重抽覆盖（删旧 pending、生成新的）。
- **错误时**：chapter.summary / status 不变（事务回滚）。

### 5.3 PendingUpdate list 端点

```
GET /api/pending-updates?project_id=1&status=pending&limit=50&offset=0
```

| Query | 必填 | 默认 | 说明 |
|---|---|---|---|
| `project_id` | 是 | — | 必填，按项目隔离 |
| `status` | 否 | `pending` | `pending` / `accepted` / `rejected` / `all` |
| `chapter_id` | 否 | — | 可选章节过滤 |
| `limit` | 否 | 50 | 最大 200 |
| `offset` | 否 | 0 | 分页 |

**响应：** `list[PendingUpdateRead]`（不含 `proposed_change` 全文，仅摘要字段）

```python
class PendingUpdateRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    chapter_id: int
    update_type: str           # 'hard_fact'
    operation: str             # 'create' / 'update'
    target_table: str          # 'characters' / 'lore_entries'
    target_id: int | None
    reason: str
    status: str
    # 摘要字段（list 视图友好，后端从 proposed_change JSON 提取）
    entity_name: str           # proposed_change["name"]
    entity_type: str           # proposed_change["type"] for lore_create, "" otherwise
    field_name: str            # proposed_change["field"] for update ops, "" for create
    old_value: str             # proposed_change["old_value"] for update ops, "" for create
    proposed_value: str        # description (for create) 或 new_value (for update)
```

### 5.4 PendingUpdate detail 端点

```
GET /api/pending-updates/{id}
```

**响应：** `PendingUpdateDetail`（含 `proposed_change` 完整 JSON + 关联章节标题 + 关联实体名）

```python
class PendingUpdateDetail(PendingUpdateRead):
    proposed_change: dict
    decision_note: str
    decided_at: datetime | None
    extractor_model: str | None
    extractor_log_id: int | None
    # 关联实体上下文
    chapter_title: str
    target_entity_name: str | None   # target_id 不为空时，按表查名字
```

### 5.5 Accept 端点

```
POST /api/pending-updates/{id}/accept
```

**逻辑：**

```python
pending = db.get(PendingUpdate, id)
if pending is None: raise 404
if pending.status != "pending": raise 409("already decided")

try:
    if pending.operation == "create":
        if pending.target_table == "characters":
            data = pending.proposed_change
            char = Character(
                project_id=pending.project_id,
                name=data["name"],
                role=data.get("role", "extra"),
                background=data.get("description", ""),
            )
            db.add(char)
        elif pending.target_table == "lore_entries":
            data = pending.proposed_change
            lore = LoreEntry(
                project_id=pending.project_id,
                type=data["type"],
                name=data["name"],
                description=data.get("description", ""),
            )
            db.add(lore)

    elif pending.operation == "update":
        if pending.target_id is None:
            raise 500("update pending without target_id")
        data = pending.proposed_change
        if pending.target_table == "characters":
            char = db.get(Character, pending.target_id)
            if char is None: raise 404("target character gone")
            setattr(char, data["field"], data["new_value"])
        elif pending.target_table == "lore_entries":
            lore = db.get(LoreEntry, pending.target_id)
            if lore is None: raise 404("target lore gone")
            setattr(lore, data["field"], data["new_value"])

    pending.status = "accepted"
    pending.decided_at = datetime.now(UTC)
    db.commit()
    return PendingUpdateRead.from_orm(pending)

except Exception:
    db.rollback()
    raise
```

**响应：** 200 + `PendingUpdateRead`（status='accepted'）

**错误：**

- 404 pending 不存在
- 409 已 accept/reject 过
- 500 target 实体已被删 / proposed_change 字段缺失

### 5.6 Reject 端点

```
POST /api/pending-updates/{id}/reject
Content-Type: application/json

{"note": "可选，用户填的理由"}
```

**逻辑：**

- pending.status = 'rejected'
- pending.decision_note = note
- pending.decided_at = now
- 不动 target 实体（不存在或保持原样）

**响应：** 200 + `PendingUpdateRead`（status='rejected'）

### 5.7 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| `/finalize` 同步 vs 异步 | 同步 | 简单；客户端等几秒可接受；不引入任务队列 |
| list 强制 project_id | 沿用 M2a logs 端点模式 | 防跨项目泄漏 |
| `entity_name` / `proposed_value` 摘要字段 | 后端从 JSON 提取 | list 视图不需要前端解 JSON |
| accept/reject 返回完整 Read | 不返回 Detail | 调用方一般已有上下文 |
| 不加 DELETE / PATCH | pending 不可改、不删 | 数据量小，留作历史；用户改变主意只能新建 |
| finalize 不返回 pending 列表 | 客户端 invalidate 自己刷 | 解耦；finalize 响应保持小 |

---

## 6. 前端 UI 与数据流

### 6.1 FinalizeButton（章节顶部）

放在 `EditorToolbar` 右侧，紧挨字数和删除按钮：

```
┌─────────────────────────────────────────────────────────────────┐
│ 第二章                                          798 字  🗑️  ✓ 完成本章 │
└─────────────────────────────────────────────────────────────────┘
```

**状态机：**

- `idle`：按钮显示 `✓ 完成本章`
- `finalizing`：按钮 disabled，显示 `⏳ 抽取中...`（spinner icon）
- `done`：按钮变成 `↻ 重新抽取`（章节已是 final 状态）
- `error`：toast 报错，按钮回到 idle

```typescript
// components/editor/FinalizeButton.tsx
"use client";

export function FinalizeButton({ chapterId, isFinal }: { chapterId: number; isFinal: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [state, setState] = useState<"idle" | "finalizing">("idle");

  const handleFinalize = async () => {
    setState("finalizing");
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/chapters/${chapterId}/finalize`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail?.reason || err.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      toast(`已抽取 ${data.pending_created} 条新事实，摘要已生成`, "success");
      // 章节状态变了；强制刷新所有相关 query
      qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
      qc.invalidateQueries({ queryKey: ["chapters"] });
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
    } catch (e) {
      toast(`抽取失败: ${(e as Error).message}`, "error");
    } finally {
      setState("idle");
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleFinalize}
      disabled={state === "finalizing"}
    >
      {state === "finalizing"
        ? "⏳ 抽取中..."
        : isFinal
        ? "↻ 重新抽取"
        : "✓ 完成本章"}
    </Button>
  );
}
```

`EditorToolbar` 新增 `extraActions?: ReactNode` slot，`ChapterEditor` 传 `<FinalizeButton chapterId={chapter.id} isFinal={chapter.status === "final"} />` 进去。

### 6.2 ActivityBar 加 📋 图标（第 7 个）

```typescript
const ITEMS = [
  { icon: "🏠", label: "项目列表", path: "__HOME__", isHome: true },
  // — divider —
  { icon: "📚", label: "章节", path: "chapters" },
  { icon: "👥", label: "人物", path: "characters" },
  { icon: "🌍", label: "设定", path: "lore" },
  { icon: "📜", label: "历史", path: "history" },
  { icon: "📋", label: "待处理", path: "pending" },   // 新增
  { icon: "🔍", label: "搜索", path: "search" },
];
```

带 pending 数量 badge（红点 + 数字）：

```typescript
// 在 ActivityBar 内
const { data: pendingCount } = usePendingCount(projectId);
// 渲染时
{it.path === "pending" && pendingCount && pendingCount > 0 && (
  <span className="absolute -top-0.5 -right-0.5 bg-red-600 text-white text-[9px] px-1 rounded-full leading-tight">
    {pendingCount > 99 ? "99+" : pendingCount}
  </span>
)}
```

`usePendingCount` 是个轻量 query（复用 list 端点的 length 字段，limit=1 只取计数）。

### 6.3 PendingUpdates 面板页（`/projects/[id]/pending`）

复用 `ChapterWorkspaceGrid` 布局：左侧 SidePanel 过滤器 + 右侧卡片列表。

```
┌──────────────────────────────────────────────────────────────────┐
│🏠│  待处理 (5)                              [全部 ▾] [× 章节 ▾]    │  ← SidePanel header
│  │──────────────────────────────────────────────────────────────│
│📚│  第二章 · 抽取于 2 分钟前                                    │
│👥│  ┌────────────────────────────────────────────────────────┐ │
│🌍│  │ ✏️ 新人物 · 韩梅                                          │ │
│📜│  │   supporting · 描述："李雷旧友，酒馆老板娘"               │ │
│📋│  │   理由：第 3 段首次出现，与李雷对话                       │ │
│🔍│  │   [✓ 接受]  [✗ 拒绝]                                     │ │
│🌙│  └────────────────────────────────────────────────────────┘ │
│  │                                                              │
│  │  第二章 · 抽取于 2 分钟前                                    │
│  │  ┌────────────────────────────────────────────────────────┐ │
│  │  │ 🔄 更新人物 · 李雷 · background                          │ │
│  │  │   旧值：南方孤儿                                          │ │
│  │  │   新值：南方孤儿，曾在守夜人服役                          │ │
│  │  │   理由：第 5 段提到从军经历                               │ │
│  │  │   [✓ 接受]  [✗ 拒绝]                                     │ │
│  │  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**SidePanel 过滤器（顶部）：**

- 状态 tabs：`待处理 (5)` / `全部` / `已接受` / `已拒绝`
- 章节下拉（可按章节过滤）

**主区（PendingUpdateItem 卡片）：**

```typescript
function PendingUpdateItem({ pending }: { pending: PendingUpdateRead }) {
  const accept = useAcceptPendingUpdate();
  const reject = useRejectPendingUpdate();
  return (
    <div className="bg-panel border border-line rounded p-3 mb-2">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span>{pending.operation === "create" ? "✏️" : "🔄"}</span>
          <span className="text-sm">
            {pending.operation === "create" ? "新建" : "更新"}
            {pending.target_table === "characters" ? "人物" : "设定"} ·
            <strong>{pending.entity_name}</strong>
          </span>
        </div>
        <span className="text-xs text-text-dim">
          {pending.target_table === "lore_entries" && `[${pending.entity_type}]`}
        </span>
      </div>

      {/* 内容预览 */}
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

      {/* 操作 */}
      {pending.status === "pending" ? (
        <div className="flex gap-2 pl-6">
          <Button variant="primary" onClick={() => accept.mutate(pending.id)}>✓ 接受</Button>
          <Button variant="ghost" onClick={() => {
            const note = prompt("拒绝理由（可选）");
            reject.mutate({ id: pending.id, note: note ?? "" });
          }}>✗ 拒绝</Button>
        </div>
      ) : (
        <div className="text-xs pl-6 text-text-dim">
          已{pending.status === "accepted" ? "接受" : "拒绝"}
          {pending.decided_at && ` · ${formatTime(pending.decided_at)}`}
        </div>
      )}
    </div>
  );
}
```

### 6.4 数据流（前端 hooks）

```typescript
// lib/queries.ts 新增

export function usePendingUpdates(
  projectId: number,
  status: "pending" | "all" | "accepted" | "rejected" = "pending",
  chapterId?: number
) {
  return useQuery({
    queryKey: ["pending-updates", projectId, status, chapterId],
    queryFn: () => api.listPendingUpdates({ project_id: projectId, status, chapter_id: chapterId }),
  });
}

export function usePendingCount(projectId: number) {
  // 复用 list query 的 length 字段（limit=1 偷懒；如果性能有问题加独立 count 端点）
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
    staleTime: 5_000,  // 5 秒内不重复请求
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

### 6.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| FinalizeButton 放 EditorToolbar 右侧 | 紧挨字数 + 删除 | 用户编辑章节时一键完成 |
| 重新抽取（status=final 状态下） | 按钮文案改 `↻ 重新抽取`，行为一致（重抽覆盖） | § 1.3 已决议 |
| PendingUpdates 不分页 | limit=200 一次拉 | 单机用户量小，简化 |
| PendingUpdateItem 卡片自包含 accept/reject | 不跳详情页 | 一次看完所有字段，减少点击 |
| reject 不强制填理由 | prompt() 可空 | 用户可能只是"这条不准" |
| ActivityBar badge 实时更新 | accept/reject 后 invalidate count | 用 query key 失效自动刷 |
| FinalizeButton 用 fetch 不用 mutation hook | 不经过 TanStack Query | 单次调用，进度局部状态足够；不污染全局 mutation 缓存 |
| 章节工作区不显示 "N 条 pending" 提示 | 仅 ActivityBar badge | 避免重复提示 |

---

## 7. 测试策略

### 7.1 测试金字塔

```
                ┌─────────────────┐
                │ Playwright E2E  │  2 个，覆盖 finalize → accept 流
                └─────────────────┘
            ┌─────────────────────────┐
            │ Agent + API 集成测试    │  mock LLM，验抽取事务和 accept/reject 流
            └─────────────────────────┘
        ┌───────────────────────────────┐
        │ 单元测试（prompt 模板）       │  StrictUndefined 完整渲染
        └───────────────────────────────┘
```

### 7.2 后端单元测试（不调 LLM）

**`tests/test_extractor_prompts.py`**：

| 测试 | 验证 |
|---|---|
| `test_render_extractor_system` | system.j2 渲染不抛错 |
| `test_render_extractor_user_full` | user.j2 含 project + chapter + 现有实体 |
| `test_render_extractor_user_minimal` | 现有实体为空时不抛错（空 for 循环） |
| `test_render_extractor_user_missing_var_raises` | StrictUndefined 缺变量时报错 |

### 7.3 Agent 集成测试（mock LLMProvider）

**`tests/test_extractor_agent.py`**：

| 测试 | 验证 |
|---|---|
| `test_extract_creates_summary_and_pending` | mock LLM 返回完整 JSON → chapter.summary/status 更新；pending 入库 |
| `test_extract_no_entities` | mock LLM 返回空 entities → summary 仍写入；pending 0 条 |
| `test_extract_invalid_json_rolls_back` | mock LLM 返回非 JSON → 抛 ExtractionError；chapter.summary/status 不变；无 pending |
| `test_extract_missing_summary_raises` | mock LLM 返回缺 summary → 抛 ExtractionError |
| `test_extract_unknown_role_defaults_extra` | role="主角"（非枚举）→ proposed_change.role="extra" |
| `test_extract_unknown_lore_type_skipped` | type="dynasty"（非枚举）→ 跳过该条，其余正常 |
| `test_extract_empty_name_skipped` | name="" → 跳过 |
| `test_extract_update_existing_resolves_target_id` | updated_characters 里 name 匹配 existing → target_id 填好 |
| `test_extract_update_unknown_name_skipped` | updated_characters 里 name 不在 existing → 跳过（不报错） |
| `test_extract_rerun_deletes_old_pending` | 两次抽取，第二次前 DELETE status='pending' 的；accepted/rejected 保留 |
| `test_extract_writes_generation_log` | generation_logs 表有 extractor 记录，含完整 prompt + response |
| `test_extract_chapter_not_found` | chapter_id=99999 → ChapterNotFoundError |

### 7.4 API 测试

**`tests/test_chapters_finalize.py`**：

| 测试 | 验证 |
|---|---|
| `test_finalize_returns_404_unknown_chapter` | 章节不存在 |
| `test_finalize_success` | mock router → 200 + summary + pending_created + log_id |
| `test_finalize_llm_failure_returns_502` | mock router raise → 502 |
| `test_finalize_invalid_json_returns_422` | mock router 返回非 JSON → 422 含 raw |
| `test_finalize_idempotent` | 两次连续 finalize → 第二次重抽覆盖；accepted 的旧 pending 不动 |

**`tests/test_pending_updates.py`**：

| 测试 | 验证 |
|---|---|
| `test_list_requires_project_id` | 缺 project_id → 422 |
| `test_list_status_filter` | status=pending 不返回 accepted/rejected |
| `test_list_chapter_filter` | chapter_id 过滤 |
| `test_detail_returns_full_proposed_change` | 详情含 proposed_change JSON |
| `test_detail_404_unknown` | id 不存在 → 404 |
| `test_accept_create_character` | accept 一条 create characters → 人物表新增；pending.status='accepted' |
| `test_accept_create_lore` | accept 一条 create lore → lore_entries 新增 |
| `test_accept_update_character` | accept 一条 update characters → 人物字段更新 |
| `test_accept_update_lore` | accept 一条 update lore_entries → lore 字段更新 |
| `test_accept_target_gone_returns_500` | target_id 已被删 → 500 |
| `test_accept_already_decided_returns_409` | 二次 accept → 409 |
| `test_reject_marks_status` | reject → status='rejected'；note 存储；不动 target |
| `test_reject_with_note` | note 字段被持久化 |

### 7.5 前端单元测试

**`tests/FinalizeButton.test.tsx`**：

| 测试 | 验证 |
|---|---|
| `test_button_idle_text` | 默认显示 "✓ 完成本章" |
| `test_final_state_shows_refinalize` | isFinal=true 显示 "↻ 重新抽取" |
| `test_button_disabled_during_finalizing` | 点击后 disabled + 文案变 "⏳ 抽取中..." |
| `test_success_toast_shows_pending_count` | 200 响应 → toast 显示 "已抽取 N 条新事实" |
| `test_error_toast_on_422` | 422 响应 → toast 显示错误理由 |

**`tests/PendingUpdateItem.test.tsx`**：

| 测试 | 验证 |
|---|---|
| `test_create_character_renders` | 显示 "新建人物 · 韩梅" + description |
| `test_update_character_renders_diff` | 显示 "更新人物 · 李雷 · background" + old/new |
| `test_accept_button_calls_mutation` | 点击 ✓ → 调 accept API |
| `test_reject_button_calls_mutation` | 点击 ✗ → 调 reject API |
| `test_already_decided_shows_status` | status=accepted → 不显示按钮，显示 "已接受" |

### 7.6 E2E 测试

**`tests/e2e/finalize-pending.spec.ts`** — 一个完整流程：

```
1. 创建项目 + 1 章节带正文（"残月酒馆门口，李雷遇见了韩梅..."）
2. 进入章节页 → 点 "完成本章"
3. 等待 toast "已抽取 N 条新事实"
4. 切到 📋 待处理 → 看到 N 条 pending
5. accept 第一条（新人物 韩梅）→ 状态变 "已接受"
6. 切到 👥 人物 → 看到韩梅出现在列表
7. reject 第二条 → 状态变 "已拒绝"
```

**`tests/e2e/refinalize-overwrites.spec.ts`** — 重抽覆盖：

```
1. finalize 章节 → 产生 3 条 pending
2. accept 1 条
3. 重新 finalize 同一章节
4. 验证：accepted 那条保留；其余 pending 被新一批覆盖
```

### 7.7 不测什么（YAGNI）

- 并发 finalize（假设单用户单请求）
- LLM 真实 API（所有测试 mock）
- 抽取内容质量（人工验收范畴）
- pending_updates 表迁移（drop & recreate）
- Embedding / 向量检索（M3b）

### 7.8 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/agents/extractor.py` | >90% |
| `app/api/chapters_finalize.py` | >85% |
| `app/api/pending_updates.py` | >90% |
| `app/llm/prompts/extractor/*.j2` | 100%（渲染） |
| 前端 `FinalizeButton` + `PendingUpdateItem` | >85% |

---

## 8. M3a 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `POST /api/chapters/{id}/finalize` 同步返回抽取结果 | curl + 单测 |
| 2 | chapter.summary 被填上 LLM 生成的摘要 | sqlite3 直查 |
| 3 | chapter.status 流转到 'final' | sqlite3 直查 |
| 4 | chapter.content_hash 被计算写入 | sqlite3 直查 |
| 5 | pending_updates 表记录抽取结果 | sqlite3 直查 |
| 6 | 重复 finalize 覆盖 status='pending' 的旧记录；保留 accepted/rejected | 单测 + 手工 |
| 7 | LLM 返回非 JSON → 422 + chapter 不变 | 单测 |
| 8 | ActivityBar 📋 图标 + pending 数量 badge | 手工 |
| 9 | 待处理面板按状态/章节过滤 | 手工 |
| 10 | accept 一条 create character → 人物出现在人物库 | E2E |
| 11 | accept 一条 update lore → 设定描述被更新 | 单测 + E2E |
| 12 | reject 一条 → status='rejected'；不动 target | 单测 |
| 13 | accept 已 accept 的 → 409 | 单测 |
| 14 | generation_logs 记录每次抽取（含 prompt + response） | sqlite3 直查 + detail 端点 |
| 15 | 全部后端测试通过 | `pytest -v` |
| 16 | 全部前端测试通过 | `npm test` |
| 17 | 全部 E2E 通过（含 finalize-pending 流） | `npm run test:e2e` |

---

## 9. 待定 / 开放问题

1. **`usePendingCount` 实现选择**：
   - 方案 A（lazy）：复用 list query 的 `length` 字段，简单但每次切到带 badge 的页面会拉完整 list
   - 方案 B：后端加独立 `GET /api/pending-updates/count?project_id=X` 端点，只返回数字
   - **倾向 A**（M3a 用户量小，不优化）；如果 ActivityBar 频繁刷新有性能问题再切 B

2. **Prompt token 上限**：长章节（2 万字）+ 现有实体列表可能 > 100k tokens 超过 context window
   - M3a 处理：max_tokens=4096（输出限制），输入限制不处理（让 Anthropic 报错时返回 502）
   - M3b 加 `ContextBudget` 自动裁剪

3. **抽取幂等性**：finalize 同章节 N 次产生不同 pending 列表（LLM 非确定性）
   - M3a 接受这个事实（temperature=0.1 已经尽力稳）
   - 用户 accept 后保留，未 accept 的会被下次 finalize 覆盖

4. **`extractor_log_id` 复用 generation_logs**：表名是 "generation_logs" 但存的是抽取记录，语义不准
   - M3a 接受（沿用 M2a 表结构，不加新表）
   - 未来重命名为 `llm_call_logs` 更准确

5. **抽取触发后是否自动跳转待处理面板**：
   - 当前设计：不跳，只 toast + invalidate badge
   - 用户可能想要直接跳过去看
   - **倾向**：不跳，保持用户在编辑器里的上下文（badge 会亮起提示）

---

## 10. 未来扩展（v2+，不在 M3a 范围）

- **M3b**：向量检索层（sqlite-vec + embedding）；按需召回相关过往场景
- **M3c**：软事实抽取（关系演变 / 状态时序 / 伏笔标注）
- **M3d**：否定记忆（reject 时记下签名，下次抽取 prompt 中提示 LLM "以下已被拒绝"）
- **M3e**：异步 finalize（任务队列 + SSE 进度推送）
- **独立 count 端点**（如果 M3a 后 ActivityBar 性能问题）
