# NovelAI M2b — 前端编辑器（Frontend Editor）设计文档

- **日期**：2026-06-17
- **状态**：草案（待用户审阅）
- **范围**：M2b = 前端编辑器（Next.js + TipTap + 三栏 VS Code 风格布局）
- **依赖**：M1（地基）已完成；M2a（写作管线）已完成；后端契约见 `2026-06-16-m2a-writing-loop-design.md`

---

## 1. 目标与非目标

### 1.1 目标

为本地优先的小说写作工具构建**全功能前端**，覆盖：

1. **项目管理**（列表 / 创建 / 切换）
2. **章节编辑器**（TipTap 富文本，Markdown 双向，防抖自动保存）
3. **AI 写作闭环**（点"生成" → SSE 流式 → 实时打字机渲染 → "接受"插入编辑器）
4. **常驻层可视化**（右侧面板实时显示"AI 将看到的人物/地点/势力"）
5. **实体管理 UI**（人物库、设定库 [世界观/地点/势力]、章节列表）
6. **生成历史**（按章节查看，含完整 system/user prompt + token 用量）
7. **全局搜索**（项目内 substring 匹配章节/人物/设定）

### 1.2 非目标（M2b 不做）

- Extractor Agent 触发 UI（M3）
- Reviewer / Discuss Agent（M4）
- 向量检索 / 语义搜索（M3）
- 多用户 / 协作编辑
- 移动端 / 响应式（仅桌面端浏览器）
- PWA / 离线模式
- 主题切换（仅暗色，VS Code 风格）
- 国际化（仅中文）

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| 范围 | M2b 全功能一次到位 | 用户明确选择，不分阶段；后端契约已齐 |
| 布局 | VS Code 风格三栏（活动栏 + 左侧列表 + 编辑器 + 右侧常驻层 + 底部生成面板） | 编辑器居中、右侧常驻层始终可见，能直接看到"AI 即将看到什么"，对调试 prompt 极有帮助 |
| 端口 | 前端 3300 / 后端 8005 | 用户环境避开 3000/8000 占用 |
| 端口落地 | 后端通过环境变量配置（具体写法实现阶段定） | 不动 `app/config.py`；最小化后端改动 |
| 内容格式 | Markdown（与 M2a DB 一致） | TipTap 加 Markdown 扩展读写；单一来源，避免双重存储 |
| TipTap 版本 | **v3** + 官方 `@tiptap/extension-markdown` | React 19 原生支持；Markdown 扩展已官方化，不再依赖社区包 |
| Next.js 渲染 | **全 Client Component**，无 Server Component 预取 | 本地单用户无 SEO/CDN 需求；省 HydrationBoundary 复杂度 |
| SSE 消费 | `fetch + ReadableStream.getReader()` 手工解析 | `EventSource` 不支持 POST body；fetch 灵活可控 |
| 技术栈 | Next.js 15 App Router + React 19 + TipTap v3 + Tailwind + Zustand + TanStack Query | 主流栈；TipTap 成熟，TanStack Query 管缓存，Zustand 管 UI 状态 |
| 项目结构 | `web/` 子目录独立 Next.js 项目，与 `app/` 后端平级 | 前后端解耦，独立开发/调试，部署灵活 |
| 保存策略 | `onUpdate` 防抖 500ms + `onBlur` 立即 | 平衡 SQLite WAL 压力与可靠性 |
| AI 内容接受 | 用户主动点"接受"按钮，插入光标位置 | 用户保留对内容的最终决定权 |
| AI 内容视觉标记 | 不做 | TipTap 无原生段落作者支持；YAGNI；M4+ 再加 |
| ContextPanel 数据源 | 显示"默认集 + 当前生成参数"；默认集来自 `chapters.last_involved_character_ids` + `last_location_id` | 打开章节即看到上下文；BottomPanel 表单预填这两个字段 |
| 后端默认集写回 | 生成 done 时后端自动 UPDATE 这两个字段 | 用户不重复劳动；多设备一致 |
| UI 状态持久化 | zustand `persist` 中间件 + localStorage | 栏宽、面板高度、BottomPanel 开关跨会话保持 |
| 历史页数据源 | `GET /api/generation-logs?project_id=X`（M2a list 端点加新参数） | 1 个请求拿项目所有日志，按 chapter_id 分组 |

---

## 2. 模块划分与文件结构

```
novelAI/
├── app/                            # 后端（M1+M2a 已存在，新增 CORS 配置）
│   └── main.py                     # 修改：加 CORSMiddleware
├── tests/                          # 后端测试（已有）
└── web/                            # 新建：Next.js 前端
    ├── package.json
    ├── tsconfig.json
    ├── next.config.mjs
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── .env.local                  # NEXT_PUBLIC_API_BASE=http://127.0.0.1:8005
    ├── app/                        # Next.js App Router
    │   ├── layout.tsx              # 根 layout：QueryClientProvider
    │   ├── globals.css             # Tailwind base + 暗色主题变量
    │   ├── page.tsx                # 首页：项目列表卡片
    │   ├── projects/
    │   │   └── [projectId]/
    │   │       ├── layout.tsx              # WorkspaceShell（三栏 + ActivityBar + BottomPanel）
    │   │       ├── page.tsx                # 项目首页（重定向到首章 or 提示新建）
    │   │       ├── chapters/
    │   │       │   ├── page.tsx            # 章节列表（活动栏 📚 激活）
    │   │       │   └── [chapterId]/
    │   │       │       └── page.tsx        # ★ 写作主界面（编辑器 + 右侧常驻层）
    │   │       ├── characters/
    │   │       │   └── page.tsx            # 人物库（👥）
    │   │       ├── lore/
    │   │       │   └── page.tsx            # 设定库（🌍，含世界观/地点/势力 子 tab）
    │   │       ├── history/
    │   │       │   └── page.tsx            # 生成历史（📜）
    │   │       └── search/
    │   │           └── page.tsx            # 全局搜索（🔍）
    │   └── settings/                        # 预留（M2b 不实现）
    │       └── page.tsx
    ├── components/
    │   ├── layout/
    │   │   ├── ActivityBar.tsx             # 最左图标条（5 个）
    │   │   ├── WorkspaceShell.tsx          # 三栏布局容器
    │   │   ├── SidePanel.tsx               # 第二栏（章节/人物/设定/历史列表）
    │   │   ├── EditorPane.tsx              # 第三栏（编辑器壳，含标题栏）
    │   │   ├── ContextPanel.tsx            # 右侧常驻层（人物/地点/势力预览）
    │   │   └── BottomPanel.tsx             # 底部生成面板（可调高度）
    │   ├── editor/
    │   │   ├── ChapterEditor.tsx           # TipTap 主编辑器（Client）
    │   │   ├── extensions.ts               # TipTap 扩展配置
    │   │   └── EditorToolbar.tsx           # 编辑器顶部工具栏（保存、字数）
    │   ├── generation/
    │   │   ├── GenerateForm.tsx            # 表单：beat_text + 人物 + 地点 + 指令
    │   │   ├── StreamView.tsx              # SSE 实时输出区
    │   │   ├── GenerationHistory.tsx       # 历史列表（点开看完整 prompt）
    │   │   └── useGenerate.ts              # 串起 SSE + store + Query 的 hook
    │   ├── entities/
    │   │   ├── ProjectPicker.tsx
    │   │   ├── ChapterItem.tsx
    │   │   ├── CharacterForm.tsx           # 人物编辑表单（内联 Editor 区）
    │   │   ├── LoreForm.tsx
    │   │   └── WorldOverviewForm.tsx
    │   └── ui/                             # 通用组件（Button、Modal、Drawer、Toast、Chip）
    ├── lib/
    │   ├── api.ts                  # typed fetch wrapper
    │   ├── sse.ts                  # SSE 消费（fetch + ReadableStream）
    │   ├── store.ts                # Zustand: UI 状态 + generate params
    │   ├── queries.ts              # TanStack Query hooks
    │   └── types.ts                # 与后端 Pydantic 对应的 TS 类型
    └── public/
```

### 2.1 职责边界

- `lib/` 只管 API 调用、状态、类型——零 React
- `components/` 按**业务领域**分组（layout/editor/generation/entities），不按技术层
- `app/` 只做路由和数据加载（Server Components 预取初始数据 → Client Components 接管交互）
- 单文件单一职责；超 300 行考虑拆

### 2.2 依赖方向

```
React 组件
   ├── TanStack Query  ──┐
   ├── Zustand Store   ──┼──► lib/api.ts ──► http://127.0.0.1:8005/api/*
   └── SSE Hook (useGenerate)
                          └──► lib/sse.ts  ──► (同上，POST /generate)
```

**单向**：组件 → lib → 后端。lib 不反向引用组件。

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| App Router vs Pages Router | App Router（Next.js 15 默认） | 文件即路由 |
| 渲染模式 | **全 Client Component**（页面文件直接 `"use client"`） | 本地单用户无 SEO/CDN 需求；省 HydrationBoundary 复杂度 |
| 编辑器内容格式 | Markdown（与 M2a DB 一致） | TipTap v3 官方 Markdown 扩展读写；避免双重存储 |
| SSE 消费 | `fetch + ReadableStream.getReader()` | EventSource 不支持 POST body；fetch 灵活 |
| API 客户端 | typed fetch wrapper（不引入 axios/swr） | 减少依赖；TanStack Query 已包缓存 |
| 状态管理 | TanStack Query（服务端状态） + Zustand `persist`（UI 状态） | 各司其职，不混；UI 状态跨会话 |
| 路由参数 | `[projectId]` 嵌套 | URL 自带工作区上下文：`/projects/1/chapters/2` |
| 主题 | 暗色（VS Code 风格） | 用户选了 VS Code 布局，调性一致 |

---

## 3. 数据流（API 客户端 + SSE 消费 + 状态）

### 3.1 lib/api.ts — Typed fetch wrapper

```typescript
const BASE = process.env.NEXT_PUBLIC_API_BASE!;  // http://127.0.0.1:8005

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, error);
  }
  return res.json();
}

export const api = {
  // Projects
  listProjects: () => http<Project[]>("/api/projects"),
  getProject: (id: number) => http<Project>(`/api/projects/${id}`),
  createProject: (data: ProjectCreate) =>
    http<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  // Characters / Lore / Chapters / GenerationLogs 同模式
};

export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(`HTTP ${status}`);
  }
}
```

### 3.2 lib/sse.ts — SSE 消费

```typescript
export type GenerationEvent =
  | { type: "meta"; generation_log_id: number; model: string; model_task: string;
      chapter_id: number; started_at: string }
  | { type: "context"; context_bundle: ContextBundle }
  | { type: "token"; text: string }
  | { type: "done"; generation_log_id: number; input_tokens: number;
      output_tokens: number; stop_reason: string }
  | { type: "error"; message: string; code: string };

export async function* streamGeneration(
  chapterId: number,
  body: GenerateRequest,
  signal?: AbortSignal
): AsyncGenerator<GenerationEvent> {
  const res = await fetch(`${BASE}/api/chapters/${chapterId}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 按 SSE 块解析（双换行分割事件）
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = parseSseChunk(chunk);
      if (event) yield event;
    }
  }
}

function parseSseChunk(chunk: string): GenerationEvent | null {
  let eventType = "";
  let dataStr = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event: ")) eventType = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataStr += line.slice(6);
  }
  if (!eventType || !dataStr) return null;
  return { type: eventType, ...JSON.parse(dataStr) } as GenerationEvent;
}
```

### 3.3 Zustand store（UI 状态，跨会话持久化）

```typescript
// lib/store.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  // 当前选中的实体（与 URL 同步；不持久化——URL 才是 source of truth）
  activeChapterId: number | null;
  activeProjectId: number | null;

  // Activity bar 当前激活的视图（不持久化）
  activeView: "chapters" | "characters" | "lore" | "history" | "search";

  // 拖拽调整的栏宽 / 面板高度（持久化）
  sidePanelWidth: number;          // 默认 220
  contextPanelWidth: number;       // 默认 240
  bottomPanelHeight: number;       // 默认 200
  bottomPanelOpen: boolean;        // 默认 false

  // 生成状态（不持久化）
  generationStatus: "idle" | "preparing" | "streaming" | "done" | "error";

  // 生成参数（不持久化——参数来自后端 chapters.last_involved_* 字段）
  generateParams: {
    involvedCharacterIds: number[];
    locationId: number | null;
  };

  // actions ...
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      activeChapterId: null,
      activeProjectId: null,
      activeView: "chapters",
      sidePanelWidth: 220,
      contextPanelWidth: 240,
      bottomPanelHeight: 200,
      bottomPanelOpen: false,
      generationStatus: "idle",
      generateParams: { involvedCharacterIds: [], locationId: null },
      // actions...
    }),
    {
      name: "m2b-ui",
      // 只持久化拖拽相关的布局字段
      partialize: (s) => ({
        sidePanelWidth: s.sidePanelWidth,
        contextPanelWidth: s.contextPanelWidth,
        bottomPanelHeight: s.bottomPanelHeight,
        bottomPanelOpen: s.bottomPanelOpen,
      }),
    }
  )
);
```

**关键**：用 `partialize` 只持久化布局字段（栏宽/面板高度/BottomPanel 开关）。URL 相关字段、生成状态、生成参数都不持久化——前者以 URL 为 source of truth，后者每次进入章节重新从后端拉默认集。

### 3.4 TanStack Query hooks

```typescript
// lib/queries.ts
export function useChapters(projectId: number) {
  return useQuery({
    queryKey: ["chapters", projectId],
    queryFn: () => api.listChapters(projectId),
  });
}

export function useChapter(chapterId: number) {
  return useQuery({
    queryKey: ["chapter", chapterId],
    queryFn: () => api.getChapter(chapterId),
  });
}

export function useUpdateChapter(chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterUpdate) => api.updateChapter(chapterId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapter", chapterId] }),
  });
}

export function useGenerationLogs(chapterId: number) {
  return useQuery({
    queryKey: ["generation-logs", chapterId],
    queryFn: () => api.listGenerationLogs(chapterId),
  });
}
```

### 3.5 useGenerate hook — 串起 SSE + store + Query

```typescript
// components/generation/useGenerate.ts
function useGenerate(chapterId: number) {
  const qc = useQueryClient();
  const { setGenerationStatus } = useUIStore();
  const [events, setEvents] = useState<GenerationEvent[]>([]);
  const [generatedText, setGeneratedText] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (req: GenerateRequest) => {
    setGenerationStatus("preparing");
    setEvents([]);
    setGeneratedText("");

    const ac = new AbortController();
    abortRef.current = ac;

    try {
      for await (const ev of streamGeneration(chapterId, req, ac.signal)) {
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "token") {
          setGeneratedText((prev) => prev + ev.text);
          setGenerationStatus("streaming");
        } else if (ev.type === "done") {
          setGenerationStatus("done");
          qc.invalidateQueries({ queryKey: ["generation-logs", chapterId] });
        } else if (ev.type === "error") {
          setGenerationStatus("error");
        }
      }
    } catch (err) {
      if (err instanceof ApiError) throw err;
      // abort 不算错
    }
  }, [chapterId, qc, setGenerationStatus]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setGenerationStatus("idle");
  }, [setGenerationStatus]);

  return { events, generatedText, start, cancel };
}
```

### 3.6 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| API 错误处理 | 抛 `ApiError`（带 status + body） | 调用方按 status 决定 UI（422 显示字段错误，404 跳转） |
| SSE 消费 | 异步生成器 `for await ... of` | 自然控制流；可被 AbortController 取消 |
| 422 错误体 | `ApiError.body.detail` 既可能是 string、对象、数组 | FastAPI 默认 vs `invalid_context` 结构不同；前端按 status 区分 |
| 章节内容保存 | `onUpdate` 防抖 500ms + `onBlur` 立即 | 平衡 SQLite WAL 压力与可靠性 |
| 生成结束后的"接受" | 用户主动点按钮 → `editor.chain().insertContent()` | 用户保留对内容的最终决定权 |
| Cancel | `abortController.abort()` → 后端 `GeneratorExit` → log 标 `client_disconnected` | 与 M2a 已实现的断开保护对接 |

---

## 3bis. 后端改动（M2b 范围内的小修订）

M2b 前端依赖两处后端小改动，否则无法满足"打开章节即见上下文"和"历史页一次拉取"的体验。

### 3bis.1 `chapters` 表加默认集字段

```sql
-- M2b 新增列
chapters(
  -- M1 已有字段...
  last_involved_character_ids JSON,    -- 上次生成时选的人物 ID 列表
  last_location_id INTEGER             -- 上次生成时选的地点 ID
)
```

**ORM 改动**（`app/memory/schema.py`）：

```python
class Chapter(Base):
    # ...M1 字段...
    last_involved_character_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

**Pydantic schema 改动**（`app/models/chapter.py`）：`ChapterRead` / `ChapterDetail` 暴露这两个字段；`ChapterUpdate` 允许 PATCH（可选）。

**Writer Agent 写回**（`app/agents/writer.py` `_finalize_done`）：done 事件后 UPDATE 这两个字段。

```python
def _finalize_done(db, log_id, full_text, event, *, chapter_id, involved_ids, location_id):
    log = db.get(GenerationLog, log_id)
    # ...M2a 已有的 log 字段更新...

    # M2b 新增：写回 chapter 的默认集
    chapter = db.get(Chapter, chapter_id)
    if chapter is not None:
        chapter.last_involved_character_ids = list(involved_ids)
        chapter.last_location_id = location_id

    db.commit()
```

**迁移**：drop & recreate（沿用 M2a 策略，本地无生产数据）。Alembic 留到 M3。

### 3bis.2 `GET /api/generation-logs` 加 `project_id` 参数

```python
# app/api/generation_logs.py
@router.get("", response_model=list[GenerationLogRead])
def list_logs(
    chapter_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    # 二选一必填
    if chapter_id is None and project_id is None:
        raise HTTPException(422, "must provide chapter_id or project_id")
    stmt = select(GenerationLog)
    if chapter_id is not None:
        stmt = stmt.where(GenerationLog.chapter_id == chapter_id)
    else:
        stmt = stmt.where(GenerationLog.project_id == project_id)
    stmt = stmt.order_by(GenerationLog.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))
```

**破坏性变更**：原 `chapter_id` 是必填，现改为可选（与 `project_id` 二选一）。M2a 已有测试要相应调整。

### 3bis.3 后端改动验收

| # | 验收项 |
|---|---|
| 1 | `chapters.last_involved_character_ids` / `last_location_id` 字段存在 |
| 2 | 生成 done 后这两字段更新为本次参数 |
| 3 | `GET /api/generation-logs?project_id=1` 返回项目所有日志 |
| 4 | `GET /api/generation-logs`（无参）返回 422 |
| 5 | M2a 所有现有测试仍通过（除 chapter_id 必填那条改为可选） |

---

## 4. 路由结构（Next.js App Router）

### 4.1 路由树

```
app/
├── layout.tsx                    # 根：providers、theme、全局字体
├── page.tsx                      # 首页 = 项目列表
│
├── projects/
│   └── [projectId]/
│       ├── layout.tsx            # WorkspaceShell（三栏 + ActivityBar + BottomPanel）
│       │
│       ├── page.tsx              # 项目首页 = 重定向到首章
│       │
│       ├── chapters/
│       │   ├── page.tsx          # 章节列表（📚 激活时显示在 SidePanel）
│       │   └── [chapterId]/
│       │       └── page.tsx      # ★ 写作主界面
│       │
│       ├── characters/
│       │   └── page.tsx          # 人物库
│       │
│       ├── lore/
│       │   └── page.tsx          # 设定库（sub-tab: 世界观/地点/势力）
│       │
│       ├── history/
│       │   └── page.tsx          # 生成历史
│       │
│       └── search/
│           └── page.tsx          # 全局搜索
│
└── settings/                     # 留作未来用（M2b 不实现）
    └── page.tsx
```

### 4.2 URL ↔ UI 映射

| URL | Activity Bar | SidePanel 内容 | Editor |
|---|---|---|---|
| `/` | — | — | 项目列表卡片 |
| `/projects/1/chapters/2` | 📚 高亮 | 章节列表（选中 2） | 第二章编辑器 + 右侧常驻层 |
| `/projects/1/chapters` | 📚 高亮 | 章节列表 | "请选择章节"提示 |
| `/projects/1/characters` | 👥 高亮 | 人物列表 | 人物表单/详情 |
| `/projects/1/lore` | 🌍 高亮 | 子 tab（世界观/地点/势力） | 对应表单 |
| `/projects/1/history` | 📜 高亮 | 历史列表 | 历史详情（含 prompt） |
| `/projects/1/search` | 🔍 高亮 | 搜索输入 | 搜索结果 |

### 4.3 WorkspaceShell 的角色

`/projects/[projectId]/layout.tsx` 渲染 `WorkspaceShell`，它负责：

- 渲染 ActivityBar（5 个图标，根据当前 URL 高亮对应的）
- 渲染 SidePanel 容器（内部内容由子路由决定）
- 渲染 Editor 容器（内部内容由子路由决定）
- 渲染 ContextPanel（**仅 `/chapters/[chapterId]` 路由显示**，其他路由隐藏）
- 渲染 BottomPanel 容器（始终存在，由 store 控制开/关和高度）

```typescript
// app/projects/[projectId]/layout.tsx
export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <WorkspaceShell projectId={Number(projectId)}>{children}</WorkspaceShell>;
}
```

### 4.4 全 Client Component 策略

所有页面文件直接 `"use client"`，组件用 TanStack Query 取数据。**无 Server Component 预取**——本地单用户场景，loading 一闪（< 100ms）可接受，省 HydrationBoundary 复杂度。

```typescript
// app/projects/[projectId]/chapters/[chapterId]/page.tsx
"use client";

import { useParams } from "next/navigation";
import { useChapter, useCharacters, useLore, useProject, useWorldOverview } from "@/lib/queries";
import { ChapterWorkspace } from "@/components/editor/ChapterWorkspace";

export default function ChapterPage() {
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>();
  const pid = Number(projectId);
  const cid = Number(chapterId);

  const { data: chapter } = useChapter(cid);
  const { data: project } = useProject(pid);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);
  const { data: worldOverview } = useWorldOverview(pid);

  if (!chapter || !project) return <Loading />;

  return <ChapterWorkspace chapter={chapter} project={project} /* ... */ />;
}
```

**Loading 处理**：每个 query 用 TanStack Query 的 `isLoading` / `isPending` 显示骨架屏，避免闪烁。

### 4.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 渲染模式 | 全 Client Component | 本地单用户无 SEO/CDN 需求；代码简单 30% |
| 项目切换 = 路由切换 | URL 含 `[projectId]` | 项目级数据缓存按 URL 自动隔离；分享/书签友好 |
| 章节切换 = 路由切换 | URL 含 `[chapterId]` | 同上；侧栏列表 + 编辑器解耦 |
| ContextPanel 仅章节路由显示 | 检查路由匹配 | 人物/lore/历史页不需要常驻层 |
| BottomPanel 全局可见 | store 控制开关 | 组件常驻避免卸载丢状态；切章节回来仍看到上次状态 |
| 搜索 = 项目内子路由 | 不是全屏 modal | 搜索结果需要可书签、可分享；按项目隔离 |
| 项目列表（首页）= 卡片网格 | 而非列表 | 小说项目用封面/标题/简介卡片更直观 |

---

## 5. 编辑器集成（TipTap + Markdown）

### 5.1 核心问题

M2a 后端 `Chapter.content` 存 Markdown 字符串。TipTap 内部用 ProseMirror JSON。需要双向转换。

### 5.2 选用的 TipTap v3 扩展

```typescript
// components/editor/extensions.ts
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "@tiptap/extension-markdown";   // v3 官方扩展
import Placeholder from "@tiptap/extension-placeholder";
import CharacterCount from "@tiptap/extension-character-count";

export const extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
  }),
  Markdown.configure({
    html: false,                  // 不允许 HTML（防 XSS、保持纯 Markdown）
    breaks: true,                 // 单换行也转为 <br>
    linkify: false,
    transformPastedText: true,    // 粘贴纯文本时按 Markdown 解析
    transformCopiedText: true,    // 复制时输出 Markdown 而非 HTML
  }),
  Placeholder.configure({
    placeholder: "开始写作... 或在底部面板点 ⚡ 生成",
  }),
  CharacterCount.configure({
    limit: null,                  // 不限字数，只统计
  }),
];
```

**关键决策**：

- TipTap **v3**——React 19 原生支持，Markdown 扩展官方化（不再依赖社区 `tiptap-markdown`）
- `getMarkdown()` API：v3 通过 `editor.storage.markdown.getMarkdown()` 取序列化结果（实现时核对官方文档确认）
- 不用 Table、TaskList、Image、Mention 等扩展——小说写作不需要
- 不用协作编辑（Yjs）——M2b 单用户
- 不用代码块高亮——小说极少用代码

### 5.3 双向转换

```typescript
// components/editor/ChapterEditor.tsx
"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import { extensions } from "./extensions";

export function ChapterEditor({
  chapter,
  onContentChange,
}: {
  chapter: Chapter;
  onContentChange: (markdown: string) => void;
}) {
  const editor = useEditor({
    extensions,
    content: chapter.content || "",  // 直接传 Markdown 字符串
    onUpdate: ({ editor }) => {
      const md = editor.storage.markdown.getMarkdown();
      onContentChange(md);
    },
    editorProps: {
      attributes: {
        class: "prose prose-invert max-w-none focus:outline-none min-h-[60vh] p-8",
      },
    },
  });

  return (
    <div className="flex flex-col h-full">
      <EditorToolbar editor={editor} wordCount={editor?.storage.characterCount.characters()} />
      <EditorContent editor={editor} className="flex-1 overflow-y-auto" />
    </div>
  );
}
```

### 5.4 保存策略（防抖）

```typescript
const saveMutation = useUpdateChapter(chapter.id);

const handleContentChange = useMemo(
  () => debounce((md: string) => {
    saveMutation.mutate({ content: md });
  }, 500),
  [chapter.id, saveMutation]
);

// 编辑器 onBlur 立即保存（避免防抖漏掉最后一次）
const handleBlur = () => {
  saveMutation.mutate({ content: currentMd });
};
```

**为什么 500ms**：

- 太短（100ms）：每次按键触发 PATCH，后端 SQLite WAL 膨胀
- 太长（2s+）：用户切走时可能漏存
- 500ms 是 Notion / Google Docs 的常用值

### 5.5 "接受生成内容"插入流程

```typescript
function acceptGeneratedText(generatedMd: string) {
  const editor = editorRef.current;
  if (!editor) return;

  // 在光标位置插入。TipTap 的 insertContent 支持多段 Markdown
  editor.chain().focus().insertContent(generatedMd).run();

  // 关闭底部面板
  setBottomPanelOpen(false);

  // 立即保存（不等防抖）
  const md = editor.storage.markdown.getMarkdown();
  saveMutation.mutate({ content: md });
}
```

不替换光标选区——如果用户选中了文字再点"接受"，那是误操作；用 TipTap 默认行为（insertContent 替换选区）即可，但要在按钮上加确认提示：

```tsx
<Button
  onClick={() => {
    if (editor.isActive("selection")) {
      if (!confirm("将替换当前选中的文字，确认？")) return;
    }
    acceptGeneratedText(generatedText);
  }}
>
  ✓ 接受并插入
</Button>
```

### 5.6 AI 生成 vs 用户手写：是否视觉区分？

**M2b 不做区分**。理由：

- TipTap 没有"段落作者"原生支持，要自定义 mark 扩展（成本高）
- 用户最终关心的是定稿（接受后就是自己的文字）
- M3 的 Extractor Agent 会扫描整章抽取事实，不关心谁写的
- M4 的 Reviewer Agent 同样全章扫描

未来想区分：M4+ 可以加一个 `data-source="ai"` 的属性，编辑器自定义 mark 渲染底色。M2b 留 hook。

### 5.7 字数统计

TipTap 的 CharacterCount 扩展提供：

- `editor.storage.characterCount.characters()` — 字符数（含中文）
- `editor.storage.characterCount.words()` — 词数（中文按字符算，意义不大）

UI 显示：编辑器顶部 EditorToolbar 显示**字符数**（小说常用度量），不是词数。

### 5.8 关键决策汇总

| 决策 | 选择 | 理由 |
|---|---|---|
| TipTap 版本 | **v3** | React 19 原生支持；官方 Markdown 扩展 |
| Markdown vs HTML vs JSON | Markdown（与后端 DB 一致） | 单一来源；减少转换层 |
| Markdown 扩展 | `@tiptap/extension-markdown`（v3 官方） | 不再依赖社区 `tiptap-markdown` |
| 字数限制 | 无 | 写作工具不应限制；M3 加超长警告 |
| 保存触发 | `onUpdate` 防抖 500ms + `onBlur` 立即 | 平衡性能与可靠 |
| AI 内容插入 | `insertContent` 在光标位置 | 不替换、不 append——用户掌握位置 |
| AI 内容视觉标记 | 不做 | YAGNI；M4+ 再加 |
| 编辑器宽度 | `max-w-3xl`（约 768px）居中 | 长文阅读/写作舒适区 |
| 编辑器字体 | 衬线（中文用 Source Han Serif / Noto Serif SC） | 小说写作传统 |

---

## 6. 三栏布局组件

### 6.1 整体结构

```
┌──┬─────────┬──────────────────────────┬─────────┐
│  │         │                          │         │
│  │         │                          │         │
│A │  Side   │       Editor (TipTap)    │ Context │
│c │ Panel   │                          │ Panel   │
│t │         │                          │ (常驻层) │
│B │         │                          │         │
│a │         │                          │         │
│r │         │                          │         │
│  ├─────────┴──────────────────────────┴─────────┤
│  │           Bottom Panel (生成)                │
└──┴──────────────────────────────────────────────┘
```

- `ActivityBar` = 40px 固定
- `SidePanel` = 220px 固定（可拖拽调宽，存到 localStorage）
- `Editor` = flex-1（最小 500px）
- `ContextPanel` = 240px 固定（仅章节路由显示，可隐藏存 localStorage）
- `BottomPanel` = 200px 起步，可拖拽调高，可关闭（`store.bottomPanelOpen`）

### 6.2 ActivityBar 组件

5 个图标，根据当前 URL 自动高亮（用 `usePathname()`）。点击切换路由。

```typescript
// components/layout/ActivityBar.tsx
"use client";

const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters" },
  { icon: "👥", label: "人物", path: "characters" },
  { icon: "🌍", label: "设定", path: "lore" },
  { icon: "📜", label: "历史", path: "history" },
  { icon: "🔍", label: "搜索", path: "search" },
];

export function ActivityBar({ projectId }: { projectId: number }) {
  const pathname = usePathname();
  const router = useRouter();
  const base = `/projects/${projectId}`;
  return (
    <aside className="w-10 bg-[#333] flex flex-col items-center py-2 gap-1">
      {ITEMS.map((it) => {
        const isActive = pathname.startsWith(`${base}/${it.path}`);
        return (
          <button
            key={it.path}
            onClick={() => router.push(`${base}/${it.path}`)}
            className={cx(
              "w-8 h-8 flex flex-col items-center justify-center rounded text-xs",
              isActive ? "bg-[#094771] text-white" : "hover:bg-[#3a3a3a] text-[#888]"
            )}
            title={it.label}
          >
            <span className="text-base">{it.icon}</span>
          </button>
        );
      })}
    </aside>
  );
}
```

### 6.3 ContextPanel（常驻层预览）

仅章节路由显示。**显示"默认集 + 当前生成参数"的并集视图**——默认集来自后端 `chapters.last_involved_character_ids` / `last_location_id`（上次生成的参数）；用户在 BottomPanel 改了表单，ContextPanel 实时同步当前选择。

**初始化流程**：

1. 进入章节路由 → `useChapter(cid)` 拉章节
2. 把 `chapter.last_involved_character_ids` 和 `chapter.last_location_id` 写入 store 的 `generateParams`（仅首次进入时）
3. ContextPanel 从 `generateParams` 读，实时显示
4. BottomPanel 表单也是从 `generateParams` 读，双向同步

```typescript
// components/layout/ContextPanel.tsx
export function ContextPanel({
  projectId,
  chapterId,
}: {
  projectId: number;
  chapterId: number;
}) {
  // 双向同步的 store slice（首次进入章节时由 useChapter 初始化）
  const { involvedCharacterIds, locationId } = useGenerateParams();
  const { data: characters } = useCharacters(projectId);
  const { data: allLore } = useLore(projectId);

  const involvedChars = characters?.filter((c) => involvedCharacterIds.includes(c.id)) ?? [];
  const location = allLore?.find((l) => l.id === locationId);
  const factions = allLore?.filter((l) =>
    involvedChars.some((c) => c.affiliations?.includes(l.id))
  );

  return (
    <aside className="w-60 bg-[#252526] border-l border-[#3c3c3c] p-3 overflow-y-auto">
      <h3 className="text-xs uppercase text-[#888] mb-2">📋 当前场景</h3>

      <Section title="人物">
        {involvedChars.map((c) => <CharacterChip key={c.id} character={c} />)}
        {involvedChars.length === 0 && <Empty>未选</Empty>}
      </Section>

      <Section title="地点">
        {location ? <LocationChip lore={location} /> : <Empty>未选</Empty>}
      </Section>

      <Section title="势力">
        {factions.length > 0
          ? factions.map((f) => <FactionChip key={f.id} lore={f} />)
          : <Empty>无</Empty>}
      </Section>

      <div className="mt-6 p-2 bg-[#1e1e1e] rounded text-xs text-[#888]">
        💡 这是 AI 生成时将看到的常驻层。
        点人物/地点可在底部生成面板中调整。
      </div>
    </aside>
  );
}
```

**关键设计**：

- ContextPanel 与 GenerateForm 共享同一个 `useGenerateParams` slice——单一数据源
- 进入章节时，store 的 `generateParams` 被 chapter 的 `last_involved_*` 字段初始化（打开章节即可见上下文）
- 用户在 GenerateForm 改人物/地点 → store 更新 → ContextPanel 立刻同步
- 生成 done 后，后端写回 `chapters.last_involved_*`，下次打开章节默认集是最新的

### 6.4 BottomPanel（生成面板）

```typescript
// components/layout/BottomPanel.tsx
export function BottomPanel({ chapterId }: { chapterId: number }) {
  const { bottomPanelOpen, bottomPanelHeight, toggle } = useUIStore();
  const [splitRatio, setSplitRatio] = useState(0.4);  // 左表单 / 右输出

  if (!bottomPanelOpen) {
    return (
      <button onClick={toggle} className="h-6 bg-[#1e1e1e] text-xs text-[#888] flex items-center justify-center">
        ⚡ 生成（展开）
      </button>
    );
  }

  return (
    <div style={{ height: bottomPanelHeight }} className="bg-[#252526] border-t border-[#3c3c3c] flex flex-col">
      <div className="flex items-center justify-between px-3 py-1 bg-[#1e1e1e] border-b border-[#3c3c3c]">
        <span className="text-xs text-[#888]">⚡ 生成</span>
        <button onClick={toggle} className="text-xs text-[#888] hover:text-white">▾ 收起</button>
      </div>

      {/* 拖拽分隔条（顶部，调高度） */}
      <div onMouseDown={startDragVertical} className="h-1 bg-transparent hover:bg-[#2563eb] cursor-ns-resize" />

      <div className="flex-1 flex overflow-hidden">
        {/* 左：表单 */}
        <div style={{ width: `${splitRatio * 100}%` }} className="overflow-y-auto p-3">
          <GenerateForm chapterId={chapterId} />
        </div>
        {/* 中：拖拽分隔条 */}
        <DragBar direction="horizontal" onDrag={setSplitRatio} />
        {/* 右：流式输出 */}
        <div className="flex-1 overflow-y-auto p-3">
          <StreamView chapterId={chapterId} />
        </div>
      </div>
    </div>
  );
}
```

### 6.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 三栏宽度调整 | SidePanel 和 ContextPanel 可拖拽调宽，宽度存 localStorage（`partialize`） | 用户偏好稳定 |
| Activity Bar 高亮 | 根据 `usePathname()` 自动计算 | 不依赖额外状态 |
| ContextPanel 与 GenerateForm 数据源 | 都从 `useGenerateParams` slice 读 | 单一来源；改一处两端同步 |
| ContextPanel 初始数据 | 进入章节时从 `chapter.last_involved_*` 初始化 store | 打开章节即可见上下文，无需先开 BottomPanel |
| BottomPanel 开关 | store 控制；初始默认关；状态跨会话持久化 | 不挤占编辑器；用户主动展开 |
| BottomPanel 状态保持 | 关闭后内容不丢（store 持久化） | 切换章节回来仍看到上次状态 |
| 拖拽调高/宽 | 自定义 mousemove handler（不引入 `react-resizable-panels`） | 简单场景不值得引库 |

---

## 7. 生成流程（底部面板交互）

### 7.1 完整生命周期

1. 用户打开章节 → BottomPanel 默认收起
2. 点 "⚡ 生成（展开）" → BottomPanel 展开，显示空白 `GenerateForm`
3. 用户在 `GenerateForm` 填表：
   - `beat_text`（必填，textarea）
   - 涉及人物（多选 chips，从 `useCharacters` 拉）
   - 地点（单选 dropdown，从 `useLore` type=location 拉）
   - `instruction`（可选 textarea）
   - `model_task`（默认 `writer_long`，下拉切换）
4. 用户调整期间 → ContextPanel 实时同步预览（人物/地点/势力）
5. 用户点 "✨ 生成" →
   - 前端校验：`beat_text` 非空，至少 1 个人物
   - 启动 `useGenerate.start(req)`
   - 后端先返回 200 + 流开始；首个事件是 `meta`
   - 出错（422 `invalid_context` / 404 / 502）→ `ApiError`，前端 Toast 显示
6. SSE 流过程：
   - `meta` 事件 → `StreamView` 显示 "[准备就绪] log_id=42, model=claude-sonnet-4-6"
   - `context` 事件 → `StreamView` 显示折叠的 `ContextBundle` 摘要（可展开看详情）
   - `token` 事件 → `StreamView` 实时打字机渲染
   - `done` 事件 → `StreamView` 底部显示 token 用量；启用 "✓ 接受" 按钮
   - `error` 事件 → `StreamView` 红色显示错误，启用 "重试" 按钮
7. 用户点 "✓ 接受并插入" →
   - 触发 `acceptGeneratedText(generatedMd)`
   - 调 TipTap 的 `editor.chain().insertContent(generatedMd)`
   - 立即 `saveMutation.mutate`（不等防抖）
   - 关闭 BottomPanel
   - invalidate `generation-logs` query（历史面板会自动更新）
8. 用户点 "重试" → 清空 `generatedText`，回到步骤 5.b 重新流
9. 用户点 "✕ 取消" → `abortController.abort()` → 后端标 `client_disconnected`

### 7.2 GenerateForm 组件

```typescript
// components/generation/GenerateForm.tsx
"use client";

export function GenerateForm({ chapterId }: { chapterId: number }) {
  const { projectId } = useProjectContext();
  const { data: characters } = useCharacters(projectId);
  const { data: lore } = useLore(projectId);
  const locations = lore?.filter((l) => l.type === "location") ?? [];

  // 表单状态
  const [beatText, setBeatText] = useState("");
  const [instruction, setInstruction] = useState("");
  const [involvedCharIds, setInvolvedCharIds] = useState<number[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [modelTask, setModelTask] = useState<"writer_long" | "writer_short">("writer_long");

  // 同步到 store（供 ContextPanel 读）
  const setParams = useGenerateParams((s) => s.setParams);
  useEffect(() => {
    setParams({ involvedCharacterIds: involvedCharIds, locationId });
  }, [involvedCharIds, locationId, setParams]);

  const { start, cancel, generatedText, status } = useGenerate(chapterId);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    try {
      await start({
        beat_text: beatText,
        instruction,
        involved_character_ids: involvedCharIds,
        location_id: locationId,
        model_task: modelTask,
        max_tokens: 4096,
      });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 422 && e.body.detail?.error === "invalid_context") {
          const d = e.body.detail;
          setError(
            `无效 ID：人物 ${d.invalid_character_ids.join(", ") || "无"}；` +
            `地点 ${d.invalid_location_id ?? "无"}`
          );
        } else {
          setError(e.body.detail?.[0]?.msg ?? `HTTP ${e.status}`);
        }
      } else {
        setError(String(e));
      }
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <Field label="Beat 文本 *" required>
        <textarea
          value={beatText}
          onChange={(e) => setBeatText(e.target.value)}
          placeholder="例：李雷推开残月酒馆的门，看见多年未见的韩梅在角落等候"
          rows={3}
          maxLength={2000}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2"
        />
        <div className="text-xs text-[#666] mt-1">{beatText.length}/2000</div>
      </Field>

      <Field label="涉及人物 *（1-20）">
        <div className="flex flex-wrap gap-1">
          {characters?.map((c) => (
            <Chip
              key={c.id}
              selected={involvedCharIds.includes(c.id)}
              onClick={() =>
                setInvolvedCharIds((prev) =>
                  prev.includes(c.id)
                    ? prev.filter((x) => x !== c.id)
                    : [...prev, c.id].slice(0, 20)
                )
              }
            >
              {c.name}（{c.role}）
            </Chip>
          ))}
        </div>
      </Field>

      <Field label="地点">
        <select
          value={locationId ?? ""}
          onChange={(e) => setLocationId(e.target.value ? Number(e.target.value) : null)}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-full"
        >
          <option value="">（无）</option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </Field>

      <Field label="附加指令">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="例：氛围压抑，对话简短"
          rows={2}
          maxLength={500}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2"
        />
      </Field>

      <Field label="模型任务">
        <select
          value={modelTask}
          onChange={(e) => setModelTask(e.target.value as "writer_long" | "writer_short")}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-40"
        >
          <option value="writer_long">writer_long（高质量）</option>
          <option value="writer_short">writer_short（快速）</option>
        </select>
      </Field>

      {error && (
        <div className="text-red-400 text-xs p-2 bg-red-950/30 border border-red-900 rounded">
          {error}
        </div>
      )}

      <div className="flex gap-2 pt-2">
        {status === "streaming" || status === "preparing" ? (
          <button onClick={cancel} className="bg-[#444] hover:bg-[#555] px-3 py-1 rounded text-xs">
            ✕ 取消
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!beatText.trim() || involvedCharIds.length === 0}
            className="bg-[#2563eb] hover:bg-[#3070e0] disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1 rounded text-xs"
          >
            ✨ 生成
          </button>
        )}
      </div>
    </div>
  );
}
```

### 7.3 StreamView 组件

```typescript
// components/generation/StreamView.tsx
export function StreamView({ chapterId }: { chapterId: number }) {
  const { events, generatedText, status } = useGenerate(chapterId);
  const { accept } = useAcceptGeneration(chapterId);

  const meta = events.find((e) => e.type === "meta");
  const contextEvent = events.find((e) => e.type === "context");
  const doneEvent = events.find((e) => e.type === "done");
  const errorEvent = events.find((e) => e.type === "error");

  return (
    <div className="space-y-3 text-xs">
      {meta && (
        <div className="text-[#888]">
          <span className="text-[#aaa]">[meta]</span> log_id={meta.generation_log_id} · model={meta.model}
        </div>
      )}

      {contextEvent && (
        <details className="bg-[#1e1e1e] rounded p-2">
          <summary className="cursor-pointer text-[#888]">
            📋 常驻层预览（{contextEvent.context_bundle.characters.length} 人物 ·
            {" "}{contextEvent.context_bundle.location_lore.length} 地点）
          </summary>
          <ContextBundlePreview bundle={contextEvent.context_bundle} />
        </details>
      )}

      {/* 实时打字机区域 */}
      <div className="font-serif text-sm leading-relaxed whitespace-pre-wrap min-h-[120px]">
        {generatedText}
        {(status === "streaming" || status === "preparing") && (
          <span className="inline-block w-2 h-4 bg-[#888] animate-pulse ml-0.5" />
        )}
      </div>

      {doneEvent && (
        <div className="flex items-center justify-between pt-2 border-t border-[#3c3c3c]">
          <span className="text-[#888]">
            ✓ 完成 · 输入 {doneEvent.input_tokens} / 输出 {doneEvent.output_tokens} tokens
          </span>
          <button
            onClick={() => accept(generatedText)}
            className="bg-[#16825d] hover:bg-[#1a9c6c] px-3 py-1 rounded"
          >
            ✓ 接受并插入
          </button>
        </div>
      )}

      {errorEvent && (
        <div className="p-2 bg-red-950/30 border border-red-900 rounded text-red-400">
          ✗ {errorEvent.message} <span className="text-[#888]">({errorEvent.code})</span>
          <button onClick={/* retry */} className="ml-2 underline">重试</button>
        </div>
      )}
    </div>
  );
}
```

### 7.4 关键交互决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 表单字段必填校验 | `beat_text` 非空 + 至少 1 人物 | 后端也会校验（422），前端先拦截避免无意义请求 |
| 人物选择上限 | 20（与后端 `GenerateRequest` 一致） | 选到 20 个后 chip 不再追加 |
| 取消正在生成 | `AbortController.abort()` | 后端会标 `client_disconnected`（M2a 已实现） |
| 错误展示 | Toast + 表单内联红框 | 422 `invalid_context` 高亮具体字段 |
| ContextBundle 显示 | `<details>` 默认折叠 | 不抢屏；想看展开 |
| 完成后是否自动接受 | 不自动 | 用户必须主动点"接受"——保留对内容的最终决定权 |
| 接受后是否清空表单 | 不清空 | 用户可能想再生成一个变体（改 beat 重试） |
| 多次生成的累积 | 每次新流覆盖前一次的 `generatedText` | M2b 不做多版本对比；M4 再做 |
| "重试"按钮 | 用**相同参数**重新发 `/generate`（不清空表单，仅清空 `generatedText`） | 便于在 beat 不变时换一次随机性 |

---

## 8. 实体管理 UI（章节/人物/设定）

### 8.1 项目列表（首页 `/`）

简单卡片网格，无三栏布局。

```
┌──────────────────────────────────────────────────┐
│  NovelAI · 本地小说写作助手                       │
├──────────────────────────────────────────────────┤
│   ┌─────────────┐  ┌─────────────┐  ┌────────┐  │
│   │ 夜行记      │  │ 未命名项目  │  │   +    │  │
│   │ 复仇 · 奇幻 │  │              │  │ 新建   │  │
│   │ 5 章 · 2 天 │  │              │  │ 项目   │  │
│   └─────────────┘  └─────────────┘  └────────┘  │
└──────────────────────────────────────────────────┘
```

点项目卡 → `/projects/[id]/chapters`（自动重定向到首章 or "新建第一章"）。

### 8.2 章节列表（SidePanel 内）

```
┌─────────────────────┐
│ 章节           + 新建│
├─────────────────────┤
│ ▸ 序幕              │
│   423 字 · draft    │
│ ▸ 第二章            │ ← 选中
│   798 字 · draft    │
│ ▸ 第三章            │
│   0 字 · draft      │
└─────────────────────┘
```

每个 `ChapterItem` 显示标题、字数（实时从 `Chapter.content` 算）、状态点（`draft`/`writing`/`reviewed`/`final` 用不同色）。点击 → `/projects/[id]/chapters/[cid]`。

新建章节：点 + → 弹小表单（title + `order_index` 自动 = max+1） → `POST /api/chapters` → 自动跳转。

### 8.3 人物库（`/projects/[id]/characters`）

```
┌──────────────────────────────────────────────┐
│ ActivityBar(👥高亮) │ SidePanel: 人物列表    │ Editor: 选中人物的详情/编辑表单
│                     │ + 新建人物             │
│                     │ ▸ 李雷 (主角)          │ ┌─────────────────────┐
│                     │   INTJ                │ │ 李雷                │
│                     │ ▸ 韩梅 (旧友)         │ │ 角色：主角 ▾         │
│                     │   ENFP                │ │ 性格：              │
│                     │ ▸ 王五 (反派)         │ │ {mbti: INTJ, ...}   │
│                     │                       │ │ 说话风格：短句       │
│                     │                       │ │ 背景：南方孤儿       │
│                     │                       │ │ 动机：复仇           │
│                     │                       │ │ 当前状态：刚进城     │
│                     │                       │ │ 所属势力：守夜人 ✓   │
│                     │                       │ │ 活动地点：青石城 ✓   │
│                     │                       │ │ [保存] [删除]        │
│                     │                       │ └─────────────────────┘
└──────────────────────────────────────────────┘
```

**人物编辑表单要点**：

- 性格（`personality` JSON）：用"键值对列表" UI（每行 key + value，可加可删）——比裸 JSON 编辑器更友好
- 所属势力 / 活动地点：多选 chips（从 Lore 里 `type=faction` / `type=location` 筛）
- 保存：防抖 500ms，调 PATCH
- 删除：弹确认（"删除人物将影响相关章节的常驻层"），DELETE

### 8.4 设定库（`/projects/[id]/lore`）

子 tab 切换：世界观 / 地点 / 势力 / 物品 / 其他

```
┌──────────────────────────────────────────────────────────┐
│ 设定  [世界观] [地点] [势力] [物品] [其他]      + 新建    │
├──────────────────────────────────────────────────────────┤
│ 左：当前 tab 列表           │ 右：详情表单                │
│                            │                              │
│ ▸ 青石王国 (location)       │ 青石城                       │
│   ▾ 青石城                  │ 类型：location ▾             │
│     ▾ 残月酒馆              │ 上级：青石王国 ▾             │
│ ▸ 北境峡道                  │ 描述：王国首都，城墙青黑色    │
│                            │ 属性：{population: 50000}    │
│ ▸ 守夜人 (faction)          │ 标签：[北方, 首都]           │
│ ▸ 黑鸦帮                    │ [保存] [删除]                │
└──────────────────────────────────────────────────────────┘
```

**关键交互**：

- 地点有层级：列表用树形展示（`parent_id` 链）。残月酒馆的父是青石城，青石城的父是青石王国
- 世界观 tab：只有一个表单（每项目唯一），不显示列表
- 新建 lore：当前 tab 决定 `type` 默认值
- `parent_id` 选择器：仅显示同 `type=location` 的同级选项（防止地点挂在势力下）

### 8.5 生成历史（`/projects/[id]/history`）

**数据源**：`GET /api/generation-logs?project_id=X`（M2a list 端点扩展，二选一必填 `chapter_id` 或 `project_id`）。1 个请求拿项目所有日志，前端按 `chapter_id` 分组。

```
┌──────────────────────────────────────────────────────────┐
│ ActivityBar(📜) │ 历史列表                  │ 详情         │
│                 │ 按章节分组                │              │
│                 │ ▾ 第二章 (5)             │ log_id: 42   │
│                 │   ▸ 2 分钟前 · 798 字    │ status: done │
│                 │   ▸ 1 小时前 · 423 字    │ input: 700   │
│                 │ ▸ 序幕 (1)               │ output: 637  │
│                 │   ▸ 昨天 · 412 字        │              │
│                 │                          │ [Beat]        │
│                 │                          │ 李雷推开残月... │
│                 │                          │ [system]      │
│                 │                          │ 你是一位资深...│
│                 │                          │ [user]        │
│                 │                          │ # 项目背景    │
│                 │                          │ 标题：夜行记  │
│                 │                          │ ...          │
│                 │                          │ [generated]   │
│                 │                          │ 青石城的夜... │
└──────────────────────────────────────────────────────────┘
```

详情面板有 4 个折叠区：Beat + Meta / System Prompt / User Prompt / Generated Text。

**用途**：调试 prompt 质量——看 AI 实际收到了什么、生成了什么、token 用量。

### 8.6 全局搜索（`/projects/[id]/search`）

M2b 简单实现：单输入框，按 Enter 搜索以下范围（前端 filter）：

| 范围 | 数据源 |
|---|---|
| 章节标题/正文 | `GET /api/chapters?project_id=X`，全文 substring 匹配 |
| 人物名/背景 | `GET /api/characters?project_id=X`，substring 匹配 `name`/`background`/`motivation` |
| Lore 名称/描述 | `GET /api/lore?project_id=X`，substring 匹配 `name`/`description` |

搜索结果分组显示，点击跳转到对应编辑界面。

**M2b 不做语义搜索/向量检索**——M3 才有 embedding。前端 filter 够用。

### 8.7 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 列表 + 详情布局 | SidePanel 列表，Editor 区显示详情 | 一致 VS Code 风格 |
| 实体编辑表单 | 内联（在 Editor 区），非 modal | 大表单（人物有 10+ 字段）modal 装不下 |
| 性格 JSON 编辑 | 键值对列表 UI（不是裸 JSON） | 用户友好；后端仍是 dict |
| 地点树形展示 | 递归渲染 parent_id 链 | 直观；点击展开/折叠 |
| 删除确认 | 全部弹 confirm dialog | 数据破坏性操作必须确认 |
| 保存策略 | 防抖 500ms PATCH，与章节编辑一致 | 统一交互节奏 |
| 搜索范围 | 仅项目内 + 仅 substring | M2b YAGNI；M3 接向量检索 |
| 章节字数实时 | 前端从 `Chapter.content.length` 算 | 不需要后端字段 |

---

## 9. CORS + 环境配置

### 9.1 后端改动（FastAPI 加 CORSMiddleware）

```python
# app/main.py 修改
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)

    # CORS — 仅允许前端 dev 端口
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3300", "http://127.0.0.1:3300"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Accel-Buffering"],  # SSE 必须
    )
    # ... 其他 router
```

**关键**：`expose_headers=["X-Accel-Buffering"]` 让前端能读到 SSE 流的禁缓冲头（虽然主要靠服务端发，但保险）。

`allow_origins` **不用 `["*"]`**——明示只允许前端 dev 端口。

### 9.2 后端端口配置

通过环境变量指定（不动 `app/config.py`）。具体实现阶段定，候选方案：

**候选 A**：`.env` 加 `UVICORN_PORT=8005`，在 `app/main.py` 的 `__main__` 块里读环境变量并传给 `uvicorn.run()`。

```python
# app/main.py 末尾
if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("UVICORN_HOST", "127.0.0.1"),
        port=int(os.environ.get("UVICORN_PORT", "8000")),
        reload=True,
    )
```

启动：`python -m app.main`（自动从 `.env` 读环境变量）。

**候选 B**：保持 `uvicorn app.main:app --reload --port 8005` 命令行参数，记到 README 和 Makefile。

实现阶段二选一，spec 不锁定。

### 9.3 前端环境变量

`web/.env.local`（Next.js 优先读）：

```
# 后端 API（client-side 也要能用，必须 NEXT_PUBLIC_ 前缀）
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8005
```

`web/package.json` 启动脚本：

```json
{
  "scripts": {
    "dev": "next dev -p 3300",
    "build": "next build",
    "start": "next start -p 3300",
    "lint": "next lint",
    "test": "vitest",
    "test:e2e": "playwright test"
  }
}
```

### 9.4 开发启动流程（README）

```bash
# 终端 1：后端
cd /Users/bugx/novelAI
source .venv/bin/activate
uvicorn app.main:app --reload --port 8005

# 终端 2：前端
cd /Users/bugx/novelAI/web
npm install
npm run dev
# → http://localhost:3300
```

### 9.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| CORS 来源白名单 | 硬编码 `localhost:3300` + `127.0.0.1:3300` | 安全；M2b 不需要生产域名 |
| 后端端口 | 8005 | 用户指定（避开 8000 占用） |
| 前端端口 | 3300 | 用户指定（避开 3000 占用） |
| 环境变量前缀 | `NEXT_PUBLIC_API_BASE` | Next.js 强制要求 client 可见 |
| 启动方式 | 两个终端进程 | M2b 不引入 docker-compose/进程管理器（YAGNI） |

---

## 10. 测试策略

### 10.1 测试金字塔

```
                ┌─────────────────┐
                │ Playwright E2E  │  3-5 个，覆盖关键用户流程
                └─────────────────┘
            ┌─────────────────────────┐
            │ 组件测试（Vitest + RTL）│  关键组件：GenerateForm、StreamView
            └─────────────────────────┘
        ┌───────────────────────────────┐
        │ 单元测试（lib/）              │  sse.ts 解析、api.ts 类型、store 逻辑
        └───────────────────────────────┘
```

### 10.2 单元测试（Vitest）

**`web/lib/__tests__/sse.test.ts`** — SSE 解析：

| 测试 | 验证 |
|---|---|
| `test_parse_single_token_event` | 单 token 块正确解析 |
| `test_parse_chunked_events` | 跨 chunk 边界的事件能正确拼接 |
| `test_parse_meta_event` | meta 事件解析出 `generation_log_id` |
| `test_parse_event_with_chinese` | 中文 token 不乱码 |
| `test_parse_partial_event_buffered` | 半个事件不丢，等下一块 |

**`web/lib/__tests__/store.test.ts`** — Zustand slice：

| 测试 | 验证 |
|---|---|
| `test_generate_params_sync` | 改 `involved_character_ids` 后 ContextPanel 读到一致 |
| `test_bottom_panel_persistence` | 关闭 BottomPanel 后状态保留 |
| `test_active_view_from_url` | URL 变化 → `activeView` 自动更新 |

### 10.3 组件测试（Vitest + React Testing Library）

**`GenerateForm.test.tsx`**：

| 测试 | 验证 |
|---|---|
| `test_disables_submit_when_beat_empty` | 空 `beat_text` 时按钮 disabled |
| `test_disables_submit_when_no_chars_selected` | 未选人物时按钮 disabled |
| `test_char_limit_20` | 选到 20 个 chip 后不可再加 |
| `test_shows_422_invalid_context_error` | mock fetch 返回 422，UI 显示具体非法 ID |
| `test_syncs_to_context_panel_store` | 选人物后 store 同步 |

**`StreamView.test.tsx`**：

| 测试 | 验证 |
|---|---|
| `test_renders_meta_first` | meta 事件先于 token 显示 |
| `test_typewriter_animation_on_token` | token 事件追加到 `generatedText` |
| `test_shows_accept_button_on_done` | done 事件后启用接受按钮 |
| `test_shows_error_on_error_event` | error 事件显示红框 |
| `test_collapsible_context_bundle` | context 事件默认折叠，点击展开 |

### 10.4 E2E 测试（Playwright）

启动真实后端（处理 CRUD）+ 真实前端，**用 Playwright 的 `page.route()` 拦截 `**/api/chapters/*/generate`**，返回伪造的 SSE 字节流（避免依赖真实 LLM API key 与网络）。CRUD 端点不打桩，走真实后端 SQLite，保证测试贴近真实交互。

| 测试 | 流程 |
|---|---|
| `e2e_create_project_and_chapter` | 首页 → 新建项目 → 新建章节 → 看到编辑器 |
| `e2e_generate_and_accept` | 进入章节 → 展开底部面板 → 填表 → 生成（mock） → 接受 → 内容插入编辑器 |
| `e2e_invalid_context_error` | 选不存在的人物 ID → 看到错误提示 |
| `e2e_character_crud` | 人物库 → 新建 → 编辑 → 保存 → 删除 |
| `e2e_generation_history` | 生成后 → 跳历史页 → 看到记录 → 点开看 prompt |

### 10.5 不测什么（YAGNI）

- 视觉回归测试（截图对比）——M2b 不需要像素级精确
- 性能测试（首屏速度、SSE 吞吐）——M2b 单用户，性能不是瓶颈
- 跨浏览器测试——本地工具，Chrome 一条够
- 真实 LLM 调用——所有测试 mock LLM

### 10.6 测试覆盖率目标

| 模块 | 目标 |
|---|---|
| `lib/sse.ts` | 100%（核心解析逻辑） |
| `lib/store.ts` | >90% |
| `lib/api.ts` | >80%（薄包装） |
| `components/generation/` | >85% |
| `components/layout/` | >70%（结构为主） |
| `components/entities/` | >70%（表单逻辑） |

---

## 11. M2b 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `npm run dev` 启动，浏览器打开 3300 看到首页 | 手工 |
| 2 | CORS 正确，前端能调通后端 `/api/*` | DevTools Network 看 200 |
| 3 | 项目 CRUD：新建/编辑/删除项目 | 手工 |
| 4 | 章节列表 + 编辑器（TipTap v3 加载/保存 Markdown） | 输入文字 → 刷新 → 内容还在 |
| 5 | 人物/lore/world overview CRUD | 手工 |
| 6 | 进入章节 → ContextPanel 立即显示默认集（上次生成参数） | 后端 `chapters.last_involved_*` 字段被读出 |
| 7 | 展开 BottomPanel → 表单预填默认集 → 改动后 ContextPanel 实时同步 | 单数据源 `useGenerateParams` |
| 8 | 填表 → 点生成 | 看到 meta → context → token* → done |
| 9 | 生成完成后 `chapters.last_involved_*` 字段被后端写回 | `sqlite3` 直查 |
| 10 | 生成完成 → 点"接受" → 内容插入编辑器并保存 | 编辑器光标位置出现生成文字 |
| 11 | 422 `invalid_context` 错误正确显示 | 故意选错 ID → 看到错误 |
| 12 | 客户端断开保护（点取消）→ 后端 log 标 `client_disconnected` | `sqlite3` 直查 |
| 13 | 历史页一次请求拿项目所有日志并按章节分组 | DevTools Network 看 1 个 `?project_id=X` 请求 |
| 14 | 历史详情（看完整 prompt） | 历史页点 log → 看 system/user prompt |
| 15 | UI 状态跨会话持久化（栏宽/面板高度/开关） | 刷新浏览器 → 拖拽过的栏宽仍在 |
| 16 | 全部前端测试通过 | `npm run test && npm run test:e2e` |
| 17 | 全部后端测试通过（含 chapters 新字段、logs 新参数） | `pytest -v` |

### 验收脚本

```bash
# 1. 启动后端
cd /Users/bugx/novelAI
source .venv/bin/activate
uvicorn app.main:app --reload --port 8005 &

# 2. 启动前端
cd web
npm install
npm run dev &
sleep 5

# 3. 浏览器手工验证
open http://localhost:3300

# 4. 跑全部测试
npm run test          # 单元 + 组件
npm run test:e2e      # E2E
pytest -v             # 后端回归
```

---

## 12. 待定 / 开放问题

实现计划阶段需决策：

1. **`max_tokens` 默认值是否暴露给用户**：当前固定 4096。是否在 GenerateForm 加滑块？
   - M2b 不加；M3 用户反馈不够再说。
2. **章节排序 UI**：当前 `order_index` 自动 = max+1。是否支持拖拽重排？
   - M2b 不支持；YAGNI。
3. **ContextPanel 在编辑器滚动时是否保持 sticky**：当前是固定右侧栏。是否需要浮动跟随光标段落？
   - M2b 固定栏；YAGNI。
4. **生成历史搜索/过滤**：当前按章节分组列表。是否加全文搜索 prompt 内容？
   - M2b 不加；历史量小（单机），人工滚动够用。
5. **TipTap v3 `getMarkdown()` 精确 API**：v3 已发布，但具体方法名（`editor.storage.markdown.getMarkdown()` 或其他）需在实现阶段核对官方文档。
6. **后端端口环境变量具体写法**：候选 A（`python -m app.main` 读 `.env`） vs 候选 B（命令行 `--port`）— 实现阶段定。

---

## 13. 未来扩展（v2+，不在 M2b 范围）

- M3：Extractor Agent UI（"完成本章"按钮、pending_updates 面板、accept/reject 流）
- M3：向量检索 + 语义搜索（替换 substring filter）
- M4：Reviewer Agent 面板（issue 列表、跳转到对应段落）
- M4：Discuss Agent 多分支对比表
- M4+：AI 生成段落视觉标记（自定义 TipTap mark）
- M4+：章节级版本控制（diff 视图）
- 移动端 / 响应式布局
- 主题切换（暗/亮）
- 多语言（i18n）
- 协作编辑（Yjs + WebSocket）
- 项目导出（epub/docx）
