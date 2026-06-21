# NovelAI M3c-D — 情节线状态流转（plot_lines）设计文档

- **日期**：2026-06-21
- **状态**：草案（待用户审阅）
- **范围**：M3c-D = plot_lines 表 + CRUD + retrieval 接入（Writer/Reviewer 注入 active 情节线）+ /plot-lines 管理页 + EventForm/ChapterEditor 接线
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要）、M3b（向量检索）、M3c-A/B/C（relationships/character_states/events）、M4a（Reviewer）已完成

> M3c 拆分为 4 个独立子项目（A 关系 ✅ / B 状态 ✅ / C 伏笔 ✅ / **D plot_lines**）。本文档覆盖 **D**——M3c 最后一块结构化记忆。

---

## 1. 目标与非目标

### 1.1 目标

让用户能管理主线/支线的生命周期，让 Writer/Reviewer 知道"当前在推进哪些情节线"：

1. 新建 `plot_lines` 表（type/title/summary/description/status/start_end_chapter）
2. `/plot-lines` CRUD 页面（ActivityBar 📊 第 10 图标）
3. EventForm 加 plot_line 下拉（写 `events.plot_line_id`，M3c-C 已预留字段）
4. ChapterEditor 加 plot_line tags（写 `chapters.plot_line_ids`，M1 已预留字段）
5. `assemble_context` + `assemble_review_context` 填充 `ContextBundle.plot_lines`（仅 active）
6. Writer/reviewer user.j2 新增"当前情节线"段

### 1.2 非目标（M3c-D 不做）

- Extractor 自动分类事件到 plot_lines（LLM 跨章理解不可靠；用户手动标）
- status 自动流转（finalize 章节时自动改 status；用户手动管理）
- plot_lines 历史版本（不像 relationships 有版本切换）
- plot_lines 时序（不像 character_states/relationships 有时间轴）
- LLM 真实 API 集成测试

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 范围 | **选项 B：CRUD + retrieval 接入** | CRUD 不接 retrieval = 数据死岛；retrieval 接入成本低（占位字段已存在） |
| retrieval 注入 | **仅 active plot_lines** | 控制 token；Writer/Reviewer 关心当前进展，不关心历史线 |
| UI | **独立 /plot-lines 页面** | 用户需管理 plot_lines 本身（建/改 status/写 summary）；下拉只能选不能建 |
| Extractor 自动分类 | **不做** | LLM 判断"事件属于哪条线"不可靠；用户手动标一个下拉 |
| status 流转 | **手动** | 用户在 plot-lines 页面改 status；自动流转逻辑复杂 |
| type 枚举 | `main` / `sub` | spec §3.1 原设计 |
| status 枚举 | `planned` / `active` / `resolved` / `abandoned` | spec §3.1 原设计 |
| start/end_chapter | nullable chapter_id（软关联） | 与 events.location_id 同模式 |
| 无 extractor_log_id / pending_update_id | 手动建，不走 extraction | 与 events/relationships 不同——plot_lines 纯手动管理 |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   ├── schema.py                        # 修改：加 PlotLine ORM
│   └── retrieval.py                     # 修改：assemble_context + assemble_review_context 填充 plot_lines
├── api/
│   └── plot_lines.py                    # 新增：CRUD 端点
├── main.py                              # 修改：注册 plot_lines router
├── llm/prompts/
│   ├── writer/user.j2                   # 修改：新增"当前情节线"段
│   └── reviewer/user.j2                 # 修改：同上
└── models/
    └── plot_line.py                     # 新增：PlotLineRead + PlotLineCreate + PlotLineUpdate

alembic/versions/
└── <hash>_add_plot_lines.py             # 新增

web/
├── app/projects/[projectId]/
│   └── plot-lines/page.tsx              # 新增：情节线管理页
├── components/
│   ├── layout/ActivityBar.tsx           # 修改：加 📊 第 10 图标
│   └── entities/
│       ├── PlotLineForm.tsx             # 新增：手动建/编辑表单
│       ├── EventForm.tsx                # 修改：加 plot_line 下拉
│       └── (ChapterEditor plot_line tags)  # 修改：ChapterEditor 或 EditorToolbar 加 tags
└── lib/
    ├── api.ts / queries.ts / types.ts   # 修改

tests/
├── test_plot_line_schema.py             # 新增
├── test_plot_lines_api.py               # 新增
├── test_context_assembly.py             # 修改：验证 plot_lines 注入
├── test_assemble_review_context.py      # 修改：验证 plot_lines 注入
└── test_prompts.py                      # 修改：验证 writer/user.j2 渲染 plot_lines

web/tests/
├── PlotLineForm.test.tsx                # 新增
└── e2e/plot-lines-flow.spec.ts          # 新增
```

---

## 3. 数据库变更

### 3.1 新增表：`plot_lines`

```sql
CREATE TABLE plot_lines (
  id INTEGER PRIMARY KEY,

  project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

  type          TEXT NOT NULL DEFAULT 'sub',     -- 'main' | 'sub'
  title         TEXT NOT NULL,
  summary       TEXT NOT NULL DEFAULT '',        -- 当前进展概述（动态）
  description   TEXT NOT NULL DEFAULT '',        -- 这条线是关于什么的（静态）
  status        TEXT NOT NULL DEFAULT 'planned', -- planned|active|resolved|abandoned

  start_chapter INTEGER,                         -- nullable chapter_id（软关联）
  end_chapter   INTEGER,                         -- nullable chapter_id（软关联）

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX idx_plot_lines_project ON plot_lines(project_id, status);
```

**字段说明：**

| 字段 | 用途 |
|---|---|
| `type` | `main`（主线）或 `sub`（支线）；不限制每项目 main 数量（用户可能有多条平行主线） |
| `title` | 简明标题（如"复仇之路"、"残月酒馆秘密"） |
| `summary` | 当前进展概述，随章节推进动态更新（如"李雷已找到韩梅的藏身处"） |
| `description` | 静态描述（如"本线围绕信任与背叛展开"） |
| `status` | 4 态流转：planned → active → resolved/abandoned |
| `start_chapter` | 情节线开始的章节 id；null = 开章前就已存在 |
| `end_chapter` | 情节线结束的章节 id；null = 未结束 |

### 3.2 Alembic 迁移

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

**down_revision = `'e8b2d6d7d6ba'`**（M3c-C events 迁移）。

### 3.3 已有字段激活

以下字段在 M1/M3c-C 时已创建但从未被读写，M3c-D 将其激活：

| 字段 | 所在表 | 创建于 | M3c-D 激活方式 |
|---|---|---|---|
| `chapters.plot_line_ids` | chapters | M1 | ChapterEditor 加 Chip 多选，写入 JSON 数组 |
| `events.plot_line_id` | events | M3c-C | EventForm 加下拉，写入 nullable INT |
| `ContextBundle.plot_lines` | retrieval.py | M2a | assemble_context + assemble_review_context 填充 |

---

## 4. Pydantic Schemas

### `app/models/plot_line.py`

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

---

## 5. API 契约

### 5.1 端点

```
GET    /api/plot-lines?project_id=X[&status=active]
POST   /api/plot-lines
PATCH  /api/plot-lines/{id}
DELETE /api/plot-lines/{id}
```

### 5.2 GET list

```
GET /api/plot-lines?project_id=1&status=active
```

| Query | 默认 | 说明 |
|---|---|---|
| `project_id` | 必填 | 项目隔离 |
| `status` | 可选 | `active` / `planned` / `resolved` / `abandoned`；不传 = 全部 |

响应：`list[PlotLineRead]`，按 `(type DESC, id ASC)` 排序（main 在前）。

### 5.3 POST / PATCH / DELETE

标准 CRUD，与 relationships/events 同模式。

DELETE 时不清理 `events.plot_line_id` / `chapters.plot_line_ids` 引用——设为悬空（前端显示"（无）"）。这是 YAGNI 简化；plot_line 删除是罕见操作。

---

## 6. Retrieval 接入

### 6.1 `assemble_context`（写作路径）

在 `app/memory/retrieval.py` 的 `assemble_context` 函数中，替换 `plot_lines=[]` 占位：

```python
from app.memory.schema import PlotLine

active_plot_lines = list(db.scalars(
    select(PlotLine).where(
        PlotLine.project_id == project_id,
        PlotLine.status == "active",
    )
))
```

`ContextBundle` 构造改为 `plot_lines=active_plot_lines`。

### 6.2 `assemble_review_context`（审稿路径）

同样注入 active plot_lines 到 `ReviewContextBundle`。

新增字段到 `ReviewContextBundle`：

```python
@dataclass
class ReviewContextBundle:
    ...
    plot_lines: list[PlotLine]  # active only
```

在 `assemble_review_context` 函数末尾查询并填充。

### 6.3 Writer user.j2 新增段

在 "# 本场景涉及人物" 段之后、"当前关系" 之前插入：

```
{% if plot_lines %}
# 当前情节线
{% for pl in plot_lines %}
- [{{ pl.type }}] {{ pl.title }}：{{ pl.summary }}
{% endfor %}
{% endif %}
```

### 6.4 Reviewer user.j2 同样新增

在 "# 当前人物关系" 段之后插入相同的"当前情节线"段。

---

## 7. 前端 UI

### 7.1 ActivityBar 加 📊 第 10 图标

```typescript
{ icon: "🎯", label: "事件", path: "events", ... },
{ icon: "📊", label: "情节线", path: "plot-lines", ... },
{ icon: "🌍", label: "设定", path: "lore", ... },
```

### 7.2 `/plot-lines` 页面

ChapterWorkspaceGrid 布局：左侧 PlotLineForm 列表 + 右侧编辑表单。与 /relationships 同模式。

### 7.3 PlotLineForm

- type 下拉（主线/支线）
- status 下拉（planned/active/resolved/abandoned）
- title 输入
- summary textarea
- description textarea
- start_chapter 下拉（项目内章节，可选）
- end_chapter 下降（项目内章节，可选）

### 7.4 EventForm 加 plot_line 下拉

在"地点"下拉下方加"情节线"下拉（项目内 plot_lines，可为空=未归属）。

### 7.5 ChapterEditor 加 plot_line tags

Chip 多选（与 CharacterForm affiliations 同模式），写入 `chapters.plot_line_ids`。

---

## 8. 测试策略

### 8.1 后端

| 测试 | 验证 |
|---|---|
| `test_plot_line_table_columns` | 表字段存在 |
| `test_plot_line_indexes` | 索引存在 |
| `test_plot_line_cascade_delete` | 删项目 → plot_lines 级联删 |
| `test_list_plot_lines_default_all` | 默认返回全部 |
| `test_list_plot_lines_status_filter` | `?status=active` 只返回 active |
| `test_create_plot_line` | POST 立即落库 |
| `test_patch_plot_line` | PATCH 改字段 |
| `test_delete_plot_line` | DELETE → 204 |
| `test_assemble_context_includes_active_plot_lines` | 写作上下文含 active plot_lines |
| `test_assemble_context_excludes_non_active` | planned/resolved 不进写作上下文 |
| `test_assemble_review_context_includes_active` | 审稿上下文同样含 active |
| `test_render_writer_user_has_plot_lines` | writer/user.j2 渲染 plot_lines 段 |
| `test_render_reviewer_user_has_plot_lines` | reviewer/user.j2 渲染 plot_lines 段 |

### 8.2 前端

| 测试 | 验证 |
|---|---|
| `test_plot_line_form_creates` | 新建 → POST |
| `test_plot_line_form_edit` | 编辑模式渲染已有数据 |
| `test_activity_bar_has_plot_lines_icon` | 📊 图标存在 |

### 8.3 E2E

```
1. 创建项目
2. 进 /plot-lines → 新建"复仇之路"（主线，active）
3. 列表出现
4. 进 /events → 新建事件 → 情节线选"复仇之路"
5. 进章节编辑器 → plot_line tags 选"复仇之路"
```

---

## 9. M3c-D 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `plot_lines` 表 + 索引 + migration | sqlite3 直查 |
| 2 | GET /api/plot-lines 默认返回全部 | curl + 单测 |
| 3 | `?status=active` 过滤正确 | 单测 |
| 4 | POST/PATCH/DELETE CRUD | 单测 |
| 5 | assemble_context 注入 active plot_lines | 单测 |
| 6 | assemble_review_context 注入 active plot_lines | 单测 |
| 7 | writer/user.j2 渲染 plot_lines 段 | 单测 |
| 8 | reviewer/user.j2 渲染 plot_lines 段 | 单测 |
| 9 | ActivityBar 📊 第 10 图标 | 手工 |
| 10 | /plot-lines 页面：列表 + 新建 + 编辑 | 手工 + E2E |
| 11 | EventForm 含 plot_line 下拉 | 手工 |
| 12 | ChapterEditor 含 plot_line tags | 手工 |
| 13 | 全后端测试通过 | `pytest -v` |
| 14 | 全前端测试通过 | `npm test` |
| 15 | E2E 通过 | `npm run test:e2e` |

---

## 10. 待定 / 开放问题

1. **main 数量限制**：当前不限制每项目 main 数量。用户可能误建多条 main。可加应用层校验（POST 时检查已有 main 数量），但 YAGNI——用户自己管理。

2. **chapters.plot_line_ids 写入时机**：用户在 ChapterEditor 手动选 Chip？还是 finalize 时自动从本章 events 的 plot_line_id 汇总？后者更自动化但引入 finalize 副作用。M3c-D 用前者（手动选）。

3. **start/end_chapter 与 status 的关系**：用户可能设了 status=resolved 但忘填 end_chapter。不做自动校验——用户自己保持一致。

---

## 11. 未来扩展（v2+，不在 M3c-D 范围）

- **Extractor 自动分类事件**：LLM 判断事件属于哪条 plot_line
- **status 自动流转**：finalize 章节时检查 plot_line 进展
- **plot_lines 可视化**：主线/支线的章节分布图
- **plot_lines 时序**：记录 status 变化历史
- **ContextBudget**：active plot_lines > 10 时自动裁剪
