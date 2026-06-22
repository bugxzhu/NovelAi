# NovelAI

AI 辅助小说写作工具——通过结构化记忆让 AI 在长篇创作中保持人物、关系、情节、伏笔和世界观的一致性。

## 核心理念

传统 AI 写作工具用全文 RAG 检索，长篇容易"失忆"。NovelAI 采用**结构化记忆**策略：

- **常驻层**（每次生成必注入）：项目设定、世界观、涉及人物档案、当前关系、情节线状态、故事蓝图
- **检索层**（按需向量召回）：过往章节中语义相关的场景/对话
- **时序层**（跨章追踪）：人物状态轨迹、关系演变、伏笔标注

四个 AI Agent 各司其职：**Writer**（写章节）、**Extractor**（抽记忆）、**Reviewer**（审稿）、**Discuss**（脑暴推演）。

## 功能一览

### 写作

| 功能 | 说明 |
|---|---|
| 大纲驱动生成 | 写 beat 大纲 → AI 扩写成正文（SSE 流式打字机） |
| 续写 | 在光标处触发 AI 续写 |
| ✨ 润色 | 选中段落或整章润色；支持指定润色方向（如"增加心理描写"）；段落润色出 2 个方案供选择 |
| 故事蓝图 | 里程碑式全局结构管理（激励事件/高潮/转折等），注入 Writer 上下文 |

### AI Agent

| Agent | 触发方式 | 功能 |
|---|---|---|
| Writer | 点"⚡ 生成" | 基于大纲 + 常驻层 + 向量检索，流式生成章节正文 |
| Extractor | 点"✓ 完成本章" | 抽取章节摘要、新人物/设定、人物状态变化、关系变化、章节事件 |
| Reviewer | 点"🔍 审稿" | 5 维度审查（人物/关系/情节/伏笔/世界观），Issue 高亮定位 |
| Discuss | 点"💬 探讨" | "如果...会怎样"多分支推演 + 推荐；支持选中文字针对性探讨 |

### 结构化记忆

| 记忆类型 | 数据表 | 说明 |
|---|---|---|
| 章节摘要 | `chapters.summary` | AI 生成的 200-400 字摘要 |
| 硬事实 | `pending_updates` (auto=true) | 新人物/设定/事件——accept 后入库 |
| 人物状态轨迹 | `character_states` | 每章末的状态快照（情绪/处境/目标），按章节回溯 |
| 关系演变 | `relationships` | 单向关系时序表（from→to），accept 时自动版本切换 |
| 伏笔标注 | `events` + `foreshadows` | 事件管理 + 跨章伏笔链接 + 孤儿伏笔检测 |
| 情节线 | `plot_lines` | 主线/支线状态追踪（planned/active/resolved） |
| 故事蓝图 | `story_milestones` | 全局里程碑结构（激励/高潮/转折），注入 Writer/Reviewer |
| 向量检索 | `chunk_meta` + `vec_chunks` | sqlite-vec 语义检索过往章节场景 |
| 否定记忆 | `pending_updates` (rejected) | 已拒绝的抽取建议不再重复（注入 Extractor prompt） |

### 项目管理

- 项目 CRUD（有章节时不可删除，防止误操作）
- 世界观总览（时代/力量体系/规则禁忌/地理文化）
- Lore 设定库（地点/势力/物品/组织/概念，支持层级嵌套）
- 人物档案（性格/说话风格/动机/背景/所属势力）
- 章节管理（草稿/写作中/已定稿）
- 待处理面板（pending_updates 审批队列）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic |
| 数据库 | SQLite + sqlite-vec（单文件，零运维） |
| 前端 | Next.js 15 + React + TipTap v3 + Zustand + TanStack Query |
| LLM | 多提供商（Anthropic Claude / OpenAI / DashScope / Deepseek / Ollama） |
| 测试 | pytest（后端）+ Vitest（前端单元）+ Playwright（E2E） |

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url> && cd novelAI

# 后端
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 前端
cd web && npm install && cd ..

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 2. 配置 LLM（.env）

```bash
# 选择 Provider
NOVELAI_LLM_PROVIDER=claude    # 或 openai

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# 或 OpenAI 兼容端点（支持 DashScope/Deepseek/Ollama 等）
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# 向量检索（需 OpenAI 兼容端点，Anthropic 不提供 embedding）
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

### 3. 初始化数据库

```bash
alembic upgrade head
```

### 4. 启动

```bash
# 终端 1：后端（端口 8005）
uvicorn app.main:app --reload --port 8005

# 终端 2：前端（端口 3300）
cd web && npm run dev
```

访问 http://localhost:3300 开始使用。

## 写作流程

```
创建项目 → 设定世界观 → 建人物/关系 → 写第 1 章大纲
    ↓
点 "⚡ 生成" → Writer 扩写正文（流式）
    ↓
修改/润色 → 点 "✓ 完成本章" → Extractor 抽取记忆
    ↓
审批 pending_updates（新人物/设定/状态/关系/事件）
    ↓
点 "🔍 审稿" → Reviewer 5 维度审查 → 修改
    ↓
写下一章 → 点 "💬 探讨" 脑暴 → Writer 生成 → 循环
```

## API 概览

| 资源 | 端点 |
|---|---|
| 项目 | `POST/GET/PATCH/DELETE /api/projects` |
| 世界观 | `PUT/GET /api/projects/{id}/world-overview` |
| Lore 设定 | `POST/GET/PATCH/DELETE /api/lore` |
| 人物 | `POST/GET/PATCH/DELETE /api/characters` |
| 人物状态 | `GET /api/characters/{id}/states` |
| 关系 | `POST/GET/PATCH/DELETE /api/relationships` |
| 关系历史 | `GET /api/relationships/history` |
| 事件 | `POST/GET/PATCH/DELETE /api/events` |
| 情节线 | `POST/GET/PATCH/DELETE /api/plot-lines` |
| 故事蓝图 | `POST/GET/PATCH/DELETE /api/story-milestones` |
| 章节 | `POST/GET/PATCH/DELETE /api/chapters` |
| 章节生成 | `POST /api/chapters/{id}/generate`（SSE 流式） |
| 章节定稿 | `POST /api/chapters/{id}/finalize` |
| 章节审稿 | `POST /api/chapters/{id}/review` |
| 章节探讨 | `POST /api/chapters/{id}/discuss` |
| 章节润色 | `POST /api/chapters/{id}/polish` |
| 待处理 | `GET /api/pending-updates` + `POST .../{id}/accept` + `POST .../{id}/reject` |
| 生成日志 | `GET /api/generation-logs` |

完整文档：http://127.0.0.1:8005/docs

## 测试

```bash
# 后端（388+ 测试）
pytest

# 前端单元（82+ 测试）
cd web && npm test

# E2E（需后端运行）
cd web && npm run test:e2e
```

## 数据库迁移

```bash
alembic upgrade head      # 应用所有迁移
alembic current           # 查看当前版本
alembic downgrade -1      # 回滚一步
```

**不要用 `rm data/novelai.db` 重建**——会丢失所有数据。

## 项目结构

```
app/
├── agents/           # AI Agent 编排
│   ├── writer.py       # 写作生成（SSE 流式）
│   ├── extractor.py    # 章节记忆抽取
│   ├── reviewer.py     # 5 维度审稿
│   ├── discuss.py      # 多分支推演
│   ├── polish.py       # 文字润色
│   └── retrieval.py    # 向量检索层
├── memory/           # 记忆服务
│   ├── schema.py       # SQLAlchemy 模型（12 张表）
│   ├── retrieval.py    # 常驻层 + 检索层组装
│   └── session.py      # DB 连接 + sqlite-vec
├── llm/              # LLM 抽象层
│   ├── base.py         # Provider 协议
│   ├── router.py       # 多提供商路由
│   ├── providers/      # Claude / OpenAI 实现
│   └── prompts/        # Jinja2 模板（extractor/writer/reviewer/discuss/polish）
├── api/              # FastAPI 路由
└── models/           # Pydantic schemas

web/
├── app/projects/[projectId]/  # 项目内页面
│   ├── chapters/        # 章节编辑器
│   ├── characters/      # 人物管理 + 状态轨迹
│   ├── relationships/   # 关系管理 + 演变历史
│   ├── events/          # 事件 + 伏笔链接
│   ├── plot-lines/      # 情节线管理
│   ├── outline/         # 故事蓝图
│   └── pending/         # 待处理审批
├── components/editor/    # TipTap 编辑器 + AI 按钮
└── lib/                  # API client + hooks + store
```

## License

Private project.
