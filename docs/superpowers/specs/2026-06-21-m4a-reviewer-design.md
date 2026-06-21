# NovelAI M4a — Reviewer Agent 设计文档

- **日期**：2026-06-21
- **状态**：草案（待用户审阅）
- **范围**：M4a = 章节审稿 Agent + 5 维度合并 LLM 调用 + Modal 展示 + TipTap 高亮 + generation_logs 审计
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要 + 硬事实）、M3b（向量检索）、M3c-A（relationships）、M3c-B（character_states）、M3c-C（events + foreshadows）已完成

> M4 拆分为 2 个独立子项目（**A Reviewer** / B Discuss）。本文档仅覆盖 **A**。

---

## 1. 目标与非目标

### 1.1 目标

让用户写完章节后能一键自查 5 个维度的问题：

1. 用户在章节工作区点 "🔍 审稿" 按钮（与 "完成本章" 并列）
2. 触发 **1 次 LLM 调用**（5 维度合并，沿用 Extractor 模式）
3. 返回 `Issue[]`，按 severity/category 分类
4. 审稿调用同时写入 `generation_logs`（model_task='reviewer'）做审计
5. Modal 弹窗显示 Issue 列表（category 分组 + severity 着色）
6. TipTap 自定义 `IssueHighlight` Mark 在编辑器高亮 `Issue.location`（精确匹配失败时优雅降级）
7. 用户点 Issue 卡片 → 编辑器滚动到高亮位置

### 1.2 非目标（M4a 不做）

- Discuss Agent（多分支推演）— M4b
- 自动审稿（finalize 后自动跑）
- 异步审稿（SSE 流式 / 后台任务队列）— M4e
- Issue 持久化（reviews/issues 表）
- inline 标注锚定到精确字符 offset
- 自动应用 suggestion 到原文
- ContextBudget 自动裁剪（章节 50+ 时 token 压力，M4+ 处理）
- LLM 真实 API 集成测试（全部 mock）

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 维度 prompt 策略 | **方案 B：1 次合并调用** | 与 Extractor 模式一致；1x 成本/延迟；维度间上下文共享 |
| 触发方式 | **手动按钮** | 用户控制成本；非每章必审 |
| 同步性 | **同步**（客户端等 5-10s） | 与 finalize 同模式；YAGNI 异步基础设施 |
| Issue 持久化 | **不存结构化，仅 generation_logs 审计** | 审稿是一次性诊断；YAGNI 历史回看 |
| UI 呈现 | **Modal** | 匹配"审完就改稿"短交互流 |
| 高亮方案 | **方案 2：TipTap Mark + 优雅降级** | 1 天 ROI 高；不匹配时降级到 modal 显示 |
| Prompt 约束 location | **要求 verbatim 引用，10-50 字** | 前端 substring match 可靠 |
| 路由 | `reviewer` 任务用 sonnet-4-6（spec §4.6） | 沿用 Extractor 路由模式 |
| retrieval 扩展 | **新建 `assemble_review_context()`**（与 assemble_context 分离） | review 需要更丰富上下文（state/relationship history + events）；不污染写作路径 |
| `_target_has_external_payoff` | **从 events.py 复制到 retrieval.py**（不导入） | Reviewer 不应依赖 events API 内部函数 |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   └── retrieval.py                     # 修改：新增 assemble_review_context()
├── agents/
│   └── reviewer.py                      # 新增：Reviewer Agent 编排
├── llm/prompts/reviewer/
│   ├── system.j2                        # 新增：5 维度规则 + JSON schema
│   └── user.j2                          # 新增：上下文 + 待审章节
├── api/
│   └── chapters_review.py               # 新增：POST /api/chapters/{id}/review
├── main.py                              # 修改：注册 chapters_review router
├── memory/errors.py                     # 修改：加 ReviewError
└── models/
    └── review.py                        # 新增：Issue + ReviewResponse

web/
├── components/editor/
│   ├── ReviewButton.tsx                 # 新增：EditorToolbar 中的审稿按钮
│   ├── ReviewModal.tsx                  # 新增：Issue 列表 modal
│   ├── EditorToolbar.tsx                # 修改：加 ReviewButton slot
│   ├── ChapterEditor.tsx                # 修改：注册 IssueHighlight Mark
│   └── tiptap/
│       └── IssueHighlight.ts            # 新增：TipTap Mark 扩展
├── lib/
│   ├── store.ts                         # 修改：加 reviewIssues slice
│   ├── api.ts                           # 修改：加 reviewChapter
│   ├── queries.ts                       # 不变（不用 React Query；用 Zustand）
│   └── types.ts                         # 修改：加 Issue + ReviewResponse

tests/                                   # 后端
├── test_reviewer_prompts.py             # 新增
├── test_reviewer_agent.py               # 新增
├── test_chapters_review.py              # 新增
└── test_assemble_review_context.py      # 新增

web/tests/                               # 前端
├── ReviewButton.test.tsx                # 新增
├── ReviewModal.test.tsx                 # 新增
└── e2e/review-highlight.spec.ts         # 新增
```

### 2.1 职责边界

- `app/memory/retrieval.py`：M2a 既有 `assemble_context`（写作用，最小化 token）+ 新增 `assemble_review_context`（审稿用，最大化诊断信息）
- `app/agents/reviewer.py`：薄编排。组装 prompt → 调 `router.complete` → 解析 JSON → 写 generation_logs（事务）
- `app/api/chapters_review.py`：薄包装。校验 chapter → 调 reviewer → 异常映射 HTTP
- `web/components/editor/ReviewButton.tsx`：触发审稿，更新 Zustand store
- `web/components/editor/ReviewModal.tsx`：纯展示组件，从 store 读 issues
- `web/components/editor/tiptap/IssueHighlight.ts`：TipTap Mark 扩展，处理高亮渲染与清除

### 2.2 依赖方向

沿用既有单向依赖：`api → agents → memory → llm → DB`。Reviewer 不调 Writer/Extractor/Discuss。

---

## 3. Pydantic Schema

### 3.1 `app/models/review.py`

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

**字段说明：**

- `severity`：error（必须修改）/ warn（建议）/ info（可选）
- `category`：5 维度之一；spec §4.2 原始枚举没有 `worldview`，本设计加上对应第 5 维度
- `location`：**verbatim 引用**，prompt 强约束 10-50 字；空字符串表示整章性问题（如"节奏过快"）
- `description`：必填，空则跳过
- `suggestion`：可空（用户判断问题但无具体建议）

---

## 4. Retrieval：`assemble_review_context()`

### 4.1 设计

`app/memory/retrieval.py` 新增 `ReviewContextBundle` dataclass + `assemble_review_context()` 函数。**不复用** `assemble_context`（写作用，最小 token）—— review 需要更广上下文，混用会污染写作路径。

```python
@dataclass
class ReviewContextBundle:
    project: Project
    world_overview: WorldOverview | None
    chapter: Chapter                          # the chapter being reviewed
    characters: list[Character]               # involved (resolved via last_involved_character_ids)
    character_states_history: dict[int, list[CharacterStateSnapshot]]
                                              # character_id → last N states (newest first)
    relationships: list[RelationshipView]     # all current-valid relationships in project
    events: list[EventRead]                   # all events with derived payoff_of + is_unpaid
    lore_entries: list[LoreEntry]             # all lore in project
    recent_chapter_summaries: list[ChapterSummary]
                                              # all chapters' summaries (not just last 2)
```

### 4.2 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| characters 解析 | `chapter.last_involved_character_ids` 或回退全项目 | 与 assemble_context 一致 |
| state_history_limit | 5（最近 5 条状态轨迹） | 足够看趋势；token 控制 |
| relationships 范围 | 全项目当前有效（不只涉及人物对） | plot 可能跨多对关系 |
| events 范围 | 全项目事件（含 foreshadows + is_unpaid） | 伏笔完整性需全局视角 |
| lore_entries 范围 | 全项目 lore | 世界观一致性需对照所有设定 |
| chapter_summaries | 全项目所有章节摘要 | 情节矛盾需跨章对照 |

### 4.3 `_target_has_external_payoff` 复用

events.py 已有此 helper（M3c-C Prep 1）。Reviewer 也需要它计算 `is_unpaid`。两种选择：

- **A：复制到 retrieval.py**（推荐）—— 解耦，Reviewer 不依赖 events API
- B：从 events.py 导入 —— 引入跨 API 依赖

选 A。代码重复 < 耦合风险。

---

## 5. Reviewer Agent

### 5.1 接口契约

```python
# app/agents/reviewer.py

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

    Flow:
      1. assemble_review_context(db, chapter_id)
      2. render reviewer/system.j2 + user.j2
      3. router.complete(request)  # 1 调用
      4. parse JSON → list[Issue] (with tolerance)
      5. INSERT generation_logs (model_task='reviewer')
      6. return ReviewResult

    Raises:
        ChapterNotFoundError: chapter does not exist.
        ReviewError: LLM returned non-JSON or invalid structure.
    """
```

### 5.2 LLM 响应格式

```json
{
  "issues_by_category": {
    "character": [
      {
        "severity": "error",
        "location": "李雷笑了笑，转身离开",
        "description": "李雷本章突然对韩梅宽容，与第 5 章仇人关系不符",
        "suggestion": "补充心理转变过程，或维持敌意"
      }
    ],
    "relationship": [...],
    "plot": [...],
    "foreshadow": [...],
    "worldview": [...]
  }
}
```

### 5.3 容错处理

| 情形 | 处理 |
|---|---|
| LLM `stop_reason == "max_tokens"` | 抛 `ReviewError`（避免解析截断的 JSON） |
| 非 JSON | 抛 `ReviewError` |
| `issues_by_category` 不是 dict | 抛 `ReviewError` |
| 缺某 category 的 key | 当作空数组（5 维度可能某维度无问题） |
| 未知 category（如 "foo"） | 跳过该 category，记 warning log |
| category 数组非 list | 跳过该 category |
| 数组元素非 dict | 跳过该 issue |
| severity 不在枚举 | 默认 "info" |
| category 已知但 issue 内未声明 | 用 dict key 作为 category |
| description 为空 | 跳过该 issue（没描述无意义） |
| location 为空 | 接受（整章性问题如"节奏过快"） |
| suggestion 为空 | 接受（用户判断问题但无具体建议） |

### 5.4 generation_logs 审计

每次审稿写一条 `generation_logs`：

```python
GenerationLog(
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
```

**复用 M2a 表**（沿用 Extractor 模式）。

---

## 6. Prompt 模板

### 6.1 `reviewer/system.j2`

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

## 3. 情节矛盾（plot）
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
        "location": "原文逐字引用，10-50 字",
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

### 6.2 `reviewer/user.j2`

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

---

## 7. API 契约

### 7.1 端点

```
POST /api/chapters/{chapter_id}/review
```

### 7.2 请求/响应

**请求：** 空 body（保留扩展）。

**响应：** `ReviewResponse`

```python
class ReviewResponse(BaseModel):
    chapter_id: int
    issues: list[Issue]
    log_id: int
```

**响应矩阵：**

| 情形 | HTTP | Body |
|---|---|---|
| 成功 | 200 | `{"chapter_id": ..., "issues": [...], "log_id": ...}` |
| 章节不存在 | 404 | `{"detail": "chapter not found"}` |
| LLM 调用失败（超时/限流/网络） | 502 | `{"detail": "llm call failed: ..."}` |
| JSON 解析失败 / 结构错误 | 422 | `{"detail": {"error": "review_failed", "reason": "..."}}` |
| 其他异常 | 500 | `{"detail": "internal error"}` |

### 7.3 `app/api/chapters_review.py`

```python
"""M4a: POST /api/chapters/{id}/review — sync review across 5 dimensions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.agents.reviewer import review_chapter
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

**注册到 `app/main.py`：**

```python
from app.api import chapters_review
app.include_router(chapters_review.router, prefix="/api/chapters",
                   tags=["chapters_review"])
```

---

## 8. 前端 UI 与数据流

### 8.1 ReviewButton（EditorToolbar 中）

放在 `EditorToolbar` 右侧，紧挨 `FinalizeButton`：

```
┌─────────────────────────────────────────────────────────────────┐
│ 第二章                            798 字  🗑️  ✓ 完成本章  🔍 审稿 │
└─────────────────────────────────────────────────────────────────┘
```

**状态机：**
- `idle`：按钮显示 "🔍 审稿"
- `reviewing`：按钮 disabled，显示 "⏳ 审稿中..."
- `done`：toast 显示 "审稿完成：N 条 Issue"，自动开 modal
- `error`：toast 报错

### 8.2 Zustand store 扩展（`lib/store.ts`）

```typescript
interface ReviewState {
  issuesByChapter: Record<number, Issue[]>;
  modalOpenFor: number | null;
  setIssues: (chapterId: number, issues: Issue[]) => void;
  openModal: (chapterId: number) => void;
  closeModal: () => void;
  clearIssues: (chapterId: number) => void;
}
```

**关键行为：**
- `setIssues(chapterId, issues)` 同时自动 set `modalOpenFor = chapterId`
- 切换章节时调 `clearIssues(oldChapterId)` 防止旧高亮残留

**Zustand persist 配置**：reviewIssues slice **不持久化**（每次启动从头开始）。

### 8.3 TipTap `IssueHighlight` Mark

`web/components/editor/tiptap/IssueHighlight.ts`：

```typescript
import { Mark, mergeAttributes } from "@tiptap/core";

export interface IssueHighlightAttrs {
  issueId: string;
  severity: "error" | "warn" | "info";
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    issueHighlight: {
      setIssueHighlight: (attrs: IssueHighlightAttrs, from: number, to: number) => ReturnType;
      unsetAllIssueHighlights: () => ReturnType;
    };
  }
}

export const IssueHighlight = Mark.create({
  name: "issueHighlight",

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
    const severity = HTMLAttributes.severity || "info";
    const colors = {
      error: "bg-red-300/50",
      warn: "bg-yellow-300/50",
      info: "bg-blue-300/50",
    };
    return [
      "mark",
      mergeAttributes(HTMLAttributes, {
        "data-issue-id": HTMLAttributes.issueId,
        class: colors[severity as keyof typeof colors],
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setIssueHighlight:
        (attrs, from, to) => ({ editor }) => {
          editor.commands.setTextSelection({ from, to });
          editor.commands.setMark(this.name, attrs);
          return true;
        },
      unsetAllIssueHighlights:
        () => ({ tr, state }) => {
          state.doc.descendants((node, pos) => {
            node.marks.forEach((mark) => {
              if (mark.type.name === this.name) {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            });
          });
          return true;
        },
    };
  },
});
```

注册到 `ChapterEditor.tsx`：

```typescript
import { IssueHighlight } from "@/components/editor/tiptap/IssueHighlight";
// 加到 useEditor({ extensions: [...existingExtensions, IssueHighlight] })
```

### 8.4 高亮应用逻辑（在 ReviewModal effect 中）

```typescript
useEffect(() => {
  const editor = editorRef.current;
  if (!editor) return;

  // Clear previous highlights
  editor.commands.unsetAllIssueHighlights();

  if (!issues.length) return;

  // For each issue with non-empty location, find & highlight
  issues.forEach((issue, idx) => {
    if (!issue.location) return;
    const text = editor.getText();
    const idx_in_text = text.indexOf(issue.location);
    if (idx_in_text < 0) return;  // graceful degrade
    const from = idx_in_text + 1;  // ProseMirror positions are 1-indexed
    const to = from + issue.location.length;
    editor.commands.setIssueHighlight(
      { issueId: `${idx}`, severity: issue.severity },
      from, to
    );
  });
}, [issues, editor]);
```

**注**：`editor.getText()` offset → ProseMirror pos 转换是简化版。TipTap 的实际位置计算需考虑块级节点偏移（段落、列表等）。实施 Task 11 时需用更精确的 API（如 `editor.state.doc.textBetween` 或社区 `prosemirror-find` 模式）。这是 M4a 中最容易踩坑的部分，预留时间。

### 8.5 ReviewModal 组件

```
┌─────────────────────────────────────────────────────────┐
│ 审稿报告：第 N 章                              [× 关闭]   │
│─────────────────────────────────────────────────────────│
│ 共 5 条 Issue：🔴 1 · 🟡 3 · 🔵 1                      │
│                                                         │
│ ▼ 人物一致性（1）                                        │
│   🔴 李雷本章突然对韩梅宽容，与第 5 章仇人关系不符        │
│      位置："李雷笑了笑，转身离开"                        │
│      建议：补充心理转变过程，或维持敌意                  │
│                                                         │
│ ▼ 关系合理性（2）                                        │
│   🟡 ...                                                │
│   🟡 ...                                                │
│                                                         │
│ ▼ 伏笔完整性（1）                                        │
│   🔵 ...                                                │
│                                                         │
│ ▼ 世界观一致性（1）                                      │
│   🟡 ...                                                │
│                                                         │
│                [📋 复制全部]  [↻ 重新审稿]  [✓ 我知道了] │
└─────────────────────────────────────────────────────────┘
```

**交互：**
- 点击 Issue 卡片 → `editor.commands.setTextSelection(foundPos)` + `editor.commands.scrollIntoView()`
- "📋 复制全部" → 格式化所有 Issue 到剪贴板
- "↻ 重新审稿" → 重新触发 `api.reviewChapter(chapterId)`，替换 modal 内容
- "✓ 我知道了" → `closeModal()`（不清除 issues，便于用户参照修改；切章节时才清）

### 8.6 Click-to-scroll

```typescript
const handleIssueClick = (issueId: string) => {
  const editor = editorRef.current;
  if (!editor) return;
  let foundPos: number | null = null;
  editor.state.doc.descendants((node, pos) => {
    if (foundPos !== null) return false;
    const mark = node.marks.find((m) => m.attrs.issueId === issueId);
    if (mark) {
      foundPos = pos;
      return false;
    }
  });
  if (foundPos !== null) {
    editor.commands.setTextSelection(foundPos);
    editor.commands.scrollIntoView();
  }
};
```

---

## 9. 测试策略

### 9.1 后端单元测试（不调 LLM）

**`tests/test_reviewer_prompts.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_render_reviewer_system` | system.j2 含 5 维度规则 + JSON schema + location 约束 |
| `test_render_reviewer_user_full` | user.j2 渲染所有 context 字段 |
| `test_render_reviewer_user_minimal` | 空 characters/relationships/events 时不抛错 |
| `test_render_reviewer_user_no_world_overview` | world_overview 缺失时不抛错 |

**`tests/test_assemble_review_context.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_assemble_review_context_minimal` | 仅 1 章无 character_states 时不抛错 |
| `test_assemble_review_context_state_history_limit` | state_history_limit=3 时只取最近 3 条 |
| `test_assemble_review_context_includes_all_relationships` | 全项目当前有效关系（不只涉及人物对） |
| `test_assemble_review_context_includes_events_with_payoff` | events 含派生 payoff_of + is_unpaid |
| `test_assemble_review_context_excludes_current_chapter_summary` | 不返回当前章的摘要 |
| `test_assemble_review_context_resolves_involved_characters` | last_involved_character_ids 解析正确 |

**`tests/test_reviewer_agent.py` 新增（mock LLM）：**

| 测试 | 验证 |
|---|---|
| `test_review_chapter_returns_issues` | mock LLM 完整 JSON → 返回 ReviewResult |
| `test_review_chapter_invalid_json_raises` | mock LLM 非 JSON → ReviewError |
| `test_review_chapter_missing_issues_by_category_raises` | 缺字段 → ReviewError |
| `test_review_chapter_issues_by_category_not_dict_raises` | 非 dict → ReviewError |
| `test_review_chapter_unknown_category_skipped` | category="foo" → 跳过 |
| `test_review_chapter_unknown_severity_defaults_info` | severity="critical" → info |
| `test_review_chapter_empty_description_skipped` | description="" → 跳过 |
| `test_review_chapter_empty_location_accepted` | location="" → 接受（整章性问题） |
| `test_review_chapter_empty_suggestion_accepted` | suggestion="" → 接受 |
| `test_review_chapter_writes_generation_log` | generation_logs 含 reviewer 记录 |
| `test_review_chapter_max_tokens_raises` | stop_reason="max_tokens" → ReviewError |
| `test_review_chapter_not_found` | chapter_id=99999 → ChapterNotFoundError |

### 9.2 API 测试

**`tests/test_chapters_review.py` 新增：**

| 测试 | 验证 |
|---|---|
| `test_review_returns_404_unknown_chapter` | 章节不存在 |
| `test_review_success` | mock router → 200 + issues + log_id |
| `test_review_llm_failure_returns_502` | mock router raise → 502 |
| `test_review_invalid_json_returns_422` | mock router 返回非 JSON → 422 |

### 9.3 前端单元测试

**`tests/ReviewButton.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_button_idle_text` | 默认 "🔍 审稿" |
| `test_button_disabled_during_reviewing` | 点击后 disabled |
| `test_button_success_toast_shows_count` | 200 → toast "审稿完成：N 条 Issue" |
| `test_button_error_toast_on_502` | 502 → toast 错误 |
| `test_button_triggers_modal_open` | 成功后 modalOpenFor 设置 |

**`tests/ReviewModal.test.tsx` 新增：**

| 测试 | 验证 |
|---|---|
| `test_modal_renders_by_category` | 按 category 分组 |
| `test_modal_severity_icons` | error/warn/info 显示对应图标 |
| `test_modal_copy_all` | 复制按钮调用 clipboard |
| `test_modal_empty_issues` | 0 Issue 时显示"未发现问题" |
| `test_modal_close_button` | "✓ 我知道了" → closeModal |
| `test_modal_click_issue_triggers_scroll` | 点击 Issue 调 editor scrollIntoView（mock editor） |

### 9.4 E2E 测试

**`tests/e2e/review-highlight.spec.ts`：**

```
1. 创建项目 + 人物"李雷" + 章节带正文（含可定位的句子"李雷笑了笑，转身离开"）
2. mock /api/chapters/{id}/review 返回 issues_by_category（含 location="李雷笑了笑，转身离开"）
3. 进入章节页 → 点 "🔍 审稿"
4. 等 modal 弹出
5. 验证按 category 分组显示
6. 点 "✓ 我知道了" → modal 关闭
7. （可选）验证编辑器中对应文字有高亮（DOM 检查 mark[data-issue-id]）
```

### 9.5 YAGNI 不测

- LLM 真实 API
- 异步审稿（SSE）
- Issue 持久化
- inline 高亮精确字符 offset
- ContextBudget 自动裁剪

### 9.6 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/agents/reviewer.py` | >90% |
| `app/api/chapters_review.py` | >85% |
| `app/memory/retrieval.py` (assemble_review_context) | >85% |
| `app/llm/prompts/reviewer/*.j2` | 100%（渲染） |
| 前端 `ReviewButton` + `ReviewModal` | >85% |

---

## 10. M4a 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `POST /api/chapters/{id}/review` 同步返回 ReviewResponse | curl + 单测 |
| 2 | 5 维度合并 1 次 LLM 调用 | mock router call_count == 1 |
| 3 | generation_logs 记录每次审稿（model_task='reviewer'） | sqlite3 直查 |
| 4 | LLM 返回非 JSON → 422 | 单测 |
| 5 | 缺 issues_by_category 字段 → 422 | 单测 |
| 6 | 任一 category 缺失 → 当作空数组 | 单测 |
| 7 | description 为空的 Issue → 跳过 | 单测 |
| 8 | severity 非枚举 → 默认 info | 单测 |
| 9 | 未知 category → 跳过 + warning log | 单测 |
| 10 | ReviewButton 显示在 EditorToolbar 与 FinalizeButton 并列 | 手工 |
| 11 | 点审稿按钮 → 5-10s spinner → modal 弹出 | E2E |
| 12 | Modal 按 category 分组 + severity 图标 | 单测 + 手工 |
| 13 | 点 "📋 复制全部" → 剪贴板含所有 Issue | 单测 |
| 14 | 点 "↻ 重新审稿" → 替换 modal 内容 | 手工 |
| 15 | 点 "✓ 我知道了" → modal 关闭 | 单测 |
| 16 | 切换章节 → 清除旧 Issue + 高亮 | 手工 |
| 17 | TipTap 编辑器渲染 IssueHighlight Mark（精确匹配的 location） | E2E |
| 18 | location 在原文中找不到 → 不高亮（优雅降级） | 单测 |
| 19 | 点 Issue 卡片 → 编辑器滚动到高亮位置 | 手工 |
| 20 | 用户编辑高亮文本 → Mark 自动跟随（TipTap 标准行为） | 手工 |
| 21 | 全后端测试通过 | `pytest -v` |
| 22 | 全前端测试通过 | `npm test` |
| 23 | 全 E2E 通过 | `npm run test:e2e` |

---

## 11. 待定 / 开放问题

1. **TipTap 文本 offset → ProseMirror pos 转换**：8.4 给出简化版（`idx_in_text + 1`），实际章节有段落/列表等块级节点，pos 计算更复杂。Task 11 实施时需用 `editor.state.doc.textBetween` 或类似 API 做精确匹配。如果踩坑严重，可降级为"不高亮，仅 scrollIntoView 到大致位置"。

2. **多匹配处理**：location 在原文出现多次时，目前只高亮第一个。可改为高亮所有（每个 issue 一个 mark），但 UI 上 Issue 卡片与多个 mark 的关联复杂。M4a v1 只高亮第一个。

3. **章节修改后高亮失效**：用户改完稿后原 location 可能不存在（被改了）。当前不自动清除高亮；用户点 "↻ 重新审稿" 替换。可加"高亮失效检测"，但 YAGNI v1。

4. **ContextBudget**：第 50+ 章审稿时，全项目 lore + events + summaries 可能超 token 上限。M4a 不处理（沿用 finalize 策略：超则 LLM 报错 → 502）。M4+ 加自动裁剪。

5. **Reviewer vs Writer prompt 风格冲突**：Reviewer 说"李雷不应宽容"，但 Writer 可能因 retrieval 召回了"宽容"的过往场景而写出宽容。两个 Agent 各自判断，不互相通信（spec §4.5）。用户决策。

6. **Issue.category 增加 "worldview"**：spec §4.2 原 Issue.category 枚举为 `Literal["character", "relationship", "plot", "foreshadow"]`（4 个），但 §4.2 同时定义了第 5 维度"世界观一致性"。本设计加 `"worldview"` 使枚举与维度对齐。这是与 spec 的小偏差，但合理。

---

## 12. 未来扩展（v2+，不在 M4a 范围）

- **M4b Discuss Agent**：多分支推演；复用 `assemble_review_context` 但输出对比表
- **M4+ 自动审稿**：finalize 时可选"审稿后再定稿"
- **M4+ Issue 持久化**：reviews/issues 表，支持历史回看 + 跨章统计
- **M4+ inline 高亮精确锚定**：LLM 输出 ProseMirror pos 或更精确的引用机制
- **M4+ ContextBudget**：token 超限时自动裁剪 lore/events/summaries
- **M4+ 审稿模板**：用户自定义维度（如"悬疑感"、"节奏"）
- **M4+ 审稿对比**：连续两次审稿结果对比，看 Issue 是否解决
