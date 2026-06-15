# NovelAI — AI 辅助小说写作工具设计文档

- **日期**：2026-06-15
- **状态**：草案（待用户审阅）
- **范围**：v1 完整愿景（4 个里程碑分阶段交付）

---

## 1. 目标与非目标

### 1.1 目标

构建一个本地优先的 Web 应用，让用户构思故事框架，AI 完成细节与描写。核心机制：**AI 通过结构化记忆（线索）推理，而非全文推理**，从而在长篇创作中保持：

- 世界观/背景一致：世界设定、地理、势力、规则可结构化管理，写作时作为约束注入
- 人物性格一致性、独特性，且能体现成长轨迹
- 人物关系稳定合理，关系演变可记忆、可回溯
- 情节前后不矛盾，伏笔可显式标注与兑现
- 主线/支线状态可追踪
- AI 写作、AI 审稿、AI 探讨三种智能体协同

### 1.2 非目标（v1 不做）

- 多用户协作 / SaaS 化
- 全文 RAG 模糊检索作为主记忆机制
- 自动化发布、排版、版权管理
- 语音/插图生成

---

## 2. 总体架构

### 2.1 形态与部署

- **形态**：Web 应用（浏览器）
- **部署**：单用户、本地优先。后端服务运行在本机，浏览器访问
- **数据**：SQLite 单文件 + sqlite-vec，便于备份与迁移

### 2.2 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python + FastAPI | AI 生态成熟，SSE 流式优秀 |
| 数据库 | SQLite + sqlite-vec + SQLAlchemy | 单文件、零运维、结构化与向量同库 |
| 前端 | Next.js + React + TipTap + Zustand | 富文本编辑器成熟，SSR 友好 |
| LLM 抽象 | 自写薄抽象层 + LiteLLM 兜底 | 可控、不绑定框架 |
| LLM 提供商 | 多提供商（Claude / OpenAI / Gemini / Ollama） | 用户可切换 |

### 2.3 模块划分

```
app/
├── api/              # FastAPI 路由层
├── agents/           # Agent 编排（业务核心）
│   ├── writer.py       # 写作生成
│   ├── reviewer.py     # 审稿
│   ├── discuss.py      # 情节探讨
│   └── extractor.py    # 章节后记忆抽取
├── memory/           # 记忆服务（核心）
│   ├── schema.py       # SQLAlchemy 模型
│   ├── retrieval.py    # 常驻层 + 检索层组装
│   ├── vectors.py      # sqlite-vec 封装
│   └── updates.py      # 硬/软事实分层更新
├── llm/              # LLM 抽象层
│   ├── base.py
│   ├── providers/
│   └── prompts/        # Jinja2 模板，版本化
└── models/           # Pydantic 数据模型

web/                  # Next.js 前端
├── app/
│   ├── editor/         # 主编辑器
│   ├── characters/     # 人物库
│   ├── plot/           # 主线/支线视图
│   └── review/         # 审稿面板
└── components/
```

**依赖方向（单向）**：`api → agents → memory → llm → DB`。Agent 之间不直接调用，通过 memory 共享状态，便于独立测试与替换。

---

## 3. 记忆库 Schema（系统核心）

### 3.1 结构化表

```sql
-- 项目（一本小说）
projects(
  id, title, genre, premise,           -- 一句话核心
  main_theme, tone,
  created_at, updated_at
)

-- 世界观总览（每项目一条）
world_overview(
  id, project_id,
  setting_era,                         -- 时代/纪元
  geography_summary,                   -- 地理概述
  history_summary,                     -- 历史概述
  culture_summary,                     -- 文化概述
  power_system,                        -- 力量体系（魔法/科技/武术等）
  rules_and_taboos,                    -- 世界规则与禁忌
  created_at, updated_at
)

-- 设定条目（通用，可扩展；覆盖地点/势力/物品/组织/概念等）
lore_entries(
  id, project_id,
  type,                                -- location / faction / item / organization / concept / custom
  name, title,
  description,
  attributes,                          -- JSON：类型相关属性（地点坐标、势力领袖等）
  parent_id,                           -- 层级关系（地点包含地点、势力包含势力）
  tags,                                -- JSON 字符串数组
  created_at, updated_at
)

-- 人物档案
characters(
  id, project_id, name, role,          -- 主角/配角/反派/路人
  personality,                         -- 性格特征 JSON
  speech_style,                        -- 说话风格（用词/句式/口癖）
  background, motivation, appearance,
  current_state,                       -- 当前情绪/处境（会变化）
  affiliations,                        -- JSON：所属势力 lore_entries.id 列表
  known_locations,                     -- JSON：知晓/活动过的地点 lore_entries.id 列表
  created_at, updated_at
)

-- 人物状态历史（成长轨迹，时序表）
character_states(
  id, character_id, chapter_id,
  state_snapshot,
  change_summary,                      -- "为什么变了"
  recorded_at
)

-- 关系（边）
relationships(
  id, project_id,
  from_char_id, to_char_id,
  type,                                -- 朋友/敌人/师徒/恋人...
  strength,                            -- -1.0 ~ 1.0
  description,
  valid_from_chapter,
  valid_to_chapter,                    -- NULL = 当前有效
  created_at
  -- 逻辑约束：同一对人物同时只能有一个 valid_to_chapter IS NULL 的"当前有效"关系
  -- 通过 SQLite 部分索引实现：
  -- CREATE UNIQUE INDEX idx_rel_current UNIQUE
  --   ON relationships(from_char_id, to_char_id) WHERE valid_to_chapter IS NULL;
)

-- 情节线
plot_lines(
  id, project_id,
  type,                                -- main / sub
  title, summary, status,              -- planned/active/resolved/abandoned
  start_chapter, end_chapter
)

-- 章节
chapters(
  id, project_id, order_index,
  title, outline,                      -- 用户写的大纲
  content,                             -- 正文
  status,                              -- draft/writing/reviewed/final
  plot_line_ids,                       -- JSON 数组
  summary,                             -- AI 生成的章节摘要
  content_hash,                        -- 用于检测定稿后是否被改动
  created_at, updated_at
)

-- 事件/线索（伏笔与呼应）
events(
  id, project_id, chapter_id,
  title, description,
  involved_characters,                 -- JSON
  location_id,                         -- lore_entries.id（type=location）
  plot_line_id,
  foreshadows,                         -- JSON：此事件是哪些事件的伏笔
  payoff_of,                           -- JSON：此事件兑现了哪些伏笔
  created_at
)

-- 待确认变更队列
pending_updates(
  id, project_id, chapter_id,
  update_type,                         -- hard_fact / soft_fact / foreshadow
  target_table, target_id,             -- 待修改的实体
  proposed_change,                     -- JSON：变更内容
  reason,                              -- AI 给出的理由
  auto,                                -- true=硬事实自动抽取；false=软事实需确认
  status,                              -- pending/accepted/rejected
  created_at
)
```

### 3.2 向量表（检索层）

```sql
-- sqlite-vec 虚拟表
vec_chunks(
  id INTEGER PRIMARY KEY,
  chapter_id, chunk_type,              -- scene / dialogue / description
  text,
  embedding FLOAT[768]                 -- 维度取决于所选 embedding 模型
)
```

### 3.3 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 人物状态变化 | 独立 `character_states` 时序表 | 保留成长轨迹，可回溯任意章节末的状态 |
| 关系变化 | `valid_from/to_chapter` 软失效 | 保留全部历史关系，可答"第 N 章时他们是什么关系" |
| 伏笔/呼应 | `events.foreshadows / payoff_of` 显式标注 | 让"埋了没收"和"无铺垫爆发"可被审稿检出 |
| 软事实更新 | 写入 `pending_updates`（`auto=false`） | 不直接落库，用户确认后才生效 |
| 硬事实更新 | 也写入 `pending_updates` 但 `auto=true` | 同一面板 UI，视觉区分；用户可 reject 抽错的硬事实；接受后才真正写库 |
| 世界观建模 | 总览表 `world_overview` + 通用 `lore_entries` | 总览管全局基线（时代/力量体系/规则），lore 管可枚举的具体条目（地点/势力/物品） |
| lore 类型扩展 | `lore_entries.type` 用字符串判别 + `attributes` JSON | 允许自定义类型（如修仙的"境界"/"法宝"），不为每类建独立表 |
| lore 层级 | `parent_id` 自引用 | 表达地点嵌套（王国→城市→街区）、势力嵌套（联盟→宗门→堂口） |

### 3.4 常驻层 vs 检索层（生成时如何使用）

**常驻层（每次生成必注入，结构化，约 5–20k tokens）**：

- 项目 premise / tone / main_theme
- `world_overview`（始终全量注入，规模可控）
- 当前章节涉及的所有人物档案（含 `affiliations` / `known_locations`）
- 这些人物的最新 `character_states` 快照
- 当前章节涉及人物两两之间的当前有效关系
- 当前章节涉及人物所属势力（`lore_entries` 中 `type=faction` 的条目）
- 当前章节预期发生地点（`lore_entries` 中 `type=location` 的条目，含其 `parent_id` 链上的祖先地点）
- 主线 plot_lines 的 status 与 summary
- 前 1–2 章的 chapter summary

**检索层（按需召回，向量，约 0–5k tokens）**：

- 用户写作指令里提到的具体过往场景
- 当前章节涉及人物的过往对话样本（保语言风格）
- 与当前情节相关的伏笔原文

---

## 4. Agent 编排

四个 Agent 共享 LLM 抽象层与记忆服务，职责严格分离，互不直接调用。

### 4.1 Writer Agent

- **输入**：章节大纲 + 写作模式（outline / continue / discuss-driven）+ 用户附加指令
- **流程**：解析指令 → 拉常驻层 → 按需向量检索 → 组 prompt → 流式生成（SSE）
- **约束**：prompt 明确"硬事实不得违反"；软氛围参考检索片段；不自动写库

### 4.2 Reviewer Agent

- **输入**：待审章节 + 审查维度
- **流程**：拉常驻层 + 涉及人物的过往状态轨迹 → 分维度独立 prompt → 汇总结构化报告
- **维度**：人物一致性 / 关系合理性 / 情节矛盾 / 伏笔完整性 / 世界观一致性
- **世界观一致性检查**：场景中出现的势力/物品/能力是否符合 `world_overview.rules_and_taboos` 与 `power_system`；引用的地点属性是否与 `lore_entries` 一致；时代/科技水平是否冲突
- **输出**：

```python
class Issue(BaseModel):
    severity: Literal["error", "warn", "info"]
    category: Literal["character", "relationship", "plot", "foreshadow"]
    location: str          # 章节内位置/原文片段
    description: str
    suggestion: str
```

- **原则**：不修改原文，只产出报告供用户决策

### 4.3 Discuss Agent

- **输入**：用户的问题 / 设想
- **流程**：拉相关人物/关系/情节线 → 多分支推演（"如果 A / 如果 B / 如果 C"）→ 每分支评估冲突点、对人物弧光影响、伏笔机会 → 输出对比表 + 推荐 + 理由
- **特点**：不写正文，只产出决策依据；用户选定后才进入 Writer Agent

### 4.4 Extractor Agent

- **触发**：用户在前端点"完成本章"时
- **流程**：扫描章节正文 → 抽硬事实（直接写 pending_updates `auto=true`）→ 抽软事实（写 pending_updates `auto=false`）→ 生成 chapter summary → 切 chunks → embedding → 写 vec_chunks → 标注事件（伏笔/兑现）→ 抽取新 lore（地点/势力/物品，写 pending_updates `auto=true`）提示用户确认
- **输出**：pending_updates 队列 + chapter summary + vec_chunks

### 4.5 Agent 间通信规则

- 不直接调用彼此，通过 memory 共享状态、通过 API 路由触发
- 共享 prompt 模板（`llm/prompts/`，Jinja2，版本化）
- 共享 `memory.retrieval.assemble_context()` 保证一致的上下文组装

### 4.6 多提供商路由

```python
class ModelRouter:
    ROUTES = {
        "writer_long":   "claude-sonnet-4-6",
        "writer_short":  "claude-haiku-4-5",
        "reviewer":      "claude-sonnet-4-6",
        "discuss":       "claude-sonnet-4-6",
        "extractor":     "claude-haiku-4-5",
        "embedding":     "bge-small-zh",
    }
```

路由表是配置项，用户可在前端修改。

---

## 5. 写作流程（端到端数据流）

### 5.1 大纲驱动模式（beat 扩写）

1. 用户写 `Chapter.outline`（多个 beat）
2. 触发 `POST /api/chapters/{id}/generate`，body 包含 beat_index 与附加指令
3. Writer Agent 解析 beat → 涉及人物 → 拉常驻层 → 向量检索相关场景与对话样本 → 流式生成
4. 前端打字机渲染 → 用户改 → 写回草稿

### 5.2 对话驱动模式（边聊边写）

1. 用户提设想（"如果让 X 在这里背叛 Y 会怎么样？"）
2. Discuss Agent 给多分支评估 + 推荐
3. 用户选分支 → Discuss Agent 输出 beat 概要 → 进入 Writer Agent 生成

### 5.3 编辑器续写模式

1. 用户在 TipTap 光标处触发续写
2. 仅注入：当前章节涉及人物 + 光标前文本 + 主线状态（不拉常驻层全量）
3. 流式插入光标位置

### 5.4 章节定稿流程

1. `Chapter.status` 流转：`draft → writing → final`
2. 异步触发 Extractor Agent
3. 前端弹"待确认变更"面板，用户逐条 accept/reject
4. 软事实落库 / 关系新版本写入 / 伏笔登记
5. 章节状态置 `final`，进入可被未来章节检索的状态

### 5.5 一致性保证机制

| 场景 | 机制 |
|---|---|
| 写作中防止硬事实违反 | prompt 强约束 + Reviewer 事后审 |
| 关系演变有迹可循 | 关系写入新版本，旧版 `valid_to_chapter` 失效 |
| 人物性格渐变 | `character_states` 时序表，生成时取最新版 |
| 跨章呼应 | `events.foreshadows / payoff_of` 显式标注 + 审稿检查 |
| 世界观冲突 | `world_overview` 全量常驻 + Reviewer 世界观一致性维度 |
| 长文 token 压力 | 常驻层只放本章相关，检索层按需召回 |

### 5.6 关键 API 端点

```
POST   /api/projects
GET    /api/projects/{id}/world-overview
PUT    /api/projects/{id}/world-overview
POST   /api/lore
GET    /api/lore?project_id=&type=
PUT    /api/lore/{id}
DELETE /api/lore/{id}
POST   /api/characters
GET    /api/characters?project_id=
POST   /api/relationships
POST   /api/chapters
POST   /api/chapters/{id}/generate        # 流式
POST   /api/chapters/{id}/continue        # 流式
POST   /api/chapters/{id}/finalize        # 触发 extractor
GET    /api/chapters/{id}/pending-updates
POST   /api/pending-updates/{id}/accept
POST   /api/pending-updates/{id}/reject
POST   /api/discuss                       # 探讨模式
POST   /api/chapters/{id}/review          # 审稿
GET    /api/projects/{id}/timeline        # 人物状态/关系时间线
```

---

## 6. 错误处理与降级

### 6.1 LLM 调用失败

| 故障 | 处理 |
|---|---|
| 超时 / 限流 | 指数退避重试 3 次（1s / 2s / 4s） |
| 上下文超长 | 自动降级：先去检索层 → 再压缩常驻层（人物档案精简版）→ 仍超则报错让用户拆 beat |
| 模型不可用 | 路由表自动 fallback（Claude → OpenAI → 本地 Ollama） |
| 流式中断 | 保留已生成内容到草稿，前端显示"已中断，可继续" |

### 6.2 记忆库一致性

| 风险 | 处理 |
|---|---|
| Extractor 抽错硬事实 | 硬事实也走 `pending_updates`（`auto=true`），用户可在面板 reject |
| 关系版本冲突 | 数据库 UNIQUE 约束保证同一对人物只有一个"当前有效"关系 |
| 章节定稿后用户又改正文 | 检测 `content_hash` 变化 → 提示"建议重新抽取"，不强制 |
| 向量索引损坏 | 从 `chunks.text` 重建，提供 CLI 命令 `reindex` |

### 6.3 数据安全

- SQLite 单文件 + WAL 模式
- 每次定稿前自动 snapshot 到 `backups/{timestamp}.db`（保留最近 20 份）
- 项目导出为单 `.zip`（DB + 资源），可整体迁移

---

## 7. 测试策略

### 7.1 单元测试（pytest）

- `memory/` 全覆盖：retrieval 组装、关系版本切换、状态时序查询
- `llm/` 抽象层：fake provider 验证路由、降级、重试
- `agents/` 每个 Agent：mock LLM 返回，验证 prompt 组装正确性

### 7.2 黄金用例测试（端到端）

预置一个示例小说项目（3 个人物 + 5 章节 + 已知伏笔 + 完整世界观 + 多个 lore 条目），跑：

- 生成第 6 章 → 检查 prompt 是否包含正确常驻层（含 `world_overview` 与涉及 lore）
- Reviewer 审一个故意埋错的章节（人物走样 + 关系矛盾 + 世界观冲突） → 检查是否能分别检出
- Extractor 跑一个有硬/软事实变化、含新地点/势力的章节 → 检查 pending_updates 内容

### 7.3 LLM 评估（非确定性测试）

- 固定种子 prompt + 温度 0，跑 N 次，断言关键事实不漂移
- 不在 CI 跑（成本高），本地 `make eval` 手动触发

### 7.4 前端测试

- 关键组件单测（Vitest）
- 编辑器、记忆库面板、审稿面板的 e2e（Playwright）

---

## 8. MVP 实现顺序

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M1：地基** | DB schema + FastAPI 骨架 + LLM 抽象层（先接一个提供商）+ 基础 CRUD（含 `world_overview` / `lore_entries`） | 能创建项目、世界观、人物、lore 条目、章节，能调 LLM 返回响应 |
| **M2：写作闭环** | Writer Agent + 常驻层组装（含世界观）+ 大纲驱动模式 + SSE 流式 + TipTap 编辑器 | 能从大纲扩写出章节，prompt 里能看到注入的常驻层（含世界观与涉及 lore） |
| **M3：记忆同步** | Extractor Agent + 硬/软事实分层 + pending_updates 面板 + 向量检索层 + lore 抽取 | 定稿一章后能正确抽出新事实（人物/关系/lore），下一章生成时能检索到 |
| **M4：智能 Agent** | Reviewer Agent（含世界观维度）+ Discuss Agent + 多模式写作（对话/续写） | 审稿能检出埋的错（含世界观冲突）；探讨模式能给出多分支 |

M1 + M2 跑完即可日常使用（覆盖约 70% 价值），M3 是质量分水岭，M4 是完整愿景。

---

## 9. 待定 / 开放问题

实现计划阶段需决策：

1. **embedding 模型**：本地 BGE 中文 vs API（OpenAI / Voyage）？影响响应速度与成本
2. **多语言**：v1 只支持中文小说，还是同时支持中英？
3. **`Chapter.content` 存储格式**：纯 Markdown vs TipTap JSON？影响编辑器复杂度
4. **导出格式**：v1 是否需要导出为 docx / epub？

---

## 10. 未来扩展（v2+，不在本设计范围）

- 知识图谱可视化（人物关系网、伏笔拓扑图、lore 层级树）
- 多用户协作
- 章节级版本控制（git-like）
- 写作风格学习（从作者已有作品微调 prompt）
- lore 条目跨项目复用（设定库导入导出）
