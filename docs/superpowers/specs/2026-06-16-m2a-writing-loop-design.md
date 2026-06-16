# NovelAI M2a — 写作管线（Writing Pipeline）设计文档

- **日期**：2026-06-16
- **状态**：草案（待用户审阅）
- **范围**：M2a = 后端写作管线。M2b（前端编辑器）独立 plan。
- **依赖**：M1（地基）已完成，提交 `f5d3f6b`

---

## 1. 目标与非目标

### 1.1 目标

让用户在已有的项目/人物/章节基础上，通过**一条 SSE 流式端点**调用 Writer Agent 生成章节正文。生成的 prompt 必须包含按场景过滤的常驻层（项目设定、世界观、涉及人物、关系、lore、前情），且整个 prompt 可观测、可审计、可重放。

### 1.2 非目标

- 前端 UI（M2b）
- 章节后记忆抽取（M3 Extractor Agent）
- Reviewer / Discuss Agent（M4）
- 向量检索层（M3）
- SSE 断线重连
- 多用户并发

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 范围 | M2a 只做后端管线 | 前后端解耦，反馈更快；M2b 独立 plan |
| 内容格式 | Chapter.content 存 Markdown | 对 LLM 友好；M2b TipTap 用 markdown 插件读写 |
| Beat 模型 | outline 纯文本；API 接 `beat_text: str` 参数 | 不动 schema；进度跟踪交给 M2b UI |
| 生成副作用 | `/generate` 只流式返回，**不写 Chapter.content** | 端点纯净可重放；用户用 PATCH 手动保存 |
| Prompt 可见性 | SSE `meta` + `context` 事件 + `generation_logs` 表 | 双重保障：流中可见 + 历史可查 |
| 涉及人物上限 | 1–20 个 | 防止 prompt 过大；20 是上限不是默认值 |
| 列表查询范围 | 强制 `chapter_id` 过滤 | 简化契约；跨章需求出现时再加 |
| 迁移策略 | drop & recreate | M2a 无生产数据；Alembic 留到 M3 |

---

## 2. 模块划分与文件结构

```
app/
├── api/
│   ├── chapters_generate.py   # 新增：POST /api/chapters/{id}/generate（SSE）
│   └── generation_logs.py     # 新增：GET /api/generation-logs（list + detail）
├── agents/
│   ├── __init__.py
│   └── writer.py              # 新增：Writer Agent 编排
├── memory/
│   ├── retrieval.py           # 新增：常驻层组装（纯函数，不调 LLM）
│   ├── errors.py              # 新增：ChapterNotFoundError / InvalidContextError
│   └── schema.py              # 修改：加 GenerationLog 表
├── llm/
│   ├── base.py                # 修改：LLMProvider 加 stream() 方法
│   ├── streaming.py           # 新增：StreamEvent 数据类
│   ├── providers/
│   │   └── claude.py          # 修改：实现 stream()
│   └── prompts/               # 新增目录
│       ├── __init__.py        # Jinja2 环境 + render() 函数
│       └── writer/
│           ├── system.j2
│           ├── user.j2
│           └── README.md
└── (main.py 修改：注册两个新 router)

tests/
├── test_retrieval.py
├── test_prompts.py
├── test_writer_agent.py
├── test_chapters_generate.py
├── test_generation_logs.py
├── test_llm_streaming.py
└── test_m2a_e2e.py
```

**依赖方向（沿用 M1）**：`api → agents → memory → llm`。

**职责边界**：

- `memory/retrieval.py`：纯函数，输入 chapter_id + 涉及实体 ID，输出 `ContextBundle`。**不调 LLM**。
- `agents/writer.py`：编排器。调 `retrieval.assemble_context` → 渲染模板 → 调 `default_router.stream` → 产出事件流 + 写 `generation_logs`。
- `api/chapters_generate.py`：HTTP/SSE 包装层。校验参数、调 Writer Agent、把 `StreamEvent` 转 SSE 字节流。
- `llm/prompts/`：所有 prompt 字符串集中。代码里只有变量名。

**为什么 retrieval 独立模块**：M3 的 Extractor Agent 要复用同样的常驻层组装（保证"生成时和审查时看到的上下文一致"）。

---

## 3. 数据库变更

### 3.1 新增表：`generation_logs`

```sql
generation_logs(
  id INTEGER PRIMARY KEY,
  chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  
  -- 输入
  beat_text TEXT NOT NULL,
  instruction TEXT DEFAULT '',
  involved_character_ids JSON,           -- list[int]
  location_id INTEGER,                   -- 可空
  
  -- 组装的 prompt（可观测性核心）
  system_prompt TEXT NOT NULL,
  user_prompt TEXT NOT NULL,
  context_summary JSON,                  -- 结构化摘要（人物名、关系网、lore 树）
  
  -- 输出
  generated_text TEXT,
  model VARCHAR(100),
  model_task VARCHAR(50),
  
  -- 用量
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  stop_reason VARCHAR(50),
  
  -- 状态
  status VARCHAR(20) NOT NULL DEFAULT 'streaming',
  -- streaming / done / failed / client_disconnected
  
  started_at DATETIME NOT NULL,
  finished_at DATETIME,
  
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
)
```

### 3.2 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| 同时存 `project_id` + `chapter_id` | 冗余 | 不用 JOIN 就能按项目过滤 |
| `context_summary` JSON | 结构化（人物名/关系网/lore 树） | 便于 diff、审计 |
| 完整存 `system_prompt` + `user_prompt` | 接受 token 成本 | 调试 prompt 质量必需 |
| `status` 字段 | streaming / done / failed / client_disconnected | 流式中断、超时、错误都要能追溯 |
| `finished_at` 可空 | 流式中断时不写 | 区分"已完成"和"中断" |
| 不存 `temperature`、`max_tokens` | 简化 | 这些是请求级配置，不影响生成质量观察 |

### 3.3 迁移策略

M2a 期间用 **drop & recreate**：

- `tests/conftest.py` 和 `init_db()` 都用 `Base.metadata.create_all`，新表会自动加
- 已存在的表不会改 schema（M1 表无变更）
- 本地开发数据库允许丢弃：`rm data/novelai.db && uvicorn app.main:app` 自动重建

**何时引入 Alembic**：M3 开始（首次需要保留用户数据时）。M2a 不引入。

### 3.4 Pydantic schema

```python
# app/models/generation.py

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
    # 不暴露 system_prompt / user_prompt / generated_text

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

---

## 4. 常驻层 retrieval 设计

### 4.1 接口契约

```python
# app/memory/retrieval.py

@dataclass
class CharacterStateSnapshot:
    """M2a 简化版：用 character.current_state。M3 加时序表后填充 change_summary。"""
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
    
    characters: list[Character]                              # 仅本次涉及
    character_states: dict[int, CharacterStateSnapshot]      # M2a：从 current_state 取
    
    relationships: list[RelationshipView]                    # M2a：返回空 list（M3 填充）
    
    lore_entries: list[LoreEntry]                            # 涉及地点 + 涉及人物所属势力
    faction_lore: list[LoreEntry]
    location_lore: list[LoreEntry]                           # 含 parent 链
    
    plot_lines: list                                         # M2a：返回空 list（M3 填充）
    recent_chapter_summaries: list[ChapterSummary]


def assemble_context(
    db: Session,
    *,
    chapter_id: int,
    beat_text: str,
    involved_character_ids: list[int],
    location_id: int | None = None,
    recent_chapters: int = 2,
) -> ContextBundle:
    """
    组装常驻层。
    
    严格按 project_id 过滤所有查询。任何 involved_character_id 或 location_id
    不属于本章节项目时，抛 InvalidContextError。
    """
```

### 4.2 严格校验（防跨项目泄漏）

```python
class InvalidContextError(Exception):
    def __init__(self, *, invalid_character_ids=None, invalid_location_id=None):
        self.invalid_character_ids = invalid_character_ids or []
        self.invalid_location_id = invalid_location_id
        ...

# assemble_context 内部：
characters = list(db.scalars(
    select(Character).where(
        Character.id.in_(involved_character_ids),
        Character.project_id == project_id,   # 关键：防跨项目泄漏
    )
))

found_ids = {c.id for c in characters}
invalid_char_ids = set(involved_character_ids) - found_ids
# 同样校验 location_id
# 不一致则 raise InvalidContextError
```

API 层捕获后返回：

```json
HTTP 422
{
  "detail": {
    "error": "invalid_context",
    "invalid_character_ids": [999, 1234],
    "invalid_location_id": null
  }
}
```

### 4.3 lore 收集策略

- **地点**：直接取 `location_id`，递归向上查 `parent_id` 直到 None，得到完整祖先链
- **势力**：从 `character.affiliations` JSON 数组聚合所有 faction ID，按 `type="faction"` 查
- **其它 lore**：M2a 不主动注入（用户没显式选择的物品/概念不进 prompt）

### 4.4 前情提要

取当前章节之前最近 N 章（默认 2）的 `summary`。**跳过 summary 为空的章节**（用户还没写完）。

### 4.5 Token 预算估算

| 项目规模 | 估算 tokens | 占 200k 上下文 |
|---|---|---|
| 小项目（3 人物 / 1 地点） | ~3–5k | <3% |
| 中项目（10 人物 / 5 地点 / 单场景 3 人物） | ~8–15k | <8% |
| 大项目（20 人物同场景 + 2 势力） | ~20–30k | <15% |

**M2a 不实现自动裁剪**——常驻层全量注入涉及实体。超长问题留到 M3 加 `ContextBudget` 配置。

---

## 5. SSE 协议

### 5.1 端点

```
POST /api/chapters/{chapter_id}/generate
Content-Type: application/json
Accept: text/event-stream

{
  "beat_text": "主角在酒馆遇旧友",
  "instruction": "氛围压抑",
  "involved_character_ids": [1, 3],
  "location_id": 7,
  "model_task": "writer_long",
  "max_tokens": 4096
}
```

### 5.2 事件序列

```
event: meta
data: {"generation_log_id": 42, "model": "claude-sonnet-4-6", "model_task": "writer_long", "chapter_id": 1, "started_at": "2026-06-16T10:30:00Z"}

event: context
data: {"project": {...}, "world_overview": {...}, "characters": [...], "character_states": {...}, "relationships": [], "faction_lore": [...], "location_lore": [...], "recent_chapter_summaries": [...]}

event: token
data: {"text": "夜"}

event: token
data: {"text": "色"}

...

event: done
data: {"generation_log_id": 42, "input_tokens": 3200, "output_tokens": 850, "stop_reason": "end_turn"}
```

### 5.3 事件类型

| event | 何时发 | 用途 |
|---|---|---|
| `meta` | 第一个 | 客户端立即拿到 generation_log_id，断线可查 |
| `context` | 第二个 | 验收核心——常驻层摘要可见 |
| `token` | 每个 LLM token | 打字机渲染 |
| `done` | 流正常结束 | 终结信号 + 用量统计 |
| `error` | 流中途错误 | LLM 上游错误（与 502 JSON 互斥） |

**关键决策**：
- `meta` 必先发（即使后续失败也能查 log）
- `context` 必第二发（验收可见性）
- `token` 只发增量 text，不带元数据
- `done` 和 `error` 互斥

### 5.4 错误两种情形

| 错误时机 | HTTP 状态 | 表现 |
|---|---|---|
| LLM 调用前（参数校验、422 context、404 章节、路由失败） | 422 / 404 / 502 | 不开 SSE，JSON 响应 |
| LLM 流中途错误（已发 meta/context） | 200 流 | 末尾发 `event: error` |

### 5.5 中断处理

- 客户端断开 → 服务端 `asyncio.CancelledError` → 把 log 标 `status="client_disconnected"`，`stop_reason="client_disconnected"`，`finished_at=now`
- 服务端崩了 → log 永远 `status="streaming"` → M2b 加清理任务
- **M2a 不实现重连**

### 5.6 GenerationLog 写入时机

| 时机 | 动作 |
|---|---|
| meta 事件发出前 | INSERT：status="streaming"，prompt/context/beat_text/ids 全填，started_at=now |
| token 流过程 | 不写 DB |
| done 事件前 | UPDATE：generated_text、tokens、stop_reason、status="done"、finished_at |
| error 事件前 | UPDATE：status="failed"、stop_reason=错误类型、finished_at |

**token 不写 DB**：避免 SQLite WAL 膨胀 + 影响生成速度。

---

## 6. LLMProvider 流式扩展

### 6.1 StreamEvent 数据类

```python
# app/llm/streaming.py

@dataclass
class StreamEvent:
    type: Literal["token", "done", "error"]
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    error_message: str = ""
    error_code: str = ""
    raw: object = None
```

### 6.2 LLMProvider 协议扩展

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...
    def stream(self, request: LLMRequest, model: str) -> Iterator[StreamEvent]: ...
```

`stream()` 返回**同步生成器**（非 async）——与 M1 全栈同步一致。

### 6.3 ClaudeProvider.stream 实现

```python
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

**关键点**：
- 用 Anthropic SDK 的 `messages.stream()` 上下文管理器
- `text_stream` 自动跳过 thinking/tool_use 块
- `get_final_message()` 拿完整 final message（含 usage）
- 所有异常包装为 error 事件，上层 Agent 不用 try/except 包生成器

### 6.4 ModelRouter 加 stream 转发

```python
def stream(self, request) -> Iterator[StreamEvent]:
    provider_name, model = self.resolve_model(request.model_task)
    provider = self._get_provider(provider_name)
    yield from provider.stream(request, model)
```

### 6.5 同步 vs 异步

| 选项 | 优 | 劣 |
|---|---|---|
| **同步生成器（选）** | 与 M1 一致；测试简单（for 循环） | FastAPI 端点要 `iterate_in_threadpool` 转 async |
| 异步生成器 | FastAPI 端点直接 `async for` | 双实现（complete 同步 + stream 异步）；测试要 async pytest |

**M2a 选同步**。FastAPI 端点用 `starlette.concurrency.iterate_in_threadpool` 把同步生成器转异步迭代器喂给 SSE。

---

## 7. Prompt 模板组织（Jinja2）

### 7.1 目录结构

```
app/llm/prompts/
├── __init__.py                # Jinja2 环境 + render() 函数
└── writer/
    ├── system.j2              # 写作 Agent 的 system prompt
    ├── user.j2                # 用户 prompt（含常驻层占位）
    └── README.md              # 设计意图、变量说明
```

**关键决策**：
- 一个 Agent 一个子目录（不是按 model_task 分目录）
- model_task 区分（writer_long vs writer_short）只影响**模型选择**，不影响 prompt
- 如果未来不同 model_task 真需要不同 prompt，再加 `system_long.j2` 等。M2a 不做。

### 7.2 加载机制

```python
# app/llm/prompts/__init__.py

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    undefined=StrictUndefined,           # 缺变量直接报错
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)

def render(template_path: str, **variables) -> str:
    template = _env.get_template(template_path)
    return template.render(**variables)
```

`StrictUndefined` 是有意选择——prompt 漏字段必须立即暴露，不能静默渲染空字符串。

### 7.3 system.j2（节选）

```
你是一位资深的小说写作助手，正在协助作者完成一部长篇小说。

# 你的工作准则

## 人物一致性
- 严格遵循每个角色的性格特征、说话风格、背景设定
- 角色间的对话要符合各自的语言习惯
- 角色行为要符合其核心动机，不能为了剧情需要而强行 OOC

## 世界观一致性
- 严格遵守世界设定的力量体系、规则与禁忌
- 不能出现与设定时代/科技水平冲突的元素

## 叙事质量
- 展示而非陈述（show, don't tell）
- 对话推进情节，避免说明性对话
- 感官细节具体，避免空洞形容

## 风格
- 严肃文学质感，避免网文套路化表达
- 第三人称限知视角（除非用户特别说明）
- 输出纯正文，不输出解析、注释、思考过程
```

### 7.4 user.j2 段落顺序

```
1. 项目背景（标题/类型/主题/基调/核心设定）
2. 世界观（时代/力量体系/规则/地理/文化）— if world_overview
3. 本场景涉及人物（每个：性格/说话风格/状态/动机/背景）
4. 当前关系（仅本场景人物间）— if relationships
5. 场景设定（地点含祖先链 + 涉及势力）— if faction_lore or location_lore
6. 前情提要（最近 2 章 summary）— if recent_chapter_summaries
7. 本次写作任务（beat_text + 可选 instruction）
```

### 7.5 变量约定

| 变量 | 类型 | 来源 |
|---|---|---|
| `project` | Project | ContextBundle.project |
| `world_overview` | WorldOverview \| None | ContextBundle.world_overview |
| `characters` | list[Character] | ContextBundle.characters |
| `character_states` | dict[int, CharacterStateSnapshot] | ContextBundle.character_states |
| `relationships` | list[RelationshipView] | ContextBundle.relationships |
| `faction_lore` | list[LoreEntry] | ContextBundle.faction_lore |
| `location_lore` | list[LoreEntry] | ContextBundle.location_lore |
| `recent_chapter_summaries` | list[ChapterSummary] | ContextBundle.recent_chapter_summaries |
| `beat_text` | str | API 请求 |
| `instruction` | str | API 请求 |

### 7.6 调试循环

```bash
# 1. 触发生成
curl -N -X POST .../api/chapters/1/generate -d '{...}'

# 2. 看 SSE context event 检查常驻层

# 3. 改 app/llm/prompts/writer/*.j2（FileSystemLoader 每次读盘，热生效）
# 4. 再触发，对比
```

---

## 8. API 契约

### 8.1 端点列表

```
POST   /api/chapters/{chapter_id}/generate              # SSE 流式生成
GET    /api/generation-logs?chapter_id=X&limit=20&offset=0
GET    /api/generation-logs/{id}                        # 详情（含完整 prompt）
```

### 8.2 Generate 请求字段约束

| 字段 | 类型 | 必填 | 默认 | 校验 |
|---|---|---|---|---|
| `beat_text` | str | 是 | — | 非空，1–2000 字符 |
| `instruction` | str | 否 | `""` | ≤ 500 字符 |
| `involved_character_ids` | list[int] | 是 | — | 1–20 个；去重保序 |
| `location_id` | int \| null | 否 | `null` | — |
| `model_task` | str | 否 | `"writer_long"` | 枚举：writer_long / writer_short |
| `max_tokens` | int | 否 | `4096` | 64–8192 |

```python
class GenerateRequest(BaseModel):
    beat_text: str = Field(..., min_length=1, max_length=2000)
    instruction: str = Field(default="", max_length=500)
    involved_character_ids: list[int] = Field(..., min_length=1, max_length=20)
    location_id: int | None = None
    model_task: Literal["writer_long", "writer_short"] = "writer_long"
    max_tokens: int = Field(default=4096, ge=64, le=8192)
    
    @field_validator("involved_character_ids")
    @classmethod
    def _dedup(cls, v):
        seen, out = set(), []
        for cid in v:
            if cid not in seen:
                seen.add(cid); out.append(cid)
        return out
```

### 8.3 Generate 响应矩阵

| 情形 | HTTP | Body |
|---|---|---|
| 成功 | 200 `text/event-stream` | SSE 流 |
| 章节不存在 | 404 `application/json` | `{"detail": "chapter not found"}` |
| 字段校验失败 | 422 | FastAPI 默认 validation 错误 |
| `involved_character_ids` 或 `location_id` 不属本项目 | 422 | `{"detail": {"error": "invalid_context", "invalid_character_ids": [...], "invalid_location_id": ...}}` |
| LLM 调用前失败 | 502 | `{"detail": "llm call failed: ..."}` |
| LLM 流中途失败 | 200 流 + `event: error` | SSE error event |

### 8.4 列表端点

```
GET /api/generation-logs?chapter_id=42&limit=20&offset=0
```

| Query | 必填 | 默认 | 说明 |
|---|---|---|---|
| `chapter_id` | 是 | — | 必填，无跨章查询 |
| `limit` | 否 | 20 | 最大 100 |
| `offset` | 否 | 0 | 分页 |

**响应**：`list[GenerationLogRead]`（轻量，不含 prompt 全文）

### 8.5 详情端点

```
GET /api/generation-logs/{id}
```

**响应**：`GenerationLogDetail`（含完整 prompt、generated_text、context_summary）

### 8.6 关键决策

- `/generate` 路径放在 `/api/chapters/{id}/` 下——动作主语是章节
- `/api/generation-logs` 是独立资源——查询、详情都走它，与 chapters 解耦
- **没有 DELETE / PATCH**——日志不可改、不删（数据量小，留作历史）
- 列表强制 `chapter_id`——避免无限制全表扫描
- **M2a 不加 CORS**——前后端同源时不需要；M2b 跨域时再加
- **M2a 不写额外 OpenAPI 描述**——SSE 在 OpenAPI 3.0 里描述复杂，让默认 schema 即可

---

## 9. 测试策略

### 9.1 测试金字塔

```
┌─────────────────┐
│  E2E 黄金用例   │  1–2 个，覆盖整条管线
└─────────────────┘
┌───────────────────────┐
│  Agent + API 集成测试  │  mock LLM，验 SSE 流
└───────────────────────┘
┌───────────────────────────────┐
│  单元测试（retrieval, 模板）  │  不调 LLM，纯函数
└───────────────────────────────┘
```

### 9.2 单元测试（不调 LLM）

**`tests/test_retrieval.py`**：

| 测试 | 验证 |
|---|---|
| `test_assemble_basic` | 项目+人物+世界观正确组装 |
| `test_assemble_excludes_other_project_chars` | 跨项目 character_id → InvalidContextError |
| `test_assemble_excludes_other_project_location` | 跨项目 location_id → InvalidContextError |
| `test_assemble_nonexistent_char_id` | 不存在的 character_id → InvalidContextError 含非法 ID 列表 |
| `test_assemble_chapter_not_found` | ChapterNotFoundError |
| `test_assemble_with_no_world_overview` | 项目无世界观时 `world_overview=None` 不报错 |
| `test_assemble_recent_summaries_skips_empty` | Chapter.summary 为空时跳过 |
| `test_assemble_recent_summaries_excludes_current` | 不包含当前章节自身 |
| `test_assemble_location_with_ancestors` | location_id 的 parent 链正确展开 |
| `test_assemble_includes_faction_from_character_affiliations` | 自动收集 faction lore |
| `test_assemble_m3_fields_are_empty` | relationships/plot_lines 返回空但字段存在 |

**`tests/test_prompts.py`**：

| 测试 | 验证 |
|---|---|
| `test_render_writer_system` | system.j2 渲染不抛错 |
| `test_render_writer_user_full` | user.j2 完整变量渲染 |
| `test_render_writer_user_minimal` | user.j2 最小变量渲染（无 world_overview/relationships/lore/summaries） |
| `test_render_writer_user_missing_var_raises` | StrictUndefined 缺变量时报错 |
| `test_render_writer_user_empty_characters_loop` | characters 空时不抛错 |

### 9.3 Agent 集成测试（mock LLMProvider）

**`tests/test_writer_agent.py`**：

| 测试 | 验证 |
|---|---|
| `test_writer_yields_meta_first` | 第一个事件是 meta |
| `test_writer_yields_context_second` | 第二个事件是 context（含常驻层摘要） |
| `test_writer_passes_through_tokens` | token 事件按顺序透传 |
| `test_writer_yields_done_at_end` | 最后事件是 done |
| `test_writer_persists_log_on_done` | DB status="done"，含完整 prompt + tokens |
| `test_writer_persists_log_on_error` | error 事件后 DB status="failed" |
| `test_writer_log_contains_rendered_prompts` | system_prompt/user_prompt 是渲染后字符串 |

### 9.4 API 测试

**`tests/test_chapters_generate.py`**：

| 测试 | 验证 |
|---|---|
| `test_generate_returns_404_unknown_chapter` | 章节不存在 |
| `test_generate_returns_422_invalid_character_id` | 跨项目 → 422 |
| `test_generate_returns_422_too_many_chars` | 21 个 character_id 被拒 |
| `test_generate_returns_422_empty_beat_text` | 空 beat_text 被拒 |
| `test_generate_sse_stream_full_sequence` | meta → context → token* → done 顺序正确 |
| `test_generate_sse_emits_error_on_llm_failure` | LLM 失败发 error event，DB 记 failed |
| `test_generate_creates_log_before_streaming` | meta 发出时 DB 已有 streaming 记录 |

**`tests/test_generation_logs.py`**：

| 测试 | 验证 |
|---|---|
| `test_list_requires_chapter_id` | 缺 chapter_id 返回 422 |
| `test_list_returns_only_target_chapter` | 不返回其他章节记录 |
| `test_list_pagination` | limit/offset 正确 |
| `test_detail_returns_full_prompt` | 详情含 system_prompt/user_prompt/generated_text |
| `test_detail_404_unknown_log` | 不存在 id 返回 404 |

### 9.5 LLM 流式测试

**`tests/test_llm_streaming.py`**：

| 测试 | 验证 |
|---|---|
| `test_claude_stream_yields_tokens_then_done` | mock SDK，验证事件序列 |
| `test_claude_stream_wraps_errors` | SDK 异常包装为 error 事件 |

### 9.6 E2E 黄金用例

**`tests/test_m2a_e2e.py::test_full_generation_workflow`**：

```python
def test_full_generation_workflow(client, monkeypatch):
    # 1. 准备数据：项目 + 世界观 + 3 人物 + 1 地点 + 1 势力 + 2 章历史
    # 2. mock default_router 返回固定流
    # 3. 触发生成
    # 4. 解析 SSE 事件
    # 5. 断言事件顺序、context 内容、token 拼接
    # 6. 查 generation_log detail，断言：
    #    - status="done"
    #    - user_prompt 含 "李雷"（常驻层注入正确）
    #    - generated_text 完整
    #    - tokens 数正确
```

### 9.7 不测什么（YAGNI）

- SSE 断线重连（M2a 不实现）
- 并发生成（假设单用户单请求）
- LLM 真实 API（所有测试 mock SDK）
- Prompt 内容质量（人工验收范畴）

### 9.8 覆盖率目标

- `app/memory/retrieval.py`：100%
- `app/agents/writer.py`：>90%
- `app/llm/streaming.py` + `prompts/__init__.py`：100%
- `app/llm/providers/claude.py`：>85%
- API 层：>85%

---

## 10. M2a 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `POST /api/chapters/{id}/generate` 流式返回正文 | curl 实测看到 token 逐个吐出 |
| 2 | SSE 事件顺序：meta → context → token* → done | curl + 单测 |
| 3 | context 事件包含常驻层（项目/世界观/人物/lore/前情） | E2E 测试断言 user_prompt 含人物名 |
| 4 | generation_logs 表记录每次生成 | sqlite3 直查 + detail 端点 |
| 5 | 跨项目 character_id / location_id 返回 422 | 单测 + curl |
| 6 | LLM 流中途错误发 error event，DB 标 failed | 单测 |
| 7 | LLM 调用前错误返回 JSON 错误，不开 SSE | 单测 |
| 8 | Jinja2 模板热改（不重启服务生效） | 手工 |
| 9 | drop & recreate 迁移生效 | 手工 |
| 10 | 全部测试通过 | `pytest -v` |

### 验收脚本

```bash
# 1. 清库重建
rm data/novelai.db
uvicorn app.main:app --reload &

# 2. 创建项目 + 世界观 + 人物 + 地点 + 章节（用 /docs 或 curl）

# 3. 触发生成
curl -N -X POST http://127.0.0.1:8000/api/chapters/1/generate \
  -H "Content-Type: application/json" \
  -d '{"beat_text": "主角在酒馆遇旧友", "involved_character_ids": [1, 2], "location_id": 1}'

# 4. 看流式输出（meta → context → token* → done）

# 5. 查日志
sqlite3 data/novelai.db "SELECT id, status, input_tokens, output_tokens FROM generation_logs ORDER BY id DESC LIMIT 1"
sqlite3 data/novelai.db "SELECT user_prompt FROM generation_logs ORDER BY id DESC LIMIT 1"

# 6. 测试 422
curl -X POST .../api/chapters/1/generate \
  -d '{"beat_text": "x", "involved_character_ids": [99999]}'

# 7. 跑全部测试
pytest -v
```

---

## 11. 待定 / 开放问题

实现计划阶段需决策：

1. **`involved_character_ids` 是否支持自动检测**：M2a 强制用户显式选择。M3 是否加 AI 提取（从 beat_text 自动识别人物名）？
2. **Prompt 模板版本控制**：M2a 用文件系统 + git。是否需要"哪一版 prompt 生成了哪一章"的可追溯性？目前 `generation_logs.system_prompt` 已存了完整字符串，可以重放。
3. **`max_tokens` 默认 4096 是否合适**：长 beat 可能需要 8192。M2b 加 UI 后用户可以调，先用 4096 跑跑看。
4. **`status="streaming"` 的清理**：M2a 不做。如果服务端崩了会有孤儿记录。M3 加启动时清理任务（status="streaming" 且 started_at 超过 1 小时的标 failed）。

---

## 12. 未来扩展（v2+，不在 M2a 范围）

- M2b：Next.js + TipTap 前端编辑器
- M3：Extractor Agent + pending_updates + 向量检索层 + relationships/plot_lines/character_states 时序表
- M4：Reviewer Agent + Discuss Agent
- 重连 SSE（断点续传，用 Range header 或 last-event-id）
- Prompt 模板 A/B 测试
- 多模型并发生成对比
