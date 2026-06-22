# NovelAI M4b-2 — Discuss Agent（多分支推演）设计文档

- **日期**：2026-06-22
- **状态**：草案（待用户审阅）
- **范围**：M4b-2 = Discuss Agent + POST /api/chapters/{id}/discuss + DiscussModal（章节工作区 💬 按钮）
- **依赖**：M1-M4a + M3d + M4b-1 全部完成（assemble_review_context 含 characters/relationships/events/milestones/lore/summaries/plot_lines）

> 原始 spec 的 4-agent 愿景最后一块（Writer + Reviewer + Extractor + **Discuss**）。

---

## 1. 目标与非目标

### 1.1 目标

让用户在写章节前能探索"如果...会怎样"的多分支可能性：

1. 用户在章节工作区点 `💬 探讨` → 输入设想（自由文本）
2. 1 次 LLM 调用 → 3 个不同方向的分支推演
3. 每分支分析：与已有事实的冲突、新机会、人物弧光影响
4. LLM 推荐最佳分支 + 理由
5. 审计写 `generation_logs`（model_task='discuss'）

### 1.2 非目标

- 自动将选定分支注入 Writer outline（用户手动写）
- 多轮对话（单次 question → answer）
- 异步/SSE
- Discuss 结果持久化（仅 generation_logs 审计）
- 蓝图级探讨（移动里程碑等——未来扩展）

### 1.3 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| UI | 章节工作区 Modal（与 ReviewModal 同模式） | 用户已在章节上下文 |
| 分支数量 | 固定 3 个 | spec §4.3 原意；简单 |
| LLM 调用 | 1 次合并（与 Reviewer 同模式） | 1x 成本/延迟 |
| 同步性 | 同步 | 与 finalize/review 一致 |
| Context | 复用 `assemble_review_context` | 已含全部结构化记忆 |
| 持久化 | 仅 generation_logs | Discuss 是一次性探索 |
| 路由 | `discuss` → `claude-sonnet-4-6` | router 已预留 |

---

## 2. Pydantic Schemas

`app/models/discuss.py`:

```python
from pydantic import BaseModel


class DiscussBranch(BaseModel):
    label: str              # "A" / "B" / "C"
    title: str              # 简短标题（≤10 字）
    summary: str            # 2-3 句话描述分支走向
    conflicts: str          # 与已有事实/关系的冲突分析
    opportunities: str      # 新机会（伏笔/人物发展/情节转折）
    character_impact: str   # 对涉及人物弧光的影响


class DiscussRequest(BaseModel):
    question: str


class DiscussResponse(BaseModel):
    question: str           # 回显用户问题
    branches: list[DiscussBranch]
    recommended: str        # "A" / "B" / "C"
    reasoning: str          # 推荐理由
    log_id: int
```

---

## 3. Discuss Agent

`app/agents/discuss.py`，与 Reviewer 同模式：

### 3.1 流程

1. `assemble_review_context(db, chapter_id)` → 全部上下文
2. 渲染 `discuss/system.j2` + `discuss/user.j2`（含用户 question）
3. `router.complete(request)` — 1 次调用
4. 解析 JSON → `DiscussBranch[]` + `recommended` + `reasoning`
5. 写 `generation_logs`（model_task='discuss'）

### 3.2 容错

| 情形 | 处理 |
|---|---|
| 非 JSON | `DiscussError` |
| `stop_reason == "max_tokens"` | `DiscussError` |
| branches 不是 list | `DiscussError` |
| branches 不是 3 个 | 取前 3 个（多截少不补） |
| branch 缺字段 | 空字符串 |
| 缺 recommended | 默认 "A" |
| 缺 reasoning | 空字符串 |
| branch 元素非 dict | 跳过 |

### 3.3 generation_logs

```python
GenerationLog(
    chapter_id=chapter_id,
    project_id=...,
    beat_text="(discuss)",
    instruction=question,  # 用户的问题存这里
    ...
    model_task="discuss",
    status="done",
)
```

---

## 4. Prompt 模板

### 4.1 `discuss/system.j2`

```
你是一位经验丰富的小说编辑顾问。用户提出了一个情节设想，你要从 3 个不同方向推演可能性。

# 你的任务
1. 基于"如果...会怎样"的设想，生成恰好 3 个不同方向的分支
2. 每个分支分析：与已有事实的冲突、新机会、对人物弧光的影响
3. 推荐最佳分支 + 给出理由

# 分支要求
- 3 个分支必须方向不同（不要 3 个都说"好"或"不好"）
- 每个分支要有实质内容，不要空泛
- 基于项目已有的人物/关系/事件/伏笔/蓝图进行分析
- label 分别为 "A"、"B"、"C"

# 输出格式

严格输出 JSON。不要输出 JSON 之外的任何内容（包括代码块标记）。

{
  "branches": [
    {
      "label": "A",
      "title": "简短标题（≤10字）",
      "summary": "2-3句话描述这个方向的走向",
      "conflicts": "与已有事实/关系的冲突分析",
      "opportunities": "新机会（伏笔/人物发展/情节转折）",
      "character_impact": "对涉及人物弧光的影响"
    },
    {"label": "B", ...},
    {"label": "C", ...}
  ],
  "recommended": "A",
  "reasoning": "推荐理由（2-3句话）"
}

# 重要
- branches 数组必须恰好包含 3 个元素
- recommended 必须是 "A"、"B" 或 "C" 之一
- 不要修改原文，只产出分析报告
```

### 4.2 `discuss/user.j2`

与 `reviewer/user.j2` 结构相同（project/world_overview/chapter/characters/relationships/events/lore/milestones/summaries），末尾加：

```
# 用户的设想
{{ question }}

请从 3 个不同方向推演这个设想的后果，并给出推荐。
```

---

## 5. API 契约

```
POST /api/chapters/{chapter_id}/discuss
Body: {"question": "如果让李雷在这里和韩梅和解？"}
Response: DiscussResponse
```

错误码与 Reviewer 一致：
- 404 chapter 不存在
- 422 JSON 解析失败 / max_tokens
- 502 LLM 调用失败

`app/api/chapters_discuss.py` 与 `chapters_review.py` 同模式。

---

## 6. 前端 UI

### 6.1 DiscussButton（EditorToolbar）

```
│ ✓ 完成本章  🔍 审稿  💬 探讨 │
```

状态机：`idle` → `discussing` (spinner) → `done` (Modal 弹出)

### 6.2 DiscussModal

```
┌─────────────────────────────────────────────────────────┐
│ 💬 情节探讨                                    [× 关闭]   │
│─────────────────────────────────────────────────────────│
│ 你的设想：                                               │
│ [如果让李雷在这里和韩梅和解？______________]              │
│                                              [推演 →]    │
│                                                         │
│ ── 推演结果 ──                                           │
│ ⭐ 推荐：分支 B                                          │
│ 理由：...                                                │
│                                                         │
│ ▼ 分支 A：直接和解                                       │
│   走向：...  冲突：...  机会：...  人物：...              │
│                                                         │
│ ▼ 分支 B：假意和解，暗中布局 ✓ 推荐                      │
│   ...                                                   │
│                                                         │
│ ▼ 分支 C：拒绝和解，加深矛盾                             │
│   ...                                                   │
│                                                         │
│                              [📋 复制全部]  [✓ 知道了]   │
└─────────────────────────────────────────────────────────┘
```

推荐分支高亮（边框加粗或背景色）。

### 6.3 Zustand store

```typescript
interface DiscussState {
  resultByChapter: Record<number, DiscussResponse | null>;
  modalOpenFor: number | null;
  setResult: (chapterId: number, result: DiscussResponse) => void;
  closeModal: () => void;
  clearResult: (chapterId: number) => void;
}
```

---

## 7. 测试策略

同 Reviewer 模式：

| 测试 | 验证 |
|---|---|
| `test_render_discuss_system` | system.j2 含 3 分支规则 + JSON schema |
| `test_render_discuss_user` | user.j2 含 question + 上下文 |
| `test_discuss_chapter_returns_branches` | mock LLM → 3 branches + recommended |
| `test_discuss_invalid_json_raises` | 非 JSON → DiscussError |
| `test_discuss_truncates_extra_branches` | 4 branches → 取前 3 |
| `test_discuss_missing_recommended_defaults_a` | 缺 recommended → "A" |
| `test_discuss_writes_generation_log` | generation_logs 含 discuss 记录 |
| `test_discuss_not_found` | chapter_id=99999 → ChapterNotFoundError |
| API tests | 404 / success / 502 / 422 |
| Frontend tests | button states, modal renders, recommended highlight |
| E2E | discuss → modal → 3 branches → close |

---

## 8. 验收清单

| # | 验收项 |
|---|---|
| 1 | POST /api/chapters/{id}/discuss 返回 DiscussResponse |
| 2 | 1 次 LLM 调用 |
| 3 | generation_logs 审计 (model_task='discuss') |
| 4 | LLM 非 JSON → 422 |
| 5 | branches > 3 → 截断到 3 |
| 6 | DiscussButton 在 EditorToolbar |
| 7 | 点推演 → 5-10s → Modal 显示 3 分支 |
| 8 | 推荐分支高亮 |
| 9 | 复制全部 / 关闭按钮 |
| 10 | 全后端 + 前端 + E2E 测试通过 |

---

## 9. 未来扩展

- 蓝图级探讨（"如果把高潮从第 10 章移到第 15 章？"）
- 多轮对话（基于上一轮结果继续追问）
- 自动将选定分支的 summary 写入 chapter.outline
- 分支对比可视化（并排卡片）
