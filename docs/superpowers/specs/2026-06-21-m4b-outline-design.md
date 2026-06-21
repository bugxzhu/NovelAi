# NovelAI M4b-1 — 大纲蓝图（story_milestones）设计文档

- **日期**：2026-06-21
- **状态**：草案（待用户审阅）
- **范围**：M4b-1 = story_milestones 表 + CRUD + retrieval 接入（Writer/Reviewer 注入全部里程碑）+ /outline 管理页
- **依赖**：M1（地基）、M2a（写作管线）、M3c-D（plot_lines，retrieval 模式参照）、M4a（Reviewer）已完成

> M4b 拆分为 2 个子项目（**1 大纲蓝图** / 2 Discuss Agent）。本文档仅覆盖 **1**。Discuss 依赖蓝图存在后才能做"蓝图级探讨"。

---

## 1. 目标与非目标

### 1.1 目标

让用户能规划小说全局结构，让 Writer/Reviewer/Discuss 知道"故事弧光"：

1. 新建 `story_milestones` 表（type/title/description/chapter_start/end/status/order_index）
2. `/outline` CRUD 页面（ActivityBar 🗺️ 图标）
3. `assemble_context` + `assemble_review_context` 注入全部里程碑（Writer + Reviewer 看到全局弧光）
4. Writer/reviewer user.j2 新增"故事蓝图"段

### 1.2 非目标

- Discuss Agent（多分支推演）— M4b-2
- 自动 status 流转（finalize 章节时自动更新 milestone status）
- 双层级结构（act + milestone）—— YAGNI；`type` 字段可标记"第一幕"等
- 拖拽排序 —— 用 order_index 数字 + 上下按钮（简单）

### 1.3 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 数据模型 | 里程碑式（单表，无 act 层级） | 灵活适配任何结构；与 events 同模式 |
| type 字段 | 自由文本 | 适配三幕/英雄之旅/网文分卷/任意体系 |
| retrieval 注入 | **全部里程碑**注入 Writer + Reviewer | Writer 需全局弧光；里程碑数量有限（10-20） |
| status 管理 | 手动 | 不耦合 finalize |
| 章节分配 | 数字输入（nullable） | 章节可能未创建；数字比下拉灵活 |
| ActivityBar 图标 | 🗺️ | 蓝图/地图隐喻 |

---

## 2. 模块划分

```
app/
├── memory/schema.py                     # 修改：加 StoryMilestone ORM
├── memory/retrieval.py                  # 修改：assemble_context + assemble_review_context 注入 milestones
├── api/story_milestones.py              # 新增：CRUD
├── main.py                              # 修改：注册 router
├── llm/prompts/
│   ├── writer/user.j2                   # 修改：新增"故事蓝图"段
│   └── reviewer/user.j2                 # 修改：同上
└── models/story_milestone.py            # 新增：Pydantic schemas

alembic/versions/<hash>_add_story_milestones.py

web/
├── app/projects/[projectId]/outline/page.tsx    # 新增
├── components/entities/MilestoneForm.tsx        # 新增
├── components/layout/ActivityBar.tsx            # 修改：加 🗺️
└── lib/api.ts / queries.ts / types.ts           # 修改

tests/ + web/tests/                        # 同 M3c-D 模式
```

---

## 3. 数据库变更

```sql
CREATE TABLE story_milestones (
  id INTEGER PRIMARY KEY,
  project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  order_index   INTEGER NOT NULL DEFAULT 0,
  type          TEXT NOT NULL DEFAULT '里程碑',
  title         TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  chapter_start INTEGER,
  chapter_end   INTEGER,
  status        TEXT NOT NULL DEFAULT 'planned',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX idx_milestones_project ON story_milestones(project_id, order_index);
```

**Alembic** `down_revision = '613de9862323'`（M3c-D plot_lines）。

---

## 4. Pydantic Schemas

```python
class StoryMilestoneRead(ORMBase, TimestampMixin):
    id: int
    project_id: int
    order_index: int
    type: str
    title: str
    description: str
    chapter_start: int | None
    chapter_end: int | None
    status: str           # planned / written / needs_revision


class StoryMilestoneCreate(BaseModel):
    project_id: int
    order_index: int = 0
    type: str = "里程碑"
    title: str
    description: str = ""
    chapter_start: int | None = None
    chapter_end: int | None = None
    status: str = "planned"


class StoryMilestoneUpdate(BaseModel):
    order_index: int | None = None
    type: str | None = None
    title: str | None = None
    description: str | None = None
    chapter_start: int | None = None
    chapter_end: int | None = None
    status: str | None = None
```

---

## 5. API

```
GET    /api/story-milestones?project_id=X
POST   /api/story-milestones
PATCH  /api/story-milestones/{id}
DELETE /api/story-milestones/{id}
```

标准 CRUD，按 `order_index ASC` 排序。与 plot_lines/events 同模式。

---

## 6. Retrieval 接入

`assemble_context` + `assemble_review_context` 注入**全部**里程碑：

```python
all_milestones = list(db.scalars(
    select(StoryMilestone).where(
        StoryMilestone.project_id == project_id,
    ).order_by(StoryMilestone.order_index)
))
```

Writer/reviewer user.j2 新增段：

```
{% if milestones %}
# 故事蓝图
{% for m in milestones %}
- [{{ m.status }}] {{ m.title }}（{{ m.type }}，第 {{ m.chapter_start or "?" }}-{% if m.chapter_end %}{{ m.chapter_end }}{% else %}?{% endif %} 章）：{{ m.description }}
{% endfor %}
{% endif %}
```

---

## 7. 前端

- ActivityBar 🗺️ 第 11 图标（outline）
- `/outline` 页面：ChapterWorkspaceGrid + SidePanel（列表）+ MilestoneForm（编辑）
- 列表卡片：`[status] title（type，第 X-Y 章）`
- MilestoneForm：order_index + type + title + description + chapter_start/end + status

---

## 8. 测试

同 M3c-D 模式（schema + API + retrieval + prompts + form）。

---

## 9. 验收清单

| # | 验收项 |
|---|---|
| 1 | story_milestones 表 + 索引 + migration |
| 2 | CRUD API |
| 3 | assemble_context 注入全部 milestones |
| 4 | assemble_review_context 注入全部 milestones |
| 5 | writer/reviewer user.j2 渲染"故事蓝图"段 |
| 6 | ActivityBar 🗺️ 图标 |
| 7 | /outline 页面：列表 + 新建 + 编辑 |
| 8 | 全后端 + 前端 + E2E 测试通过 |

---

## 10. 未来扩展

- **M4b-2 Discuss Agent**：基于里程碑做多分支推演
- 里程碑拖拽排序
- 自动 status（finalize 章节时更新）
- 里程碑与 events/plot_lines 关联
