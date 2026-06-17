# M2b — Frontend Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js frontend (VS Code-style three-column layout, TipTap v3 editor, SSE generation flow, entity management UI) plus two small backend changes that enable "default set" persistence and project-wide history queries.

**Architecture:** Frontend lives in `web/` (Next.js 15 App Router, all Client Components, TanStack Query + Zustand persist). Backend gets two additions: `chapters.last_involved_*` columns written back on generation done, and `GET /api/generation-logs` gains an optional `project_id` query parameter. CORS is added to FastAPI to allow `http://localhost:3300`.

**Tech Stack:** Next.js 15, React 19, TypeScript 5, Tailwind v4, TipTap v3 (`@tiptap/extension-markdown`), TanStack Query v5, Zustand v5 (`persist` middleware), Vitest, Playwright. Python/FastAPI on the backend side (existing).

**Reference spec:** `docs/superpowers/specs/2026-06-17-m2b-editor-frontend-design.md`

**Working directory:** `/Users/bugx/novelAI`

---

## Scope Check

M2b is one cohesive subsystem (frontend editor + enabling backend tweaks). No further decomposition needed. Spec §3bis calls out the backend changes; they're small enough to bundle into Task 1.

---

## File Structure

### Backend (modify existing)

```
app/
├── main.py                         # modify: add CORSMiddleware
├── memory/schema.py                # modify: Chapter + 2 columns
├── models/chapter.py               # modify: ChapterRead/Update expose new fields
├── agents/writer.py                # modify: _finalize_done writes back chapter defaults
└── api/generation_logs.py          # modify: list_logs accepts chapter_id OR project_id
```

### Frontend (new `web/` subdirectory)

```
web/
├── package.json
├── tsconfig.json
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.js
├── .env.local
├── .env.example
├── vitest.config.ts
├── playwright.config.ts
├── app/
│   ├── layout.tsx                  # root layout
│   ├── globals.css                 # Tailwind base + dark theme
│   ├── providers.tsx               # QueryClientProvider
│   ├── page.tsx                    # home: project list
│   └── projects/
│       └── [projectId]/
│           ├── layout.tsx          # WorkspaceShell wrapper
│           ├── page.tsx            # redirect to first chapter
│           ├── chapters/
│           │   ├── page.tsx        # chapter list view (SidePanel content)
│           │   └── [chapterId]/
│           │       └── page.tsx    # ★ chapter workspace
│           ├── characters/page.tsx
│           ├── lore/page.tsx
│           ├── history/page.tsx
│           └── search/page.tsx
├── components/
│   ├── layout/
│   │   ├── WorkspaceShell.tsx
│   │   ├── ActivityBar.tsx
│   │   ├── SidePanel.tsx
│   │   ├── ContextPanel.tsx
│   │   └── BottomPanel.tsx
│   ├── editor/
│   │   ├── ChapterEditor.tsx
│   │   ├── extensions.ts
│   │   └── EditorToolbar.tsx
│   ├── generation/
│   │   ├── GenerateForm.tsx
│   │   ├── StreamView.tsx
│   │   └── useGenerate.ts
│   ├── entities/
│   │   ├── ProjectCard.tsx
│   │   ├── ChapterItem.tsx
│   │   ├── CharacterForm.tsx
│   │   ├── LoreForm.tsx
│   │   └── WorldOverviewForm.tsx
│   └── ui/
│       ├── Button.tsx
│       ├── Chip.tsx
│       ├── Field.tsx
│       └── Toast.tsx
├── lib/
│   ├── types.ts                    # TS types matching backend Pydantic
│   ├── api.ts                      # typed fetch wrapper + ApiError
│   ├── sse.ts                      # SSE async generator
│   ├── store.ts                    # Zustand persist
│   ├── queries.ts                  # TanStack Query hooks
│   └── debounce.ts                 # tiny debounce util
└── tests/                          # Vitest + RTL
    ├── sse.test.ts
    ├── store.test.ts
    ├── api.test.ts
    ├── debounce.test.ts
    ├── GenerateForm.test.tsx
    ├── StreamView.test.tsx
    └── e2e/                         # Playwright
        ├── project-chapter.spec.ts
        ├── generate-accept.spec.ts
        ├── invalid-context.spec.ts
        ├── character-crud.spec.ts
        └── generation-history.spec.ts
```

### Principles

- `lib/` zero React. `components/` grouped by domain. `app/` only routing + page assembly.
- One responsibility per file. Files over 300 lines get split.
- Each task produces a green test + commit.

---

## Task 1: Backend changes for M2b

**Files:**
- Modify: `app/memory/schema.py` (Chapter + 2 columns)
- Modify: `app/models/chapter.py` (expose new fields in Read/Update)
- Modify: `app/api/generation_logs.py` (add `project_id` param)
- Modify: `app/agents/writer.py` (`_finalize_done` writes back chapter defaults)
- Modify: `app/main.py` (add CORSMiddleware)
- Modify: `tests/test_chapter_models.py` (assert new fields)
- Modify: `tests/test_generation_logs.py` (project_id tests; relax chapter_id requirement)
- Modify: `tests/test_writer_agent.py` (assert writeback)
- Create: `tests/test_m2b_backend_changes.py` (consolidated M2b backend assertions)

- [ ] **Step 1.1: Write failing test for Chapter new fields**

Append to `tests/test_chapter_models.py`:

```python
def test_chapter_read_includes_default_set_fields():
    """ChapterRead must expose last_involved_character_ids and last_location_id."""
    from app.models.chapter import ChapterRead
    fields = ChapterRead.model_fields
    assert "last_involved_character_ids" in fields
    assert "last_location_id" in fields


def test_chapter_update_allows_default_set_patch():
    from app.models.chapter import ChapterUpdate
    fields = ChapterUpdate.model_fields
    assert "last_involved_character_ids" in fields
    assert "last_location_id" in fields
```

- [ ] **Step 1.2: Run test → verify fails**

```bash
pytest tests/test_chapter_models.py::test_chapter_read_includes_default_set_fields -v
```

Expected: FAIL with KeyError on `model_fields["last_involved_character_ids"]`.

- [ ] **Step 1.3: Add columns to Chapter ORM**

In `app/memory/schema.py`, modify the `Chapter` class (after `content_hash` line, before `created_at`):

```python
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    # M2b: default-set fields, written back by Writer Agent on generation done
    last_involved_character_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
```

- [ ] **Step 1.4: Expose new fields in Pydantic schemas**

In `app/models/chapter.py`, modify `ChapterBase` (add after `content_hash`):

```python
class ChapterBase(BaseModel):
    order_index: int = 0
    title: str = ""
    outline: str = ""
    content: str = ""
    status: str = "draft"
    plot_line_ids: list[int] = []
    summary: str = ""
    content_hash: str = ""
    last_involved_character_ids: list[int] = []
    last_location_id: int | None = None
```

In `ChapterUpdate`, add (after `content_hash`):

```python
class ChapterUpdate(BaseModel):
    order_index: int | None = None
    title: str | None = None
    outline: str | None = None
    content: str | None = None
    status: str | None = None
    plot_line_ids: list[int] | None = None
    summary: str | None = None
    content_hash: str | None = None
    last_involved_character_ids: list[int] | None = None
    last_location_id: int | None = None
```

- [ ] **Step 1.5: Run chapter model tests → verify pass**

```bash
pytest tests/test_chapter_models.py -v
```

Expected: All PASS.

- [ ] **Step 1.6: Write failing test for project_id query**

Append to `tests/test_generation_logs.py`:

```python
def test_list_with_project_id_returns_all_project_logs(client, fake_router):
    """list endpoint accepts project_id and returns all logs in that project."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    ch1 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 1,
                            "title": "CH1"}).json()["id"]
    ch2 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 2,
                            "title": "CH2"}).json()["id"]
    # Generate once per chapter
    for ch in (ch1, ch2):
        with client.stream("POST", f"/api/chapters/{ch}/generate",
                           json={"beat_text": "x",
                                 "involved_character_ids": [c1]}) as r:
            assert r.status_code == 200

    r = client.get(f"/api/generation-logs?project_id={pid}")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) == 2
    assert {log["chapter_id"] for log in logs} == {ch1, ch2}


def test_list_requires_chapter_or_project_id(client):
    """Neither param → 422."""
    r = client.get("/api/generation-logs")
    assert r.status_code == 422
```

- [ ] **Step 1.7: Run test → verify fails**

```bash
pytest tests/test_generation_logs.py::test_list_with_project_id_returns_all_project_logs -v
```

Expected: FAIL — `chapter_id` is still required.

Note: `test_list_requires_chapter_id` (existing) will now need updating since the requirement changed. Rename it:

Find `def test_list_requires_chapter_id` in `tests/test_generation_logs.py` and rename to `def test_list_requires_chapter_or_project_id`, replacing the body with the version above.

- [ ] **Step 1.8: Modify list_logs to accept project_id**

Replace `app/api/generation_logs.py` `list_logs` function:

```python
@router.get("", response_model=list[GenerationLogRead])
def list_logs(
    chapter_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if chapter_id is None and project_id is None:
        raise HTTPException(
            status_code=422,
            detail="must provide chapter_id or project_id",
        )
    stmt = select(GenerationLog)
    if chapter_id is not None:
        stmt = stmt.where(GenerationLog.chapter_id == chapter_id)
    else:
        stmt = stmt.where(GenerationLog.project_id == project_id)
    stmt = (
        stmt.order_by(GenerationLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))
```

- [ ] **Step 1.9: Run logs tests → verify pass**

```bash
pytest tests/test_generation_logs.py -v
```

Expected: All PASS.

- [ ] **Step 1.10: Write failing test for writer writeback**

Append to `tests/test_writer_agent.py`:

```python
def test_finalize_done_writes_back_chapter_defaults(db_session):
    """When generation done, chapter.last_involved_character_ids and last_location_id
    must be updated to the values used in this generation."""
    from app.memory.schema import Chapter
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    fake_router = FakeRouter([
        StreamEvent(type="token", text="hello"),
        StreamEvent(type="done", input_tokens=5, output_tokens=1,
                    stop_reason="end_turn"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[0].id, chars[1].id],
        location_id=loc.id,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    list(stream_generation(db_session, prep, router=fake_router))

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.last_involved_character_ids == [chars[0].id, chars[1].id]
    assert chapter.last_location_id == loc.id


def test_finalize_done_preserves_chapter_on_error(db_session):
    """Error path must NOT overwrite chapter defaults — keep previous values."""
    from app.memory.schema import Chapter
    p, chars, loc, faction, ch = _seed_full_project(db_session)
    # Pre-set defaults
    ch_ref = db_session.get(Chapter, ch.id)
    ch_ref.last_involved_character_ids = [chars[0].id]
    ch_ref.last_location_id = None
    db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="error", error_message="boom", error_code="X"),
    ])
    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[chars[1].id], location_id=loc.id,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    list(stream_generation(db_session, prep, router=fake_router))

    db_session.expire_all()
    chapter = db_session.get(Chapter, ch.id)
    # Untouched
    assert chapter.last_involved_character_ids == [chars[0].id]
    assert chapter.last_location_id is None
```

- [ ] **Step 1.11: Run test → verify fails**

```bash
pytest tests/test_writer_agent.py::test_finalize_done_writes_back_chapter_defaults -v
```

Expected: FAIL — chapter defaults not updated.

- [ ] **Step 1.12: Modify `_finalize_done` to write back chapter defaults**

In `app/agents/writer.py`, replace the `_finalize_done` function:

```python
def _finalize_done(
    db: Session,
    log_id: int,
    text: str,
    event,
) -> None:
    log = db.get(GenerationLog, log_id)
    if log is None:
        return
    log.generated_text = text
    log.input_tokens = event.input_tokens
    log.output_tokens = event.output_tokens
    log.stop_reason = event.stop_reason
    log.status = "done"
    log.finished_at = _now()

    # M2b: write back chapter default set
    chapter = db.get(Chapter, log.chapter_id)
    if chapter is not None:
        chapter.last_involved_character_ids = list(log.involved_character_ids)
        chapter.last_location_id = log.location_id

    db.commit()
```

Ensure `Chapter` is imported at the top of `app/agents/writer.py`:

```python
from app.memory.schema import Chapter, GenerationLog
```

- [ ] **Step 1.13: Run writer tests → verify pass**

```bash
pytest tests/test_writer_agent.py -v
```

Expected: All PASS (existing 5 + 2 new).

- [ ] **Step 1.14: Add CORSMiddleware to main.py**

In `app/main.py`, replace the file content:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    chapters,
    chapters_generate,
    characters,
    deps,
    generation_logs,
    health,
    llm,
    lore,
    projects,
    world,
)
from app.memory.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)

    # CORS — allow the Next.js dev server (M2b)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3300",
            "http://127.0.0.1:3300",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Accel-Buffering"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(world.router, prefix="/api/projects", tags=["world"])
    app.include_router(lore.router, prefix="/api/lore", tags=["lore"])
    app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
    app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
    app.include_router(chapters_generate.router, prefix="/api/chapters",
                       tags=["chapters_generate"])
    app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
    app.include_router(generation_logs.router, prefix="/api/generation-logs",
                       tags=["generation_logs"])
    return app


app = create_app()
```

- [ ] **Step 1.15: Run full backend test suite**

```bash
pytest -v
```

Expected: All previous tests pass (M1 + M2a + new M2b assertions). No regressions. If `test_list_requires_chapter_id` still exists with old name, delete or rename.

- [ ] **Step 1.16: Manual smoke test — drop DB, restart, verify CORS preflight**

```bash
rm -f /Users/bugx/novelAI/data/novelai.db /Users/bugx/novelAI/data/novelai.db-shm /Users/bugx/novelAI/data/novelai.db-wal
source /Users/bugx/novelAI/.venv/bin/activate
uvicorn app.main:app --port 8005 &
sleep 2
# CORS preflight
curl -s -i -X OPTIONS http://127.0.0.1:8005/api/projects \
  -H "Origin: http://localhost:3300" \
  -H "Access-Control-Request-Method: GET" | head -10
kill %1
```

Expected: HTTP 200 with `access-control-allow-origin: http://localhost:3300`.

- [ ] **Step 1.17: Commit**

```bash
git add app/memory/schema.py app/models/chapter.py app/api/generation_logs.py \
        app/agents/writer.py app/main.py tests/
git commit -m "feat(m2b): backend changes for frontend (chapter defaults + logs project_id + cors)"
```

---

## Task 2: Next.js project scaffold

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/next.config.mjs`
- Create: `web/tailwind.config.ts`
- Create: `web/postcss.config.js`
- Create: `web/.env.local`
- Create: `web/.env.example`
- Create: `web/.gitignore`
- Create: `web/app/layout.tsx`
- Create: `web/app/providers.tsx`
- Create: `web/app/globals.css`
- Create: `web/app/page.tsx` (minimal placeholder; real home page is Task 9)
- Create: `web/vitest.config.ts`
- Create: `web/vitest.setup.ts`

- [ ] **Step 2.1: Create `web/package.json`**

```json
{
  "name": "novelai-web",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev -p 3300",
    "build": "next build",
    "start": "next start -p 3300",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "@tiptap/core": "^3.0.0",
    "@tiptap/react": "^3.0.0",
    "@tiptap/starter-kit": "^3.0.0",
    "@tiptap/extension-markdown": "^3.0.0",
    "@tiptap/extension-placeholder": "^3.0.0",
    "@tiptap/extension-character-count": "^3.0.0",
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.6.0",
    "vitest": "^2.1.0"
  }
}
```

Note: Tailwind v3 (not v4) is chosen for stability — v4 changed config API significantly.

- [ ] **Step 2.2: Create `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 2.3: Create `web/next.config.mjs`**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

- [ ] **Step 2.4: Create `web/tailwind.config.ts`**

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Source Han Serif SC"', '"Noto Serif SC"', "Georgia", "serif"],
      },
      colors: {
        // VS Code Dark+ palette
        bg: { DEFAULT: "#1e1e1e", panel: "#252526", sidebar: "#333" },
        border: { DEFAULT: "#3c3c3c" },
        accent: { DEFAULT: "#0e639c", hover: "#1177bb" },
        text: { DEFAULT: "#cccccc", muted: "#888888" },
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 2.5: Create `web/postcss.config.js`**

```javascript
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 2.6: Create `web/.env.local` and `web/.env.example`**

`.env.local`:
```
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8005
```

`.env.example`:
```
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8005
```

- [ ] **Step 2.7: Create `web/.gitignore`**

```
node_modules/
.next/
.env.local
*.tsbuildinfo
playwright-report/
test-results/
```

- [ ] **Step 2.8: Create `web/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body {
  height: 100%;
  background-color: #1e1e1e;
  color: #cccccc;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
}

* {
  box-sizing: border-box;
}

/* Custom scrollbars (VS Code style) */
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #424242;
}
::-webkit-scrollbar-thumb:hover {
  background: #4f4f4f;
}

/* TipTap editor */
.ProseMirror {
  outline: none;
  min-height: 60vh;
}
.ProseMirror p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  color: #6a6a6a;
  float: left;
  height: 0;
  pointer-events: none;
}
```

- [ ] **Step 2.9: Create `web/app/providers.tsx`**

```typescript
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 2.10: Create `web/app/layout.tsx`**

```typescript
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "NovelAI",
  description: "本地优先的 AI 辅助小说写作工具",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 2.11: Create minimal `web/app/page.tsx` (placeholder)**

```typescript
export default function Home() {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <h1 className="text-2xl">NovelAI — scaffold OK</h1>
    </main>
  );
}
```

- [ ] **Step 2.12: Create `web/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});
```

- [ ] **Step 2.13: Create `web/vitest.setup.ts`**

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 2.14: Run `npm install`**

```bash
cd /Users/bugx/novelAI/web
npm install
```

Expected: completes without errors. Some peer dep warnings acceptable.

- [ ] **Step 2.15: Run dev server smoke test**

```bash
cd /Users/bugx/novelAI/web
npm run dev &
sleep 8
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3300/
kill %1
```

Expected: prints `200`.

- [ ] **Step 2.16: Commit**

```bash
git add web/
git commit -m "feat(m2b): next.js scaffold (app router, tailwind, vitest, tanstack-query)"
```

---

## Task 3: lib/types.ts — TS types matching backend

**Files:**
- Create: `web/lib/types.ts`
- Create: `web/tests/types.test.ts` (compile-time sanity)

- [ ] **Step 3.1: Create `web/lib/types.ts`**

```typescript
// Mirrors app/models/*.py Pydantic schemas on the backend.
// Keep field names in snake_case to match JSON payloads — no transformation layer.

export interface Project {
  id: number;
  title: string;
  genre: string;
  premise: string;
  main_theme: string;
  tone: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  title: string;
  genre?: string;
  premise?: string;
  main_theme?: string;
  tone?: string;
}

export interface ProjectUpdate {
  title?: string;
  genre?: string;
  premise?: string;
  main_theme?: string;
  tone?: string;
}

export interface WorldOverview {
  id: number;
  project_id: number;
  setting_era: string;
  geography_summary: string;
  history_summary: string;
  culture_summary: string;
  power_system: string;
  rules_and_taboos: string;
  created_at: string;
  updated_at: string;
}

export interface WorldOverviewUpdate {
  setting_era?: string;
  geography_summary?: string;
  history_summary?: string;
  culture_summary?: string;
  power_system?: string;
  rules_and_taboos?: string;
}

export type LoreType =
  | "location"
  | "faction"
  | "item"
  | "organization"
  | "concept"
  | "custom";

export interface LoreEntry {
  id: number;
  project_id: number;
  type: LoreType;
  name: string;
  title: string;
  description: string;
  attributes: Record<string, unknown>;
  parent_id: number | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface LoreCreate {
  project_id: number;
  type: LoreType;
  name: string;
  title?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  parent_id?: number | null;
  tags?: string[];
}

export interface LoreUpdate {
  type?: LoreType;
  name?: string;
  title?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  parent_id?: number | null;
  tags?: string[];
}

export interface Character {
  id: number;
  project_id: number;
  name: string;
  role: string;
  personality: Record<string, unknown>;
  speech_style: string;
  background: string;
  motivation: string;
  appearance: string;
  current_state: string;
  affiliations: number[];
  known_locations: number[];
  created_at: string;
  updated_at: string;
}

export interface CharacterCreate {
  project_id: number;
  name: string;
  role?: string;
  personality?: Record<string, unknown>;
  speech_style?: string;
  background?: string;
  motivation?: string;
  appearance?: string;
  current_state?: string;
  affiliations?: number[];
  known_locations?: number[];
}

export interface CharacterUpdate {
  name?: string;
  role?: string;
  personality?: Record<string, unknown>;
  speech_style?: string;
  background?: string;
  motivation?: string;
  appearance?: string;
  current_state?: string;
  affiliations?: number[];
  known_locations?: number[];
}

export interface Chapter {
  id: number;
  project_id: number;
  order_index: number;
  title: string;
  outline: string;
  content: string;
  status: string;
  plot_line_ids: number[];
  summary: string;
  content_hash: string;
  last_involved_character_ids: number[];
  last_location_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChapterCreate {
  project_id: number;
  order_index: number;
  title?: string;
  outline?: string;
  content?: string;
  status?: string;
}

export interface ChapterUpdate {
  order_index?: number;
  title?: string;
  outline?: string;
  content?: string;
  status?: string;
  summary?: string;
  last_involved_character_ids?: number[];
  last_location_id?: number | null;
}

export type ModelTask = "writer_long" | "writer_short";

export interface GenerateRequest {
  beat_text: string;
  instruction?: string;
  involved_character_ids: number[];
  location_id?: number | null;
  model_task?: ModelTask;
  max_tokens?: number;
}

export interface GenerationLogRead {
  id: number;
  chapter_id: number;
  project_id: number;
  beat_text: string;
  model: string | null;
  status: string;
  input_tokens: number;
  output_tokens: number;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerationLogDetail extends GenerationLogRead {
  instruction: string;
  involved_character_ids: number[];
  location_id: number | null;
  system_prompt: string;
  user_prompt: string;
  context_summary: Record<string, unknown>;
  generated_text: string | null;
  model_task: string | null;
  stop_reason: string | null;
}

// Context bundle carried in the SSE context event
export interface ContextBundlePreview {
  project: {
    id: number;
    title: string;
    genre: string;
    main_theme: string;
    tone: string;
    premise: string;
  };
  world_overview: {
    setting_era: string;
    geography_summary: string;
    history_summary: string;
    culture_summary: string;
    power_system: string;
    rules_and_taboos: string;
  } | null;
  characters: Array<{
    id: number;
    name: string;
    role: string;
    current_state: string;
  }>;
  relationships: Array<{
    from: string;
    to: string;
    type: string;
    strength: number;
    description: string;
  }>;
  faction_lore: Array<{ id: number; name: string; description: string }>;
  location_lore: Array<{ id: number; name: string; description: string }>;
  recent_chapter_summaries: Array<{
    chapter_id: number;
    order_index: number;
    title: string;
    summary: string;
  }>;
}
```

- [ ] **Step 3.2: Create `web/tests/types.test.ts` (compile-time check)**

```typescript
import { describe, it, expectTypeOf } from "vitest";
import type {
  Project,
  Chapter,
  GenerateRequest,
  GenerationLogDetail,
} from "@/lib/types";

describe("types", () => {
  it("Chapter has last_involved_character_ids as number[]", () => {
    expectTypeOf<Chapter["last_involved_character_ids"]>().toEqualTypeOf<number[]>();
  });

  it("Chapter.last_location_id is number | null", () => {
    expectTypeOf<Chapter["last_location_id"]>().toEqualTypeOf<number | null>();
  });

  it("Project has required fields", () => {
    const p: Project = {
      id: 1, title: "x", genre: "", premise: "", main_theme: "", tone: "",
      created_at: "", updated_at: "",
    };
    expectTypeOf(p).toMatchTypeOf<Project>();
  });

  it("GenerateRequest allows optional fields", () => {
    const r: GenerateRequest = {
      beat_text: "x",
      involved_character_ids: [1],
    };
    expectTypeOf(r).toMatchTypeOf<GenerateRequest>();
  });

  it("GenerationLogDetail has prompt fields", () => {
    expectTypeOf<GenerationLogDetail>().toHaveProperty("system_prompt").toBeString();
    expectTypeOf<GenerationLogDetail>().toHaveProperty("user_prompt").toBeString();
  });
});
```

- [ ] **Step 3.3: Run type tests**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit && npm test -- types.test.ts
```

Expected: 0 type errors; 5 tests pass.

- [ ] **Step 3.4: Commit**

```bash
git add web/lib/types.ts web/tests/types.test.ts
git commit -m "feat(m2b): ts types matching backend pydantic schemas"
```

---

## Task 4: lib/api.ts — typed fetch wrapper

**Files:**
- Create: `web/lib/api.ts`
- Create: `web/tests/api.test.ts`

- [ ] **Step 4.1: Write failing tests**

Create `web/tests/api.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError } from "@/lib/api";

const BASE = "http://127.0.0.1:8005";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE", BASE);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("api", () => {
  it("GET listProjects returns parsed JSON", async () => {
    const fake = [{ id: 1, title: "P" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fake), { status: 200 })
    );
    const out = await api.listProjects();
    expect(out).toEqual(fake);
    expect(fetch).toHaveBeenCalledWith(
      `${BASE}/api/projects`,
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
  });

  it("POST createProject sends JSON body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 9, title: "x" }), { status: 201 })
    );
    await api.createProject({ title: "x" });
    const call = (fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ title: "x" });
  });

  it("throws ApiError on non-2xx with parsed body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "nope" }), { status: 422 })
    );
    await expect(api.getProject(99)).rejects.toMatchObject({
      status: 422,
      body: { detail: "nope" },
    });
    try {
      await api.getProject(99);
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
    }
  });

  it("handles non-JSON error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Bad Gateway", { status: 502 })
    );
    await expect(api.getProject(1)).rejects.toMatchObject({ status: 502 });
  });

  it("updateChapter sends PATCH with partial body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 1, content: "x" }), { status: 200 })
    );
    await api.updateChapter(1, { content: "x" });
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toBe(`${BASE}/api/chapters/1`);
    expect(call[1].method).toBe("PATCH");
  });

  it("listGenerationLogs supports project_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    await api.listGenerationLogs({ project_id: 5 });
    expect((fetch as any).mock.calls[0][0]).toContain("project_id=5");
  });
});
```

- [ ] **Step 4.2: Run tests → verify fails**

```bash
cd /Users/bugx/novelAI/web && npm test -- api.test.ts
```

Expected: FAIL — `Cannot find module '@/lib/api'`.

- [ ] **Step 4.3: Create `web/lib/api.ts`**

```typescript
import type {
  Project, ProjectCreate, ProjectUpdate,
  WorldOverview, WorldOverviewUpdate,
  LoreEntry, LoreCreate, LoreUpdate,
  Character, CharacterCreate, CharacterUpdate,
  Chapter, ChapterCreate, ChapterUpdate,
  GenerationLogRead, GenerationLogDetail,
  GenerateRequest,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // Projects
  listProjects: () => http<Project[]>("/api/projects"),
  getProject: (id: number) => http<Project>(`/api/projects/${id}`),
  createProject: (data: ProjectCreate) =>
    http<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  updateProject: (id: number, data: ProjectUpdate) =>
    http<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProject: (id: number) =>
    http<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // World overview
  getWorldOverview: (projectId: number) =>
    http<WorldOverview | null>(`/api/projects/${projectId}/world-overview`),
  updateWorldOverview: (projectId: number, data: WorldOverviewUpdate) =>
    http<WorldOverview>(`/api/projects/${projectId}/world-overview`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Lore
  listLore: (projectId: number, type?: string) =>
    http<LoreEntry[]>(`/api/lore${qs({ project_id: projectId, type })}`),
  createLore: (data: LoreCreate) =>
    http<LoreEntry>("/api/lore", { method: "POST", body: JSON.stringify(data) }),
  updateLore: (id: number, data: LoreUpdate) =>
    http<LoreEntry>(`/api/lore/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteLore: (id: number) =>
    http<void>(`/api/lore/${id}`, { method: "DELETE" }),

  // Characters
  listCharacters: (projectId: number) =>
    http<Character[]>(`/api/characters${qs({ project_id: projectId })}`),
  getCharacter: (id: number) => http<Character>(`/api/characters/${id}`),
  createCharacter: (data: CharacterCreate) =>
    http<Character>("/api/characters", { method: "POST", body: JSON.stringify(data) }),
  updateCharacter: (id: number, data: CharacterUpdate) =>
    http<Character>(`/api/characters/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteCharacter: (id: number) =>
    http<void>(`/api/characters/${id}`, { method: "DELETE" }),

  // Chapters
  listChapters: (projectId: number) =>
    http<Chapter[]>(`/api/chapters${qs({ project_id: projectId })}`),
  getChapter: (id: number) => http<Chapter>(`/api/chapters/${id}`),
  createChapter: (data: ChapterCreate) =>
    http<Chapter>("/api/chapters", { method: "POST", body: JSON.stringify(data) }),
  updateChapter: (id: number, data: ChapterUpdate) =>
    http<Chapter>(`/api/chapters/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteChapter: (id: number) =>
    http<void>(`/api/chapters/${id}`, { method: "DELETE" }),

  // Generation logs (M2b: project_id supported)
  listGenerationLogs: (params: { chapter_id?: number; project_id?: number; limit?: number; offset?: number }) =>
    http<GenerationLogRead[]>(`/api/generation-logs${qs(params as Record<string, unknown>)}`),
  getGenerationLog: (id: number) =>
    http<GenerationLogDetail>(`/api/generation-logs/${id}`),
};
```

- [ ] **Step 4.4: Run tests → verify passes**

```bash
npm test -- api.test.ts
```

Expected: 6 PASS.

- [ ] **Step 4.5: Commit**

```bash
git add web/lib/api.ts web/tests/api.test.ts
git commit -m "feat(m2b): typed fetch wrapper + ApiError"
```

---

## Task 5: lib/sse.ts — SSE async generator

**Files:**
- Create: `web/lib/sse.ts`
- Create: `web/tests/sse.test.ts`

- [ ] **Step 5.1: Write failing tests**

Create `web/tests/sse.test.ts`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { streamGeneration, parseSseChunk } from "@/lib/sse";
import { ApiError } from "@/lib/api";

function makeReadable(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

describe("parseSseChunk", () => {
  it("parses single token event", () => {
    const chunk = "event: token\ndata: {\"text\":\"hi\"}\n";
    const ev = parseSseChunk(chunk);
    expect(ev).toEqual({ type: "token", text: "hi" });
  });

  it("parses meta event", () => {
    const chunk = 'event: meta\ndata: {"generation_log_id":1,"model":"x","model_task":"y","chapter_id":2,"started_at":"z"}\n';
    const ev = parseSseChunk(chunk);
    expect(ev?.type).toBe("meta");
    expect(ev && "generation_log_id" in ev && ev.generation_log_id).toBe(1);
  });

  it("parses event with Chinese content", () => {
    const chunk = 'event: token\ndata: {"text":"你好"}\n';
    const ev = parseSseChunk(chunk);
    expect(ev).toEqual({ type: "token", text: "你好" });
  });

  it("returns null on incomplete chunk", () => {
    expect(parseSseChunk("data: foo\n")).toBeNull();
  });
});

describe("streamGeneration", () => {
  it("yields events across multiple byte chunks", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    const chunks = [
      "event: meta\ndata: {\"generation_log_id\":1,\"model\":\"m\",\"model_task\":\"t\",\"chapter_id\":1,\"started_at\":\"s\"}\n\n",
      "event: token\ndata: {\"text\":\"Hello \"}\n\nevent: token\ndata: {\"text\":\"world\"}\n\n",
      "event: done\ndata: {\"generation_log_id\":1,\"input_tokens\":10,\"output_tokens\":2,\"stop_reason\":\"end_turn\"}\n\n",
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events.map((e) => e.type)).toEqual(["meta", "token", "token", "done"]);
  });

  it("buffers partial events across chunks", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    const chunks = [
      "event: token\ndata: {\"text\":",  // partial
      "\"half\"}\n\n",
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "token", text: "half" });
  });

  it("throws ApiError on non-2xx", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "bad" }), { status: 422 })
    );
    await expect(
      (async () => {
        for await (const _ of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
          // drain
        }
      })()
    ).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 5.2: Run tests → verify fails**

```bash
npm test -- sse.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 5.3: Create `web/lib/sse.ts`**

```typescript
import { ApiError } from "./api";
import type { ContextBundlePreview, GenerateRequest } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";

export type GenerationEvent =
  | { type: "meta"; generation_log_id: number; model: string; model_task: string; chapter_id: number; started_at: string }
  | { type: "context"; context_bundle: ContextBundlePreview }
  | { type: "token"; text: string }
  | { type: "done"; generation_log_id: number; input_tokens: number; output_tokens: number; stop_reason: string }
  | { type: "error"; message: string; code: string };

export function parseSseChunk(chunk: string): GenerationEvent | null {
  let eventType = "";
  let dataStr = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event: ")) eventType = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataStr += line.slice(6);
  }
  if (!eventType || !dataStr) return null;
  try {
    return { type: eventType, ...JSON.parse(dataStr) } as GenerationEvent;
  } catch {
    return null;
  }
}

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
    let errBody: unknown = null;
    try {
      errBody = await res.json();
    } catch {
      errBody = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, errBody);
  }

  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const ev = parseSseChunk(chunk);
        if (ev) yield ev;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 5.4: Run tests → verify passes**

```bash
npm test -- sse.test.ts
```

Expected: 7 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add web/lib/sse.ts web/tests/sse.test.ts
git commit -m "feat(m2b): sse async generator + chunk parser"
```

---

## Task 6: lib/store.ts — Zustand persist store

**Files:**
- Create: `web/lib/store.ts`
- Create: `web/tests/store.test.ts`

- [ ] **Step 6.1: Write failing tests**

Create `web/tests/store.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore, useGenerateParams } from "@/lib/store";

beforeEach(() => {
  localStorage.clear();
  useUIStore.setState({
    sidePanelWidth: 220,
    contextPanelWidth: 240,
    bottomPanelHeight: 200,
    bottomPanelOpen: false,
    activeView: "chapters",
    generationStatus: "idle",
    generateParams: { involvedCharacterIds: [], locationId: null },
  });
});

describe("useUIStore", () => {
  it("toggles bottomPanelOpen", () => {
    useUIStore.getState().toggleBottomPanel();
    expect(useUIStore.getState().bottomPanelOpen).toBe(true);
  });

  it("updates sidePanelWidth", () => {
    useUIStore.getState().setSidePanelWidth(300);
    expect(useUIStore.getState().sidePanelWidth).toBe(300);
  });

  it("partialize only persists layout fields", () => {
    useUIStore.setState({ generationStatus: "streaming", bottomPanelOpen: true });
    const persisted = JSON.parse(localStorage.getItem("m2b-ui") ?? "{}");
    expect(persisted.state).toMatchObject({
      sidePanelWidth: 220,
      bottomPanelOpen: true,
    });
    // generationStatus not persisted
    expect(persisted.state.generationStatus).toBeUndefined();
  });
});

describe("useGenerateParams", () => {
  it("sets involvedCharacterIds", () => {
    useGenerateParams.getState().setParams({ involvedCharacterIds: [1, 2] });
    expect(useGenerateParams.getState().involvedCharacterIds).toEqual([1, 2]);
  });

  it("setParams merges partial", () => {
    useGenerateParams.getState().setParams({ involvedCharacterIds: [1] });
    useGenerateParams.getState().setParams({ locationId: 7 });
    expect(useGenerateParams.getState()).toMatchObject({
      involvedCharacterIds: [1],
      locationId: 7,
    });
  });

  it("hydrateFromChapter resets params from chapter defaults", () => {
    useGenerateParams.getState().setParams({
      involvedCharacterIds: [99],
      locationId: 88,
    });
    useGenerateParams.getState().hydrateFromChapter({
      last_involved_character_ids: [3, 4],
      last_location_id: 9,
    });
    expect(useGenerateParams.getState()).toMatchObject({
      involvedCharacterIds: [3, 4],
      locationId: 9,
    });
  });
});
```

- [ ] **Step 6.2: Run tests → verify fails**

```bash
npm test -- store.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 6.3: Create `web/lib/store.ts`**

```typescript
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ActiveView = "chapters" | "characters" | "lore" | "history" | "search";
export type GenerationStatus = "idle" | "preparing" | "streaming" | "done" | "error";

interface UIState {
  // Layout (persisted)
  sidePanelWidth: number;
  contextPanelWidth: number;
  bottomPanelHeight: number;
  bottomPanelOpen: boolean;

  // Ephemeral (NOT persisted)
  activeView: ActiveView;
  generationStatus: GenerationStatus;

  // Actions
  setSidePanelWidth: (w: number) => void;
  setContextPanelWidth: (w: number) => void;
  setBottomPanelHeight: (h: number) => void;
  toggleBottomPanel: () => void;
  setBottomPanelOpen: (open: boolean) => void;
  setActiveView: (v: ActiveView) => void;
  setGenerationStatus: (s: GenerationStatus) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidePanelWidth: 220,
      contextPanelWidth: 240,
      bottomPanelHeight: 200,
      bottomPanelOpen: false,
      activeView: "chapters",
      generationStatus: "idle",

      setSidePanelWidth: (w) => set({ sidePanelWidth: w }),
      setContextPanelWidth: (w) => set({ contextPanelWidth: w }),
      setBottomPanelHeight: (h) => set({ bottomPanelHeight: h }),
      toggleBottomPanel: () => set((s) => ({ bottomPanelOpen: !s.bottomPanelOpen })),
      setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),
      setActiveView: (v) => set({ activeView: v }),
      setGenerationStatus: (s) => set({ generationStatus: s }),
    }),
    {
      name: "m2b-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        sidePanelWidth: s.sidePanelWidth,
        contextPanelWidth: s.contextPanelWidth,
        bottomPanelHeight: s.bottomPanelHeight,
        bottomPanelOpen: s.bottomPanelOpen,
      }),
    }
  )
);

// Separate non-persistent store for generate params (resets each chapter entry)
interface GenerateParamsState {
  involvedCharacterIds: number[];
  locationId: number | null;
  setParams: (p: Partial<Omit<GenerateParamsState, "setParams" | "hydrateFromChapter" | "reset">>) => void;
  hydrateFromChapter: (chapter: {
    last_involved_character_ids: number[];
    last_location_id: number | null;
  }) => void;
  reset: () => void;
}

export const useGenerateParams = create<GenerateParamsState>((set) => ({
  involvedCharacterIds: [],
  locationId: null,
  setParams: (p) => set(p),
  hydrateFromChapter: (chapter) =>
    set({
      involvedCharacterIds: [...(chapter.last_involved_character_ids ?? [])],
      locationId: chapter.last_location_id ?? null,
    }),
  reset: () => set({ involvedCharacterIds: [], locationId: null }),
}));
```

- [ ] **Step 6.4: Run tests → verify passes**

```bash
npm test -- store.test.ts
```

Expected: 6 PASS.

- [ ] **Step 6.5: Commit**

```bash
git add web/lib/store.ts web/tests/store.test.ts
git commit -m "feat(m2b): zustand persist (layout only) + generate params store"
```

---

## Task 7: lib/queries.ts + lib/debounce.ts

**Files:**
- Create: `web/lib/queries.ts`
- Create: `web/lib/debounce.ts`
- Create: `web/tests/debounce.test.ts`

- [ ] **Step 7.1: Write failing test for debounce**

Create `web/tests/debounce.test.ts`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { debounce } from "@/lib/debounce";

describe("debounce", () => {
  it("calls fn once after wait", async () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 500);
    d("a");
    d("b");
    d("c");
    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("c");
    vi.useRealTimers();
  });

  it("cancel prevents call", async () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 500);
    d("x");
    d.cancel();
    vi.advanceTimersByTime(500);
    expect(fn).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("flush invokes immediately", async () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 500);
    d("x");
    d.flush();
    expect(fn).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1); // not called again
    vi.useRealTimers();
  });
});
```

- [ ] **Step 7.2: Run → verify fails**

```bash
npm test -- debounce.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 7.3: Create `web/lib/debounce.ts`**

```typescript
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  wait: number
): ((...args: A) => void) & { cancel: () => void; flush: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastArgs: A | null = null;

  const wrapped = (...args: A) => {
    lastArgs = args;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      if (lastArgs) fn(...lastArgs);
      lastArgs = null;
    }, wait);
  };

  wrapped.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    lastArgs = null;
  };

  wrapped.flush = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (lastArgs) {
      fn(...lastArgs);
      lastArgs = null;
    }
  };

  return wrapped;
}
```

- [ ] **Step 7.4: Run → verify passes**

```bash
npm test -- debounce.test.ts
```

Expected: 3 PASS.

- [ ] **Step 7.5: Create `web/lib/queries.ts`**

```typescript
"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./api";
import type {
  Project, ProjectCreate, ProjectUpdate,
  WorldOverview, WorldOverviewUpdate,
  LoreEntry, LoreCreate, LoreUpdate,
  Character, CharacterCreate, CharacterUpdate,
  Chapter, ChapterCreate, ChapterUpdate,
  GenerationLogRead,
} from "./types";

// Projects
export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() });
}
export function useProject(id: number) {
  return useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id) });
}
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProjectCreate) => api.createProject(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useUpdateProject(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProjectUpdate) => api.updateProject(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

// World overview
export function useWorldOverview(projectId: number) {
  return useQuery({
    queryKey: ["world-overview", projectId],
    queryFn: () => api.getWorldOverview(projectId),
  });
}
export function useUpdateWorldOverview(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: WorldOverviewUpdate) => api.updateWorldOverview(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["world-overview", projectId] }),
  });
}

// Lore
export function useLore(projectId: number, type?: string) {
  return useQuery({
    queryKey: ["lore", projectId, type],
    queryFn: () => api.listLore(projectId, type),
  });
}
export function useCreateLore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LoreCreate) => api.createLore(data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["lore", data.project_id] });
    },
  });
}
export function useUpdateLore(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LoreUpdate) => api.updateLore(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lore", projectId] }),
  });
}
export function useDeleteLore(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteLore(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lore", projectId] }),
  });
}

// Characters
export function useCharacters(projectId: number) {
  return useQuery({
    queryKey: ["characters", projectId],
    queryFn: () => api.listCharacters(projectId),
  });
}
export function useCreateCharacter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CharacterCreate) => api.createCharacter(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["characters", data.project_id] }),
  });
}
export function useUpdateCharacter(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CharacterUpdate) => api.updateCharacter(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters", projectId] }),
  });
}
export function useDeleteCharacter(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteCharacter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters", projectId] }),
  });
}

// Chapters
export function useChapters(projectId: number) {
  return useQuery({
    queryKey: ["chapters", projectId],
    queryFn: () => api.listChapters(projectId),
  });
}
export function useChapter(id: number) {
  return useQuery({
    queryKey: ["chapter", id],
    queryFn: () => api.getChapter(id),
  });
}
export function useCreateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterCreate) => api.createChapter(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["chapters", data.project_id] }),
  });
}
export function useUpdateChapter(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterUpdate) => api.updateChapter(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapter", id] });
      qc.invalidateQueries({ queryKey: ["chapters"] });
    },
  });
}
export function useDeleteChapter(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteChapter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapters", projectId] }),
  });
}

// Generation logs
export function useGenerationLogsByChapter(chapterId: number) {
  return useQuery({
    queryKey: ["generation-logs", "chapter", chapterId],
    queryFn: () => api.listGenerationLogs({ chapter_id: chapterId }),
  });
}
export function useGenerationLogsByProject(projectId: number) {
  return useQuery({
    queryKey: ["generation-logs", "project", projectId],
    queryFn: () => api.listGenerationLogs({ project_id: projectId }),
  });
}
export function useGenerationLog(id: number) {
  return useQuery({
    queryKey: ["generation-log", id],
    queryFn: () => api.getGenerationLog(id),
  });
}
```

- [ ] **Step 7.6: Verify type-checks**

```bash
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 7.7: Commit**

```bash
git add web/lib/queries.ts web/lib/debounce.ts web/tests/debounce.test.ts
git commit -m "feat(m2b): tanstack query hooks + debounce util"
```

---

## Task 8: WorkspaceShell + ActivityBar (three-column layout)

**Files:**
- Create: `web/components/layout/WorkspaceShell.tsx`
- Create: `web/components/layout/ActivityBar.tsx`
- Create: `web/components/ui/Toast.tsx`
- Create: `web/app/projects/[projectId]/layout.tsx`

- [ ] **Step 8.1: Create `web/components/ui/Toast.tsx`**

Simple toast utility used across the app.

```typescript
"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; message: string; tone: "info" | "error" | "success" };

const ToastCtx = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-3 py-2 rounded shadow text-sm border ${
              t.tone === "error"
                ? "bg-red-950/80 border-red-800 text-red-200"
                : t.tone === "success"
                ? "bg-green-950/80 border-green-800 text-green-200"
                : "bg-[#252526] border-[#3c3c3c] text-[#cccccc]"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
```

- [ ] **Step 8.2: Update `web/app/providers.tsx` to wrap ToastProvider**

```typescript
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ToastProvider } from "@/components/ui/Toast";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 8.3: Create `web/components/layout/ActivityBar.tsx`**

```typescript
"use client";

import { usePathname, useRouter } from "next/navigation";

const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters", view: "chapters" as const },
  { icon: "👥", label: "人物", path: "characters", view: "characters" as const },
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
  { icon: "📜", label: "历史", path: "history", view: "history" as const },
  { icon: "🔍", label: "搜索", path: "search", view: "search" as const },
];

export function ActivityBar({ projectId }: { projectId: number }) {
  const pathname = usePathname();
  const router = useRouter();
  const base = `/projects/${projectId}`;
  return (
    <aside className="w-10 bg-[#333] flex flex-col items-center py-2 gap-1 shrink-0">
      {ITEMS.map((it) => {
        const isActive = pathname.startsWith(`${base}/${it.path}`);
        return (
          <button
            key={it.path}
            onClick={() => router.push(`${base}/${it.path}`)}
            title={it.label}
            className={`w-8 h-8 flex flex-col items-center justify-center rounded ${
              isActive
                ? "bg-[#094771] text-white"
                : "hover:bg-[#3a3a3a] text-[#888]"
            }`}
          >
            <span className="text-base leading-none">{it.icon}</span>
          </button>
        );
      })}
    </aside>
  );
}
```

- [ ] **Step 8.4: Create `web/components/layout/WorkspaceShell.tsx`**

```typescript
"use client";

import { type ReactNode } from "react";
import { ActivityBar } from "./ActivityBar";
import { useUIStore } from "@/lib/store";

export function WorkspaceShell({
  projectId,
  children,
}: {
  projectId: number;
  children: ReactNode;
}) {
  const sidePanelWidth = useUIStore((s) => s.sidePanelWidth);

  return (
    <div className="flex h-screen overflow-hidden">
      <ActivityBar projectId={projectId} />
      <div style={{ width: sidePanelWidth }} className="shrink-0 bg-[#252526] border-r border-[#3c3c3c] overflow-hidden">
        {/* SidePanel content injected by children */}
        {children}
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Editor + ContextPanel + BottomPanel injected by children */}
      </div>
    </div>
  );
}
```

Note: the layout renders the activity bar + a fixed-width side panel container. Editor / ContextPanel / BottomPanel are rendered by the page itself, not by the shell — this gives each route flexibility. (The unused flex-1 wrapper is intentional; pages mount under it via the layout's `children`.)

Actually let me reconsider — Next.js layouts wrap page content. If we want pages to control all three columns, the shell should just render ActivityBar + a content area. Rewrite:

```typescript
"use client";

import { type ReactNode } from "react";
import { ActivityBar } from "./ActivityBar";

export function WorkspaceShell({
  projectId,
  children,
}: {
  projectId: number;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <ActivityBar projectId={projectId} />
      <div className="flex-1 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}
```

Pages render their own side panel + editor + context panel + bottom panel via a shared `<Workspace>` sub-component (see Task 11).

- [ ] **Step 8.5: Create `web/app/projects/[projectId]/layout.tsx`**

```typescript
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";

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

- [ ] **Step 8.6: Create stub `web/app/projects/[projectId]/page.tsx` (redirect to chapters)**

```typescript
"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ProjectHomePage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/projects/${params.projectId}/chapters`);
  }, [params.projectId, router]);
  return <div className="p-4 text-[#888]">加载中...</div>;
}
```

- [ ] **Step 8.7: Type-check + commit**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit
git add web/components/layout/ web/components/ui/Toast.tsx web/app/providers.tsx \
        web/app/projects/
git commit -m "feat(m2b): workspace shell + activity bar + toast provider"
```

Expected: 0 type errors.

---

## Task 9: Home page (project list)

**Files:**
- Create: `web/components/entities/ProjectCard.tsx`
- Create: `web/components/ui/Button.tsx`
- Replace: `web/app/page.tsx`

- [ ] **Step 9.1: Create `web/components/ui/Button.tsx`**

```typescript
import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "ghost" | "danger" | "subtle";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const STYLES: Record<Variant, string> = {
  primary: "bg-[#0e639c] hover:bg-[#1177bb] text-white",
  ghost: "bg-transparent hover:bg-[#3a3a3a] text-[#cccccc]",
  danger: "bg-red-900 hover:bg-red-800 text-red-100",
  subtle: "bg-[#3c3c3c] hover:bg-[#4c4c4c] text-[#cccccc]",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "subtle", className = "", ...rest }, ref) => (
    <button
      ref={ref}
      className={`px-3 py-1.5 rounded text-sm disabled:opacity-40 disabled:cursor-not-allowed ${STYLES[variant]} ${className}`}
      {...rest}
    />
  )
);
Button.displayName = "Button";
```

- [ ] **Step 9.2: Create `web/components/entities/ProjectCard.tsx`**

```typescript
"use client";

import Link from "next/link";
import type { Project } from "@/lib/types";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/projects/${project.id}/chapters`}
      className="block bg-[#252526] hover:bg-[#2d2d2d] border border-[#3c3c3c] rounded p-4 transition-colors"
    >
      <h3 className="text-base font-semibold mb-1">{project.title || "未命名项目"}</h3>
      <p className="text-xs text-[#888] mb-2">
        {[project.genre, project.main_theme].filter(Boolean).join(" · ") || "无设定"}
      </p>
      <p className="text-xs text-[#666] line-clamp-2">{project.premise}</p>
    </Link>
  );
}
```

- [ ] **Step 9.3: Replace `web/app/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProjects, useCreateProject } from "@/lib/queries";
import { ProjectCard } from "@/components/entities/ProjectCard";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";

export default function HomePage() {
  const router = useRouter();
  const toast = useToast();
  const { data: projects, isLoading } = useProjects();
  const createProject = useCreateProject();
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const p = await createProject.mutateAsync({ title: "未命名项目" });
      router.push(`/projects/${p.id}/chapters`);
    } catch (e) {
      toast(`创建失败: ${(e as Error).message}`, "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl">NovelAI</h1>
          <Button variant="primary" onClick={handleCreate} disabled={creating}>
            + 新建项目
          </Button>
        </div>

        {isLoading ? (
          <p className="text-[#888]">加载中...</p>
        ) : !projects || projects.length === 0 ? (
          <p className="text-[#888]">还没有项目。点右上角"新建项目"开始。</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 9.4: Manual smoke test**

Start backend (port 8005) and frontend (port 3300):

```bash
# Terminal 1
cd /Users/bugx/novelAI && source .venv/bin/activate && uvicorn app.main:app --reload --port 8005 &

# Terminal 2
cd /Users/bugx/novelAI/web && npm run dev &
sleep 8

# Verify CORS works end-to-end
curl -s http://localhost:8005/api/projects -H "Origin: http://localhost:3300" -i | head -5
curl -s http://localhost:3300/ | head -5
```

Expected: backend responds 200 with CORS header; frontend HTML loads. Open `http://localhost:3300` in browser to verify rendering.

- [ ] **Step 9.5: Commit**

```bash
git add web/app/page.tsx web/components/entities/ProjectCard.tsx web/components/ui/Button.tsx
git commit -m "feat(m2b): home page with project list grid"
```

---

## Task 10: ChapterEditor (TipTap v3 + Markdown)

**Files:**
- Create: `web/components/editor/extensions.ts`
- Create: `web/components/editor/EditorToolbar.tsx`
- Create: `web/components/editor/ChapterEditor.tsx`
- Create: `web/components/editor/useChapterAutosave.ts`

- [ ] **Step 10.1: Create `web/components/editor/extensions.ts`**

```typescript
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "@tiptap/extension-markdown";
import Placeholder from "@tiptap/extension-placeholder";
import CharacterCount from "@tiptap/extension-character-count";

export const extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
  }),
  Markdown.configure({
    html: false,
    breaks: true,
    linkify: false,
    transformPastedText: true,
    transformCopiedText: true,
  }),
  Placeholder.configure({
    placeholder: "开始写作... 或在底部面板点 ⚡ 生成",
  }),
  CharacterCount.configure({
    limit: null,
  }),
];
```

Note: if `@tiptap/extension-markdown` v3 exposes a different `Markdown` configuration shape, check the package's README at install time and adjust. The two essential APIs are: constructor accepts config; instances attach `editor.storage.markdown.getMarkdown()`.

- [ ] **Step 10.2: Create `web/components/editor/EditorToolbar.tsx`**

```typescript
"use client";

import type { Editor } from "@tiptap/react";

export function EditorToolbar({
  editor,
  title,
  charCount,
}: {
  editor: Editor | null;
  title: string;
  charCount: number;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-[#3c3c3c] bg-[#252526]">
      <span className="text-sm text-[#cccccc] truncate max-w-md">{title || "未命名章节"}</span>
      <span className="text-xs text-[#888]">{charCount} 字</span>
    </div>
  );
}
```

- [ ] **Step 10.3: Create `web/components/editor/useChapterAutosave.ts`**

```typescript
"use client";

import { useEffect, useMemo, useRef } from "react";
import { useUpdateChapter } from "@/lib/queries";
import { debounce } from "@/lib/debounce";

export function useChapterAutosave(chapterId: number) {
  const mutation = useUpdateChapter(chapterId);
  const debounced = useMemo(
    () =>
      debounce((content: string) => {
        mutation.mutate({ content });
      }, 500),
    [mutation, chapterId]
  );
  const ref = useRef(debounced);
  ref.current = debounced;

  useEffect(() => () => ref.current.cancel(), []);

  const saveNow = (content: string) => {
    ref.current.flush();
    mutation.mutate({ content });
  };

  return { schedule: debounced, saveNow, mutation };
}
```

- [ ] **Step 10.4: Create `web/components/editor/ChapterEditor.tsx`**

```typescript
"use client";

import { useEffect, useRef } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import { extensions } from "./extensions";
import { EditorToolbar } from "./EditorToolbar";
import { useChapterAutosave } from "./useChapterAutosave";
import type { Chapter } from "@/lib/types";

export function ChapterEditor({ chapter }: { chapter: Chapter }) {
  const autosave = useChapterAutosave(chapter.id);
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null);

  const editor = useEditor({
    extensions,
    content: chapter.content || "",
    onUpdate: ({ editor }) => {
      // TipTap v3 Markdown extension exposes getMarkdown on storage
      const md = (editor.storage.markdown?.getMarkdown?.() ?? "") as string;
      autosave.schedule(md);
    },
    onBlur: ({ editor }) => {
      const md = (editor.storage.markdown?.getMarkdown?.() ?? "") as string;
      autosave.saveNow(md);
    },
    editorProps: {
      attributes: {
        class: "prose prose-invert max-w-none focus:outline-none min-h-[60vh] p-8 font-serif leading-relaxed",
      },
    },
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // Expose imperative API for "accept generated text" insertion
  useEffect(() => {
    (window as any).__chapterEditor = editor;
    return () => {
      delete (window as any).__chapterEditor;
    };
  }, [editor]);

  // Reset content when chapter changes
  useEffect(() => {
    if (editor && chapter.content !== undefined) {
      const current = editor.storage.markdown?.getMarkdown?.() ?? "";
      if (current !== chapter.content) {
        editor.commands.setContent(chapter.content || "", false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter.id]);

  const charCount = editor?.storage.characterCount?.characters?.() ?? 0;

  return (
    <div className="flex flex-col h-full">
      <EditorToolbar editor={editor} title={chapter.title} charCount={charCount} />
      <EditorContent editor={editor} className="flex-1 overflow-y-auto" />
    </div>
  );
}
```

- [ ] **Step 10.5: Type-check**

```bash
cd /Users/bugx/novelAI/web && npx tsc --noEmit
```

Expected: 0 errors. If `@tiptap/extension-markdown` v3 lacks the `Markdown` export, check the actual export name (it may be `MarkdownExtension` or re-exported via `StarterKit` config).

- [ ] **Step 10.6: Commit**

```bash
git add web/components/editor/
git commit -m "feat(m2b): chapter editor (tiptap v3 + markdown + autosave)"
```

---

## Task 11: Chapter workspace page (SidePanel + ChapterEditor + ContextPanel wiring)

**Files:**
- Create: `web/components/layout/SidePanel.tsx`
- Create: `web/components/entities/ChapterItem.tsx`
- Create: `web/components/layout/ChapterWorkspaceGrid.tsx`
- Create: `web/app/projects/[projectId]/chapters/page.tsx`
- Create: `web/app/projects/[projectId]/chapters/[chapterId]/page.tsx`

- [ ] **Step 11.1: Create `web/components/entities/ChapterItem.tsx`**

```typescript
"use client";

import Link from "next/link";
import type { Chapter } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-[#666]",
  writing: "bg-yellow-600",
  reviewed: "bg-blue-600",
  final: "bg-green-600",
};

export function ChapterItem({
  chapter,
  active,
}: {
  chapter: Chapter;
  active: boolean;
}) {
  const wordCount = chapter.content?.length ?? 0;
  return (
    <Link
      href={`#`}
      onClick={(e) => e.preventDefault()}
      className={`block px-3 py-2 rounded text-sm cursor-default ${
        active ? "bg-[#37373d] text-white" : "hover:bg-[#2a2a2a] text-[#cccccc]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLOR[chapter.status] ?? "bg-[#666]"}`} />
        <span className="flex-1 truncate">{chapter.title || `第 ${chapter.order_index} 章`}</span>
      </div>
      <div className="text-xs text-[#666] mt-0.5 pl-3.5">{wordCount} 字 · {chapter.status}</div>
    </Link>
  );
}
```

Note: `Link` with `href="#"` and `preventDefault` is a placeholder; this is rendered inside a `<select>`-style list managed by the parent. Real navigation is done by wrapping with proper `Link` in the parent — see Step 11.4.

Actually simpler — use real `Link`. Rewrite:

```typescript
"use client";

import Link from "next/link";
import type { Chapter } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-[#666]",
  writing: "bg-yellow-600",
  reviewed: "bg-blue-600",
  final: "bg-green-600",
};

export function ChapterItem({
  chapter,
  href,
  active,
}: {
  chapter: Chapter;
  href: string;
  active: boolean;
}) {
  const wordCount = chapter.content?.length ?? 0;
  return (
    <Link
      href={href}
      className={`block px-3 py-2 rounded text-sm ${
        active ? "bg-[#37373d] text-white" : "hover:bg-[#2a2a2a] text-[#cccccc]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLOR[chapter.status] ?? "bg-[#666]"}`} />
        <span className="flex-1 truncate">{chapter.title || `第 ${chapter.order_index} 章`}</span>
      </div>
      <div className="text-xs text-[#666] mt-0.5 pl-3.5">{wordCount} 字 · {chapter.status}</div>
    </Link>
  );
}
```

- [ ] **Step 11.2: Create `web/components/layout/SidePanel.tsx`**

```typescript
"use client";

import { type ReactNode } from "react";

export function SidePanel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#3c3c3c]">
        <span className="text-xs uppercase text-[#888] font-semibold">{title}</span>
        {action}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">{children}</div>
    </div>
  );
}
```

- [ ] **Step 11.3: Create `web/components/layout/ChapterWorkspaceGrid.tsx`**

This assembles the chapter workspace's three columns (sidebar list + editor + context panel) + bottom panel.

```typescript
"use client";

import { type ReactNode } from "react";
import { useUIStore } from "@/lib/store";

export function ChapterWorkspaceGrid({
  sidePanel,
  editor,
  contextPanel,
  bottomPanel,
}: {
  sidePanel: ReactNode;
  editor: ReactNode;
  contextPanel?: ReactNode;
  bottomPanel?: ReactNode;
}) {
  const sidePanelWidth = useUIStore((s) => s.sidePanelWidth);
  const contextPanelWidth = useUIStore((s) => s.contextPanelWidth);
  const bottomPanelOpen = useUIStore((s) => s.bottomPanelOpen);
  const bottomPanelHeight = useUIStore((s) => s.bottomPanelHeight);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <aside
          style={{ width: sidePanelWidth }}
          className="shrink-0 border-r border-[#3c3c3c] overflow-hidden bg-[#252526]"
        >
          {sidePanel}
        </aside>
        <main className="flex-1 min-w-[500px] overflow-hidden bg-[#1e1e1e]">
          {editor}
        </main>
        {contextPanel && (
          <aside
            style={{ width: contextPanelWidth }}
            className="shrink-0 border-l border-[#3c3c3c] overflow-hidden bg-[#252526]"
          >
            {contextPanel}
          </aside>
        )}
      </div>
      {bottomPanel && (
        <div
          style={{ height: bottomPanelOpen ? bottomPanelHeight : 28 }}
          className="shrink-0 border-t border-[#3c3c3c] bg-[#252526] overflow-hidden transition-[height] duration-150"
        >
          {bottomPanel}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 11.4: Create `web/app/projects/[projectId]/chapters/page.tsx`**

Chapter list view (no chapter selected yet):

```typescript
"use client";

import { useParams } from "next/navigation";
import { useChapters, useCreateChapter } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterItem } from "@/components/entities/ChapterItem";
import { Button } from "@/components/ui/Button";

export default function ChaptersListPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: chapters, isLoading } = useChapters(pid);
  const createChapter = useCreateChapter();

  const handleCreate = async () => {
    const order = (chapters?.reduce((m, c) => Math.max(m, c.order_index), 0) ?? 0) + 1;
    const ch = await createChapter.mutateAsync({
      project_id: pid,
      order_index: order,
      title: `第 ${order} 章`,
    });
    window.location.href = `/projects/${pid}/chapters/${ch.id}`;
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="章节"
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChapter.isPending}>
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-[#888] p-2">加载中...</p>
          ) : !chapters || chapters.length === 0 ? (
            <p className="text-xs text-[#888] p-2">还没有章节</p>
          ) : (
            chapters
              .slice()
              .sort((a, b) => a.order_index - b.order_index)
              .map((c) => (
                <ChapterItem
                  key={c.id}
                  chapter={c}
                  href={`/projects/${pid}/chapters/${c.id}`}
                  active={false}
                />
              ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full flex items-center justify-center text-[#888]">
          请从左侧选择一个章节
        </div>
      }
    />
  );
}

import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
```

Note: imports must be at the top of the file. Move the `ChapterWorkspaceGrid` import to the top in actual file.

- [ ] **Step 11.5: Create `web/app/projects/[projectId]/chapters/[chapterId]/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useChapter, useChapters } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterItem } from "@/components/entities/ChapterItem";
import { ChapterEditor } from "@/components/editor/ChapterEditor";
import { ContextPanel } from "@/components/layout/ContextPanel";
import { BottomPanel } from "@/components/layout/BottomPanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";

export default function ChapterPage() {
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>();
  const pid = Number(projectId);
  const cid = Number(chapterId);
  const { data: chapter, isLoading } = useChapter(cid);
  const { data: chapters } = useChapters(pid);
  const createChapter = useCreateChapter();
  const hydrate = useGenerateParams((s) => s.hydrateFromChapter);

  // Hydrate generate params from chapter defaults once per chapter entry
  useEffect(() => {
    if (chapter) hydrate(chapter);
  }, [chapter?.id, hydrate]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading || !chapter) {
    return <div className="flex-1 p-8 text-[#888]">加载章节...</div>;
  }

  const handleCreate = async () => {
    const order = (chapters?.reduce((m, c) => Math.max(m, c.order_index), 0) ?? 0) + 1;
    const ch = await createChapter.mutateAsync({
      project_id: pid,
      order_index: order,
      title: `第 ${order} 章`,
    });
    window.location.href = `/projects/${pid}/chapters/${ch.id}`;
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="章节"
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChapter.isPending}>
              + 新建
            </Button>
          }
        >
          {(chapters ?? [])
            .slice()
            .sort((a, b) => a.order_index - b.order_index)
            .map((c) => (
              <ChapterItem
                key={c.id}
                chapter={c}
                href={`/projects/${pid}/chapters/${c.id}`}
                active={c.id === cid}
              />
            ))}
        </SidePanel>
      }
      editor={<ChapterEditor chapter={chapter} />}
      contextPanel={<ContextPanel projectId={pid} />}
      bottomPanel={<BottomPanel chapterId={cid} />}
    />
  );
}

import { useCreateChapter } from "@/lib/queries";
```

Note: again, move imports to top in the actual file.

- [ ] **Step 11.6: Type-check (will fail — `ContextPanel` and `BottomPanel` not yet created)**

```bash
npx tsc --noEmit
```

Expected: FAIL on missing `ContextPanel` and `BottomPanel` imports. That's intentional — they're created in Tasks 12 and 13. Move on; the file will compile after those tasks.

- [ ] **Step 11.7: Commit (work-in-progress)**

```bash
git add web/components/layout/SidePanel.tsx \
        web/components/layout/ChapterWorkspaceGrid.tsx \
        web/components/entities/ChapterItem.tsx \
        web/app/projects/
git commit -m "feat(m2b): chapter workspace grid + chapter list page (wires pending components)"
```

---

## Task 12: ContextPanel

**Files:**
- Create: `web/components/layout/ContextPanel.tsx`
- Create: `web/components/ui/Chip.tsx`

- [ ] **Step 12.1: Create `web/components/ui/Chip.tsx`**

```typescript
import { type ReactNode } from "react";

export function Chip({
  children,
  selected,
  onClick,
  className = "",
}: {
  children: ReactNode;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2 py-0.5 rounded text-xs border ${
        selected
          ? "bg-[#0e639c] border-[#1177bb] text-white"
          : "bg-[#3c3c3c] border-[#4c4c4c] text-[#cccccc] hover:bg-[#4c4c4c]"
      } ${className}`}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 12.2: Create `web/components/layout/ContextPanel.tsx`**

```typescript
"use client";

import { useCharacters, useLore } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";

export function ContextPanel({ projectId }: { projectId: number }) {
  const { involvedCharacterIds, locationId } = useGenerateParams();
  const { data: characters } = useCharacters(projectId);
  const { data: allLore } = useLore(projectId);

  const involvedChars = (characters ?? []).filter((c) => involvedCharacterIds.includes(c.id));
  const location = (allLore ?? []).find((l) => l.id === locationId);
  const factionIds = new Set<number>();
  for (const c of involvedChars) for (const fid of c.affiliations ?? []) factionIds.add(fid);
  const factions = (allLore ?? []).filter((l) => l.type === "faction" && factionIds.has(l.id));

  return (
    <div className="h-full overflow-y-auto p-3 text-sm">
      <h3 className="text-xs uppercase text-[#888] mb-3">📋 当前场景</h3>

      <Section title="人物">
        {involvedChars.length === 0 ? (
          <Empty>未选</Empty>
        ) : (
          involvedChars.map((c) => (
            <div key={c.id} className="text-[#cccccc]">
              · {c.name}
              <span className="text-[#888]"> （{c.role}）</span>
            </div>
          ))
        )}
      </Section>

      <Section title="地点">
        {location ? (
          <div className="text-[#cccccc]">· {location.name}</div>
        ) : (
          <Empty>未选</Empty>
        )}
      </Section>

      <Section title="势力">
        {factions.length === 0 ? (
          <Empty>无</Empty>
        ) : (
          factions.map((f) => <div key={f.id} className="text-[#cccccc]">· {f.name}</div>)
        )}
      </Section>

      <div className="mt-6 p-2 bg-[#1e1e1e] rounded text-xs text-[#888]">
        💡 这是 AI 生成时将看到的常驻层。点人物/地点可在底部生成面板中调整。
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-xs text-[#aaa] mb-1">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-[#666] text-xs">{children}</div>;
}
```

- [ ] **Step 12.3: Type-check**

```bash
npx tsc --noEmit
```

Expected: still fails on `BottomPanel` only (Task 13). ContextPanel itself compiles.

- [ ] **Step 12.4: Commit**

```bash
git add web/components/layout/ContextPanel.tsx web/components/ui/Chip.tsx
git commit -m "feat(m2b): context panel (default-set + generate-params preview)"
```

---

## Task 13: Generation UI (useGenerate hook + BottomPanel + GenerateForm + StreamView)

**Files:**
- Create: `web/components/generation/useGenerate.ts`
- Create: `web/components/generation/GenerateForm.tsx`
- Create: `web/components/generation/StreamView.tsx`
- Create: `web/components/layout/BottomPanel.tsx`
- Create: `web/tests/GenerateForm.test.tsx`
- Create: `web/tests/StreamView.test.tsx`

- [ ] **Step 13.1: Create `web/components/generation/useGenerate.ts`**

```typescript
"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamGeneration, type GenerationEvent } from "@/lib/sse";
import { ApiError } from "@/lib/api";
import { useUIStore } from "@/lib/store";
import type { GenerateRequest } from "@/lib/types";

export function useGenerate(chapterId: number) {
  const qc = useQueryClient();
  const setGenerationStatus = useUIStore((s) => s.setGenerationStatus);
  const [events, setEvents] = useState<GenerationEvent[]>([]);
  const [generatedText, setGeneratedText] = useState("");
  const [status, setStatus] = useState<
    "idle" | "preparing" | "streaming" | "done" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(
    async (req: GenerateRequest) => {
      setStatus("preparing");
      setGenerationStatus("preparing");
      setEvents([]);
      setGeneratedText("");
      setError(null);

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        for await (const ev of streamGeneration(chapterId, req, ac.signal)) {
          setEvents((prev) => [...prev, ev]);
          if (ev.type === "token") {
            setGeneratedText((prev) => prev + ev.text);
            setStatus("streaming");
            setGenerationStatus("streaming");
          } else if (ev.type === "done") {
            setStatus("done");
            setGenerationStatus("done");
            qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "project"] });
          } else if (ev.type === "error") {
            setStatus("error");
            setGenerationStatus("error");
            setError(`${ev.message} (${ev.code})`);
          }
        }
      } catch (e) {
        if (e instanceof ApiError) {
          setStatus("error");
          setGenerationStatus("error");
          setError(`HTTP ${e.status}`);
          throw e;
        }
        // aborted — silent
      }
    },
    [chapterId, qc, setGenerationStatus]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setGenerationStatus("idle");
  }, [setGenerationStatus]);

  const reset = useCallback(() => {
    setEvents([]);
    setGeneratedText("");
    setStatus("idle");
    setError(null);
    setGenerationStatus("idle");
  }, [setGenerationStatus]);

  return { events, generatedText, status, error, start, cancel, reset };
}
```

- [ ] **Step 13.2: Write failing test for GenerateForm**

Create `web/tests/GenerateForm.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GenerateForm } from "@/components/generation/GenerateForm";

// Stub the useGenerate hook
vi.mock("@/components/generation/useGenerate", () => ({
  useGenerate: () => ({
    events: [],
    generatedText: "",
    status: "idle",
    error: null,
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "1", chapterId: "1" }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
  );
}

describe("GenerateForm", () => {
  it("disables submit when beat is empty", () => {
    renderWithProviders(<GenerateForm chapterId={1} />);
    const btn = screen.getByRole("button", { name: /生成/ });
    expect(btn).toBeDisabled();
  });

  it("disables submit when no character selected", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GenerateForm chapterId={1} />);
    await user.type(screen.getByPlaceholderText(/李雷推开/), "主角遇旧友");
    expect(screen.getByRole("button", { name: /生成/ })).toBeDisabled();
  });
});
```

- [ ] **Step 13.3: Run test → verify fails**

```bash
npm test -- GenerateForm.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 13.4: Create `web/components/generation/GenerateForm.tsx`**

```typescript
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useCharacters, useLore } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";
import { useGenerate } from "./useGenerate";
import { ApiError } from "@/lib/api";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { ModelTask } from "@/lib/types";

export function GenerateForm({ chapterId }: { chapterId: number }) {
  const params = useParams<{ projectId: string }>();
  const pid = Number(params.projectId);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);
  const locations = (lore ?? []).filter((l) => l.type === "location");

  // Local form state mirrors store; sync on change
  const { involvedCharacterIds, locationId, setParams } = useGenerateParams();
  const [beatText, setBeatText] = useState("");
  const [instruction, setInstruction] = useState("");
  const [modelTask, setModelTask] = useState<ModelTask>("writer_long");

  const { start, cancel, status } = useGenerate(chapterId);
  const toast = useToast();

  const toggleChar = (id: number) => {
    const next = involvedCharacterIds.includes(id)
      ? involvedCharacterIds.filter((x) => x !== id)
      : [...involvedCharacterIds, id].slice(0, 20);
    setParams({ involvedCharacterIds: next });
  };

  const handleSubmit = async () => {
    try {
      await start({
        beat_text: beatText,
        instruction,
        involved_character_ids: involvedCharacterIds,
        location_id: locationId,
        model_task: modelTask,
        max_tokens: 4096,
      });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 422) {
          const detail = (e.body as any)?.detail;
          if (detail?.error === "invalid_context") {
            toast(
              `无效 ID：人物 ${detail.invalid_character_ids?.join(", ") || "无"}；` +
                `地点 ${detail.invalid_location_id ?? "无"}`,
              "error"
            );
          } else if (Array.isArray(detail)) {
            toast(detail[0]?.msg ?? `HTTP ${e.status}`, "error");
          } else {
            toast(`HTTP ${e.status}`, "error");
          }
        } else {
          toast(`HTTP ${e.status}`, "error");
        }
      }
    }
  };

  const isStreaming = status === "preparing" || status === "streaming";

  return (
    <div className="space-y-3 text-sm">
      <div>
        <label className="text-xs text-[#aaa] block mb-1">Beat 文本 *</label>
        <textarea
          value={beatText}
          onChange={(e) => setBeatText(e.target.value)}
          placeholder="例：李雷推开残月酒馆的门，看见多年未见的韩梅在角落等候"
          rows={3}
          maxLength={2000}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        />
        <div className="text-xs text-[#666] mt-1">{beatText.length}/2000</div>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">涉及人物 *（1-20）</label>
        <div className="flex flex-wrap gap-1">
          {(characters ?? []).map((c) => (
            <Chip
              key={c.id}
              selected={involvedCharacterIds.includes(c.id)}
              onClick={() => toggleChar(c.id)}
            >
              {c.name}（{c.role}）
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">地点</label>
        <select
          value={locationId ?? ""}
          onChange={(e) => setParams({ locationId: e.target.value ? Number(e.target.value) : null })}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-full text-[#cccccc]"
        >
          <option value="">（无）</option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">附加指令</label>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="例：氛围压抑，对话简短"
          rows={2}
          maxLength={500}
          className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        />
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">模型任务</label>
        <select
          value={modelTask}
          onChange={(e) => setModelTask(e.target.value as ModelTask)}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 w-48 text-[#cccccc]"
        >
          <option value="writer_long">writer_long（高质量）</option>
          <option value="writer_short">writer_short（快速）</option>
        </select>
      </div>

      <div className="flex gap-2 pt-2">
        {isStreaming ? (
          <Button variant="danger" onClick={cancel}>✕ 取消</Button>
        ) : (
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!beatText.trim() || involvedCharacterIds.length === 0}
          >
            ✨ 生成
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 13.5: Run GenerateForm tests → verify pass**

```bash
npm test -- GenerateForm.test.tsx
```

Expected: 2 PASS.

- [ ] **Step 13.6: Write failing test for StreamView**

Create `web/tests/StreamView.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StreamView } from "@/components/generation/StreamView";

vi.mock("@/components/generation/useGenerate", () => {
  const state = {
    events: [],
    generatedText: "",
    status: "idle" as const,
    error: null,
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
  };
  return {
    useGenerate: () => state,
    // Hook to mutate state between tests
    __setMockState: (s: Partial<typeof state>) => Object.assign(state, s),
  };
});

describe("StreamView", () => {
  it("renders nothing when no events", () => {
    render(<StreamView chapterId={1} />);
    expect(screen.getByText(/准备就绪|暂无生成/)).toBeTruthy();
  });

  it("renders meta then tokens", async () => {
    const mod = await import("@/components/generation/useGenerate");
    (mod as any).__setMockState({
      events: [
        { type: "meta", generation_log_id: 1, model: "m", model_task: "writer_long", chapter_id: 1, started_at: "s" },
        { type: "token", text: "Hello " },
        { type: "token", text: "world" },
      ],
      generatedText: "Hello world",
      status: "streaming",
    });
    render(<StreamView chapterId={1} />);
    expect(screen.getByText(/Hello world/)).toBeTruthy();
    expect(screen.getByText(/log_id=1/)).toBeTruthy();
  });
});
```

- [ ] **Step 13.7: Run → verify fails**

```bash
npm test -- StreamView.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 13.8: Create `web/components/generation/StreamView.tsx`**

```typescript
"use client";

import { useGenerate } from "./useGenerate";
import { Button } from "@/components/ui/Button";
import type { Editor } from "@tiptap/react";

export function StreamView({ chapterId }: { chapterId: number }) {
  const { events, generatedText, status, reset, start, error } = useGenerate(chapterId);

  const meta = events.find((e) => e.type === "meta");
  const contextEvent = events.find((e) => e.type === "context");
  const doneEvent = events.find((e) => e.type === "done");

  const handleAccept = () => {
    const editor = (window as any).__chapterEditor as Editor | undefined;
    if (!editor) return;
    if (!generatedText) return;
    editor.chain().focus().insertContent(generatedText).run();
    const md = editor.storage.markdown?.getMarkdown?.() ?? "";
    // Trigger immediate save by simulating blur
    editor.commands.blur();
    reset();
  };

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-[#888]">
        暂无生成。点左侧 ✨ 生成 开始。
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3 text-xs">
      {meta && (
        <div className="text-[#888]">
          <span className="text-[#aaa]">[meta]</span> log_id={meta.generation_log_id} · model={meta.model}
        </div>
      )}

      {contextEvent && contextEvent.type === "context" && (
        <details className="bg-[#1e1e1e] rounded p-2">
          <summary className="cursor-pointer text-[#888]">
            📋 常驻层预览（{contextEvent.context_bundle.characters.length} 人物 ·{" "}
            {contextEvent.context_bundle.location_lore.length} 地点）
          </summary>
          <pre className="mt-2 text-[10px] text-[#aaa] whitespace-pre-wrap">
            {JSON.stringify(contextEvent.context_bundle, null, 2)}
          </pre>
        </details>
      )}

      <div className="font-serif text-sm leading-relaxed whitespace-pre-wrap min-h-[120px] text-[#cccccc]">
        {generatedText}
        {(status === "streaming" || status === "preparing") && (
          <span className="inline-block w-2 h-4 bg-[#888] animate-pulse ml-0.5" />
        )}
      </div>

      {error && (
        <div className="p-2 bg-red-950/30 border border-red-900 rounded text-red-400">
          ✗ {error}
        </div>
      )}

      {doneEvent && (
        <div className="flex items-center justify-between pt-2 border-t border-[#3c3c3c]">
          <span className="text-[#888]">
            ✓ 完成 · 输入 {doneEvent.input_tokens} / 输出 {doneEvent.output_tokens} tokens
          </span>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                reset();
              }}
            >
              重试
            </Button>
            <Button variant="primary" onClick={handleAccept} disabled={!generatedText}>
              ✓ 接受并插入
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 13.9: Create `web/components/layout/BottomPanel.tsx`**

```typescript
"use client";

import { useUIStore } from "@/lib/store";
import { GenerateForm } from "@/components/generation/GenerateForm";
import { StreamView } from "@/components/generation/StreamView";

export function BottomPanel({ chapterId }: { chapterId: number }) {
  const { bottomPanelOpen, toggleBottomPanel } = useUIStore();

  if (!bottomPanelOpen) {
    return (
      <button
        onClick={toggleBottomPanel}
        className="w-full h-full flex items-center justify-center text-xs text-[#888] hover:text-[#cccccc]"
      >
        ⚡ 生成（展开）
      </button>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-1 bg-[#1e1e1e] border-b border-[#3c3c3c]">
        <span className="text-xs text-[#888]">⚡ 生成</span>
        <button
          onClick={toggleBottomPanel}
          className="text-xs text-[#888] hover:text-white"
        >
          ▾ 收起
        </button>
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-2/5 overflow-y-auto p-3 border-r border-[#3c3c3c]">
          <GenerateForm chapterId={chapterId} />
        </div>
        <div className="flex-1 overflow-hidden">
          <StreamView chapterId={chapterId} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 13.10: Type-check + run all unit/component tests**

```bash
npx tsc --noEmit
npm test
```

Expected: 0 type errors. All tests pass (sse + store + api + debounce + types + GenerateForm + StreamView).

- [ ] **Step 13.11: Commit**

```bash
git add web/components/generation/ web/components/layout/BottomPanel.tsx \
        web/tests/GenerateForm.test.tsx web/tests/StreamView.test.tsx
git commit -m "feat(m2b): generation ui (useGenerate + GenerateForm + StreamView + BottomPanel)"
```

---

## Task 14: Entity management UI (characters / lore / world overview)

**Files:**
- Create: `web/components/entities/CharacterForm.tsx`
- Create: `web/components/entities/LoreForm.tsx`
- Create: `web/components/entities/WorldOverviewForm.tsx`
- Create: `web/app/projects/[projectId]/characters/page.tsx`
- Create: `web/app/projects/[projectId]/lore/page.tsx`

- [ ] **Step 14.1: Create `web/components/entities/WorldOverviewForm.tsx`**

```typescript
"use client";

import { useEffect, useState } from "react";
import { useWorldOverview, useUpdateWorldOverview } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { WorldOverviewUpdate } from "@/lib/types";

const FIELDS: Array<{ key: keyof WorldOverviewUpdate; label: string; rows?: number }> = [
  { key: "setting_era", label: "时代/纪元" },
  { key: "power_system", label: "力量体系" },
  { key: "rules_and_taboos", label: "规则与禁忌", rows: 3 },
  { key: "geography_summary", label: "地理概述", rows: 3 },
  { key: "history_summary", label: "历史概述", rows: 3 },
  { key: "culture_summary", label: "文化概述", rows: 3 },
];

export function WorldOverviewForm({ projectId }: { projectId: number }) {
  const { data, isLoading } = useWorldOverview(projectId);
  const update = useUpdateWorldOverview(projectId);
  const toast = useToast();
  const [form, setForm] = useState<WorldOverviewUpdate>({});

  useEffect(() => {
    if (data) {
      setForm({
        setting_era: data.setting_era,
        power_system: data.power_system,
        rules_and_taboos: data.rules_and_taboos,
        geography_summary: data.geography_summary,
        history_summary: data.history_summary,
        culture_summary: data.culture_summary,
      });
    }
  }, [data]);

  const save = debounce((value: WorldOverviewUpdate) => {
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const handleChange = (key: keyof WorldOverviewUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  if (isLoading) return <div className="p-4 text-[#888]">加载中...</div>;

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <h2 className="text-lg">世界观</h2>
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          <textarea
            value={(form[f.key] as string) ?? ""}
            onChange={(e) => handleChange(f.key, e.target.value)}
            rows={f.rows ?? 1}
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 14.2: Create `web/components/entities/CharacterForm.tsx`**

```typescript
"use client";

import { useEffect, useState } from "react";
import { useCharacters, useCreateCharacter, useUpdateCharacter, useDeleteCharacter, useLore } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import type { Character, CharacterUpdate } from "@/lib/types";

const TEXT_FIELDS: Array<{ key: keyof Character; label: string }> = [
  { key: "name", label: "姓名" },
  { key: "role", label: "角色" },
  { key: "speech_style", label: "说话风格" },
  { key: "background", label: "背景" },
  { key: "motivation", label: "动机" },
  { key: "appearance", label: "外貌" },
  { key: "current_state", label: "当前状态" },
];

export function CharacterForm({
  projectId,
  character,
  onDeleted,
}: {
  projectId: number;
  character?: Character;
  onDeleted?: () => void;
}) {
  const update = useUpdateCharacter(character?.id ?? 0, projectId);
  const del = useDeleteCharacter(projectId);
  const toast = useToast();
  const { data: lore } = useLore(projectId);
  const factions = (lore ?? []).filter((l) => l.type === "faction");
  const locations = (lore ?? []).filter((l) => l.type === "location");

  const [form, setForm] = useState<CharacterUpdate>({});

  useEffect(() => {
    if (character) {
      setForm({
        name: character.name,
        role: character.role,
        speech_style: character.speech_style,
        background: character.background,
        motivation: character.motivation,
        appearance: character.appearance,
        current_state: character.current_state,
        affiliations: character.affiliations,
        known_locations: character.known_locations,
      });
    }
  }, [character?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = debounce((value: CharacterUpdate) => {
    if (!character) return;
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const setText = (key: keyof CharacterUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  const toggleAff = (id: number) => {
    if (!character) return;
    const current = form.affiliations ?? character.affiliations ?? [];
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    setForm({ ...form, affiliations: next });
    save({ ...form, affiliations: next });
  };

  const toggleLoc = (id: number) => {
    if (!character) return;
    const current = form.known_locations ?? character.known_locations ?? [];
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    setForm({ ...form, known_locations: next });
    save({ ...form, known_locations: next });
  };

  if (!character) {
    return <div className="p-4 text-[#888]">请从左侧选择或新建人物</div>;
  }

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{form.name || character.name || "未命名"}</h2>
        <Button
          variant="danger"
          onClick={() => {
            if (!confirm(`删除人物 "${character.name}"？此操作不可撤销。`)) return;
            del.mutate(character.id, {
              onSuccess: () => onDeleted?.(),
              onError: (e) => toast(`删除失败: ${(e as Error).message}`, "error"),
            });
          }}
        >
          删除
        </Button>
      </div>

      {TEXT_FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          <input
            value={(form[f.key] as string) ?? ""}
            onChange={(e) => setText(f.key, e.target.value)}
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          />
        </div>
      ))}

      <div>
        <label className="text-xs text-[#aaa] block mb-1">所属势力</label>
        <div className="flex flex-wrap gap-1">
          {factions.map((f) => (
            <Chip
              key={f.id}
              selected={(form.affiliations ?? character.affiliations ?? []).includes(f.id)}
              onClick={() => toggleAff(f.id)}
            >
              {f.name}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">活动地点</label>
        <div className="flex flex-wrap gap-1">
          {locations.map((l) => (
            <Chip
              key={l.id}
              selected={(form.known_locations ?? character.known_locations ?? []).includes(l.id)}
              onClick={() => toggleLoc(l.id)}
            >
              {l.name}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 14.3: Create `web/components/entities/LoreForm.tsx`**

```typescript
"use client";

import { useEffect, useState } from "react";
import { useLore, useUpdateLore, useDeleteLore } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { LoreEntry, LoreUpdate, LoreType } from "@/lib/types";

const TEXT_FIELDS: Array<{ key: keyof LoreEntry; label: string; rows?: number }> = [
  { key: "name", label: "名称" },
  { key: "title", label: "别名" },
  { key: "description", label: "描述", rows: 4 },
];

export function LoreForm({
  projectId,
  lore,
  onDeleted,
}: {
  projectId: number;
  lore?: LoreEntry;
  onDeleted?: () => void;
}) {
  const update = useUpdateLore(lore?.id ?? 0, projectId);
  const del = useDeleteLore(projectId);
  const { data: allLore } = useLore(projectId);
  const toast = useToast();

  const [form, setForm] = useState<LoreUpdate>({});

  useEffect(() => {
    if (lore) {
      setForm({
        type: lore.type,
        name: lore.name,
        title: lore.title,
        description: lore.description,
        parent_id: lore.parent_id,
      });
    }
  }, [lore?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = debounce((value: LoreUpdate) => {
    if (!lore) return;
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const setText = (key: keyof LoreUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  if (!lore) {
    return <div className="p-4 text-[#888]">请从左侧选择或新建条目</div>;
  }

  // For locations, parent candidates are other locations of same project (excluding self + descendants)
  const sameTypeLocations = (allLore ?? []).filter(
    (l) => l.type === "location" && l.id !== lore.id
  );

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{form.name || lore.name || "未命名"}</h2>
        <Button
          variant="danger"
          onClick={() => {
            if (!confirm(`删除 "${lore.name}"？`)) return;
            del.mutate(lore.id, {
              onSuccess: () => onDeleted?.(),
              onError: (e) => toast(`删除失败: ${(e as Error).message}`, "error"),
            });
          }}
        >
          删除
        </Button>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">类型</label>
        <select
          value={(form.type as LoreType) ?? lore.type}
          onChange={(e) => {
            const v = e.target.value as LoreType;
            setForm({ ...form, type: v });
            save({ ...form, type: v });
          }}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        >
          {["location", "faction", "item", "organization", "concept", "custom"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {TEXT_FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          {f.rows ? (
            <textarea
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              rows={f.rows}
              className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
            />
          ) : (
            <input
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
            />
          )}
        </div>
      ))}

      {lore.type === "location" && (
        <div>
          <label className="text-xs text-[#aaa] block mb-1">上级地点</label>
          <select
            value={form.parent_id ?? lore.parent_id ?? ""}
            onChange={(e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              setForm({ ...form, parent_id: v });
              save({ ...form, parent_id: v });
            }}
            className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          >
            <option value="">（顶级）</option>
            {sameTypeLocations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 14.4: Create `web/app/projects/[projectId]/characters/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import {
  useCharacters,
  useCreateCharacter,
} from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { CharacterForm } from "@/components/entities/CharacterForm";
import { Button } from "@/components/ui/Button";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: characters, isLoading } = useCharacters(pid);
  const createChar = useCreateCharacter();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (characters ?? []).find((c) => c.id === selectedId);

  const handleCreate = async () => {
    const c = await createChar.mutateAsync({ project_id: pid, name: "未命名" });
    setSelectedId(c.id);
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="人物"
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChar.isPending}>
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-[#888] p-2">加载中...</p>
          ) : !characters || characters.length === 0 ? (
            <p className="text-xs text-[#888] p-2">还没有人物</p>
          ) : (
            characters.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === c.id
                    ? "bg-[#37373d] text-white"
                    : "hover:bg-[#2a2a2a] text-[#cccccc]"
                }`}
              >
                {c.name || "未命名"} <span className="text-[#888]">({c.role})</span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          <CharacterForm
            projectId={pid}
            character={selected}
            onDeleted={() => setSelectedId(null)}
          />
        </div>
      }
    />
  );
}
```

- [ ] **Step 14.5: Create `web/app/projects/[projectId]/lore/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useLore, useCreateLore, useWorldOverview } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { LoreForm } from "@/components/entities/LoreForm";
import { WorldOverviewForm } from "@/components/entities/WorldOverviewForm";
import { Button } from "@/components/ui/Button";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import type { LoreType } from "@/lib/types";

const TABS: Array<{ key: string; label: string; types: LoreType[] }> = [
  { key: "overview", label: "世界观", types: [] },
  { key: "location", label: "地点", types: ["location"] },
  { key: "faction", label: "势力", types: ["faction"] },
  { key: "item", label: "物品", types: ["item"] },
  { key: "other", label: "其他", types: ["organization", "concept", "custom"] },
];

export default function LorePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [tab, setTab] = useState<string>("location");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: lore } = useLore(pid);
  const createLore = useCreateLore();
  const { data: worldOverview } = useWorldOverview(pid);

  const currentTab = TABS.find((t) => t.key === tab)!;
  const filtered = (lore ?? []).filter((l) =>
    tab === "overview" ? false : currentTab.types.includes(l.type)
  );
  const selected = (lore ?? []).find((l) => l.id === selectedId);

  const handleCreate = async () => {
    if (tab === "overview") return;
    const l = await createLore.mutateAsync({
      project_id: pid,
      type: currentTab.types[0],
      name: "未命名",
    });
    setSelectedId(l.id);
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="设定">
          <div className="flex flex-wrap gap-1 mb-2 px-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setTab(t.key);
                  setSelectedId(null);
                }}
                className={`px-2 py-0.5 rounded text-xs ${
                  tab === t.key
                    ? "bg-[#0e639c] text-white"
                    : "bg-[#3c3c3c] text-[#cccccc]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {tab !== "overview" && (
            <div className="px-1 mb-2">
              <Button variant="ghost" onClick={handleCreate} disabled={createLore.isPending}>
                + 新建
              </Button>
            </div>
          )}
          {tab === "overview" ? (
            <p className="text-xs text-[#888] p-2">
              {worldOverview ? "点右侧编辑" : "右侧创建"}
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-[#888] p-2">无</p>
          ) : (
            filtered.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelectedId(l.id)}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === l.id
                    ? "bg-[#37373d] text-white"
                    : "hover:bg-[#2a2a2a] text-[#cccccc]"
                }`}
              >
                {l.name}
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {tab === "overview" ? (
            <WorldOverviewForm projectId={pid} />
          ) : (
            <LoreForm
              projectId={pid}
              lore={selected}
              onDeleted={() => setSelectedId(null)}
            />
          )}
        </div>
      }
    />
  );
}
```

- [ ] **Step 14.6: Type-check**

```bash
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 14.7: Commit**

```bash
git add web/components/entities/CharacterForm.tsx \
        web/components/entities/LoreForm.tsx \
        web/components/entities/WorldOverviewForm.tsx \
        web/app/projects/\[projectId\]/characters/ \
        web/app/projects/\[projectId\]/lore/
git commit -m "feat(m2b): entity management UI (characters, lore, world overview)"
```

---

## Task 15: History + Search pages

**Files:**
- Create: `web/app/projects/[projectId]/history/page.tsx`
- Create: `web/app/projects/[projectId]/search/page.tsx`

- [ ] **Step 15.1: Create `web/app/projects/[projectId]/history/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import {
  useGenerationLogsByProject,
  useGenerationLog,
  useChapters,
} from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";

export default function HistoryPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: logs, isLoading } = useGenerationLogsByProject(pid);
  const { data: chapters } = useChapters(pid);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: detail } = useGenerationLog(selectedId ?? 0);

  // Group logs by chapter_id, ordered by chapter order_index
  const grouped = useMemo(() => {
    const chapterOrder = new Map((chapters ?? []).map((c) => [c.id, c.order_index]));
    const groups = new Map<number, typeof logs>();
    for (const log of logs ?? []) {
      const arr = groups.get(log.chapter_id) ?? [];
      arr.push(log);
      groups.set(log.chapter_id, arr);
    }
    return Array.from(groups.entries())
      .map(([chapterId, items]) => ({ chapterId, items: items! }))
      .sort(
        (a, b) =>
          (chapterOrder.get(b.chapterId) ?? 0) - (chapterOrder.get(a.chapterId) ?? 0)
      );
  }, [logs, chapters]);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="历史">
          {isLoading ? (
            <p className="text-xs text-[#888] p-2">加载中...</p>
          ) : grouped.length === 0 ? (
            <p className="text-xs text-[#888] p-2">无生成记录</p>
          ) : (
            grouped.map(({ chapterId, items }) => {
              const ch = (chapters ?? []).find((c) => c.id === chapterId);
              return (
                <div key={chapterId} className="mb-2">
                  <div className="text-xs text-[#888] px-2 py-1">
                    {ch?.title ?? `Chapter ${chapterId}`} ({items.length})
                  </div>
                  {items.map((log) => (
                    <button
                      key={log.id}
                      onClick={() => setSelectedId(log.id)}
                      className={`block w-full text-left px-3 py-1.5 rounded text-xs ${
                        selectedId === log.id
                          ? "bg-[#37373d] text-white"
                          : "hover:bg-[#2a2a2a] text-[#cccccc]"
                      }`}
                    >
                      #{log.id} · {log.status} ·{" "}
                      {log.finished_at
                        ? new Date(log.finished_at).toLocaleString()
                        : "..."}
                    </button>
                  ))}
                </div>
              );
            })
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4 text-sm">
          {!detail ? (
            <p className="text-[#888]">请从左侧选择记录</p>
          ) : (
            <div className="space-y-4 max-w-3xl">
              <div className="text-xs text-[#888]">
                #{detail.id} · chapter_id={detail.chapter_id} · status={detail.status} ·{" "}
                input={detail.input_tokens} output={detail.output_tokens}
              </div>
              <details open>
                <summary className="cursor-pointer text-[#aaa]">Beat + 指令</summary>
                <pre className="mt-2 p-2 bg-[#1e1e1e] rounded whitespace-pre-wrap text-xs">
                  {detail.beat_text}
                  {detail.instruction ? `\n\n[指令] ${detail.instruction}` : ""}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-[#aaa]">System Prompt</summary>
                <pre className="mt-2 p-2 bg-[#1e1e1e] rounded whitespace-pre-wrap text-xs">
                  {detail.system_prompt}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-[#aaa]">User Prompt</summary>
                <pre className="mt-2 p-2 bg-[#1e1e1e] rounded whitespace-pre-wrap text-xs">
                  {detail.user_prompt}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-[#aaa]">Generated Text</summary>
                <pre className="mt-2 p-2 bg-[#1e1e1e] rounded whitespace-pre-wrap text-xs">
                  {detail.generated_text ?? "(empty)"}
                </pre>
              </details>
            </div>
          )}
        </div>
      }
    />
  );
}
```

- [ ] **Step 15.2: Create `web/app/projects/[projectId]/search/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useChapters, useCharacters, useLore } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import Link from "next/link";

export default function SearchPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [q, setQ] = useState("");
  const { data: chapters } = useChapters(pid);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);

  const needle = q.trim().toLowerCase();
  const match = (s: string | undefined | null) =>
    !!needle && !!s && s.toLowerCase().includes(needle);

  const chapterHits = (chapters ?? []).filter(
    (c) => match(c.title) || match(c.content) || match(c.outline)
  );
  const charHits = (characters ?? []).filter(
    (c) => match(c.name) || match(c.background) || match(c.motivation)
  );
  const loreHits = (lore ?? []).filter(
    (l) => match(l.name) || match(l.description)
  );

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="搜索">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索章节/人物/设定…"
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc] text-sm"
          />
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4 text-sm space-y-4">
          {!needle ? (
            <p className="text-[#888]">输入关键字搜索项目内容（substring 匹配）</p>
          ) : (
            <>
              <Section title={`章节 (${chapterHits.length})`}>
                {chapterHits.map((c) => (
                  <Link
                    key={c.id}
                    href={`/projects/${pid}/chapters/${c.id}`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {c.title} <span className="text-[#888]">#{c.id}</span>
                  </Link>
                ))}
              </Section>
              <Section title={`人物 (${charHits.length})`}>
                {charHits.map((c) => (
                  <Link
                    key={c.id}
                    href={`/projects/${pid}/characters`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {c.name} <span className="text-[#888]">({c.role})</span>
                  </Link>
                ))}
              </Section>
              <Section title={`设定 (${loreHits.length})`}>
                {loreHits.map((l) => (
                  <Link
                    key={l.id}
                    href={`/projects/${pid}/lore`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {l.name} <span className="text-[#888]">({l.type})</span>
                  </Link>
                ))}
              </Section>
            </>
          )}
        </div>
      }
    />
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs text-[#888] mb-1">{title}</h3>
      {children}
    </div>
  );
}
```

- [ ] **Step 15.3: Type-check**

```bash
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 15.4: Commit**

```bash
git add web/app/projects/\[projectId\]/history/ web/app/projects/\[projectId\]/search/
git commit -m "feat(m2b): history + search pages"
```

---

## Task 16: E2E tests (Playwright) + final integration

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/tests/e2e/project-chapter.spec.ts`
- Create: `web/tests/e2e/generate-accept.spec.ts`
- Create: `web/tests/e2e/invalid-context.spec.ts`
- Modify: `web/package.json` (e2e script)

- [ ] **Step 16.1: Create `web/playwright.config.ts`**

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false, // shared SQLite
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3300",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "cd .. && source .venv/bin/activate && uvicorn app.main:app --port 8005",
      url: "http://127.0.0.1:8005/api/health",
      timeout: 30_000,
      reuseExistingServer: true,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3300",
      timeout: 60_000,
      reuseExistingServer: true,
    },
  ],
});
```

- [ ] **Step 16.2: Create `web/tests/e2e/project-chapter.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("create project, navigate to chapters, create chapter", async ({ page }) => {
  await page.goto("/");
  await page.click("text=新建项目");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  // Create chapter
  await page.click("text=+ 新建");
  await page.waitForURL(/\/chapters\/\d+/);

  // Editor visible
  await expect(page.locator(".ProseMirror")).toBeVisible();

  // Type content
  await page.locator(".ProseMirror").click();
  await page.keyboard.type("测试章节内容");
  await page.locator(".ProseMirror").blur();

  // Wait for autosave
  await page.waitForTimeout(700);

  // Reload to verify persistence
  await page.reload();
  await expect(page.locator(".ProseMirror")).toContainText("测试章节内容");
});
```

- [ ] **Step 16.3: Create `web/tests/e2e/generate-accept.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("generate and accept inserts into editor", async ({ page }) => {
  // Setup: create project + chapter via UI, then mock SSE
  await page.goto("/");
  await page.click("text=新建项目");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  const projectId = new URL(page.url()).pathname.split("/")[2];

  // Seed character + chapter via API (faster than UI clicks)
  await fetch(`http://127.0.0.1:8005/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), name: "测试人物" }),
  });
  const charId = await fetch(`http://127.0.0.1:8005/api/characters?project_id=${projectId}`)
    .then((r) => r.json())
    .then((arr) => arr[0].id);

  const ch = await fetch(`http://127.0.0.1:8005/api/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), order_index: 1, title: "测试章节" }),
  }).then((r) => r.json());

  // Mock SSE response
  const sseBody = [
    'event: meta\ndata: {"generation_log_id":1,"model":"m","model_task":"writer_long","chapter_id":' + ch.id + ',"started_at":"s"}\n\n',
    'event: context\ndata: {"context_bundle":{"project":{"id":1,"title":"","genre":"","main_theme":"","tone":"","premise":""},"world_overview":null,"characters":[],"relationships":[],"faction_lore":[],"location_lore":[],"recent_chapter_summaries":[]}}\n\n',
    'event: token\ndata: {"text":"夜色压在屋脊上"}\n\n',
    'event: token\ndata: {"text":"，残月酒馆的灯还亮着。"}\n\n',
    'event: done\ndata: {"generation_log_id":1,"input_tokens":10,"output_tokens":12,"stop_reason":"end_turn"}\n\n',
  ].join("");
  await page.route(`**/api/chapters/${ch.id}/generate`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody,
    });
  });

  await page.goto(`/projects/${projectId}/chapters/${ch.id}`);

  // Open bottom panel
  await page.click("text=⚡ 生成（展开）");

  // Fill form
  await page.fill("textarea", "主角推开酒馆的门");
  await page.click(`text=测试人物`);

  // Submit
  await page.click("button:has-text('✨ 生成')");

  // Wait for done event
  await expect(page.locator("text=✓ 完成")).toBeVisible({ timeout: 5_000 });

  // Accept
  await page.click("button:has-text('✓ 接受并插入')");

  // Verify editor has content
  await expect(page.locator(".ProseMirror")).toContainText("夜色压在屋脊上");
});
```

- [ ] **Step 16.4: Create `web/tests/e2e/invalid-context.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("invalid context shows toast", async ({ page }) => {
  await page.goto("/");
  await page.click("text=新建项目");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  const projectId = new URL(page.url()).pathname.split("/")[2];

  const ch = await fetch(`http://127.0.0.1:8005/api/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), order_index: 1, title: "x" }),
  }).then((r) => r.json());

  // Real character in another project
  const otherProject = await fetch(`http://127.0.0.1:8005/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Other" }),
  }).then((r) => r.json());
  const otherChar = await fetch(`http://127.0.0.1:8005/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: otherProject.id, name: "外项目人物" }),
  }).then((r) => r.json());

  await page.goto(`/projects/${projectId}/chapters/${ch.id}`);
  await page.click("text=⚡ 生成（展开）");
  await page.fill("textarea", "beat");
  // The other-project character won't appear in the chip list (filter by project),
  // so we directly POST via fetch to verify backend rejects
  const r = await fetch(`http://127.0.0.1:8005/api/chapters/${ch.id}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      beat_text: "x",
      involved_character_ids: [otherChar.id],
    }),
  });
  expect(r.status).toBe(422);
  const body = await r.json();
  expect(body.detail.error).toBe("invalid_context");
  expect(body.detail.invalid_character_ids).toContain(otherChar.id);
});
```

- [ ] **Step 16.5: Run E2E tests**

```bash
cd /Users/bugx/novelAI/web && npm run test:e2e
```

Expected: 3 PASS. If `project-chapter.spec.ts` times out on first run, ensure backend has fresh DB (`rm ../data/novelai.db`) and re-run.

- [ ] **Step 16.6: Run full unit + component test suite**

```bash
npm test
```

Expected: All tests pass.

- [ ] **Step 16.7: Run full backend regression**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate && pytest -v
```

Expected: All M1 + M2a + M2b backend tests pass.

- [ ] **Step 16.8: Commit**

```bash
cd /Users/bugx/novelAI/web
git add playwright.config.ts tests/e2e/
git commit -m "test(m2b): playwright e2e (project-chapter, generate-accept, invalid-context)"
```

- [ ] **Step 16.9: Update README**

In `/Users/bugx/novelAI/README.md`, replace the existing "## 启动" section with:

```markdown
## 启动

### 后端（端口 8005）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8005
```

访问 http://127.0.0.1:8005/docs 查看 OpenAPI 文档。

### 前端（端口 3300）

```bash
cd web
npm install
npm run dev
```

访问 http://localhost:3300 使用前端编辑器。

## 测试

```bash
# 后端
pytest

# 前端单元 + 组件
cd web && npm test

# 前端 E2E（需要后端在 8005 运行）
cd web && npm run test:e2e
```
```

- [ ] **Step 16.10: Commit README + final**

```bash
cd /Users/bugx/novelAI
git add README.md
git commit -m "docs(m2b): update README with frontend run/test instructions"
```

---

## Self-Review

### Spec coverage

| Spec § | Coverage |
|---|---|
| §1.3 关键决策（端口、TipTap v3、Client Component、Markdown 存储、persist、project_id） | Task 1 + 2 + 6 + 10 |
| §2 文件结构 | All files mapped (Tasks 1–16) |
| §3.1 lib/api.ts | Task 4 |
| §3.2 lib/sse.ts | Task 5 |
| §3.3 Zustand store + persist + partialize | Task 6 |
| §3.4 TanStack Query hooks | Task 7 |
| §3.5 useGenerate hook | Task 13 |
| §3.6 关键数据流决策 | Tasks 4–7, 13 |
| §3bis 后端 chapters schema 改动 | Task 1 (Step 1.3–1.5) |
| §3bis 后端 logs project_id 参数 | Task 1 (Step 1.6–1.9) |
| §3bis 后端 writer 写回 | Task 1 (Step 1.10–1.13) |
| §3bis CORS | Task 1 (Step 1.14–1.16) |
| §4 路由结构（全 Client Component） | Tasks 8, 9, 11, 14, 15 |
| §5 TipTap v3 + Markdown | Task 10 |
| §5 保存策略（防抖 500ms + onBlur） | Task 10 (useChapterAutosave) |
| §5 接受生成内容（insertContent） | Task 13 (StreamView.handleAccept) |
| §6 三栏布局 | Tasks 8, 11 (ChapterWorkspaceGrid) |
| §6 ActivityBar 5 图标 | Task 8 |
| §6 ContextPanel 默认集 + 当前参数 | Tasks 6 (store) + 12 |
| §6 BottomPanel 可折叠 + 高度持久化 | Tasks 6 + 13 |
| §7 生成流程生命周期 | Task 13 |
| §7 GenerateForm + StreamView | Task 13 |
| §8.1 项目列表 | Task 9 |
| §8.2 章节列表 + ChapterItem | Tasks 9, 11 |
| §8.3 人物库 + 表单 | Task 14 |
| §8.4 设定库 + 子 tab + 地点树 | Task 14 |
| §8.5 历史页（project_id 一次拉取） | Task 15 |
| §8.6 全局搜索 | Task 15 |
| §9 CORS + 环境配置 | Task 1 + Task 2 (.env.local) |
| §10 测试策略（vitest + playwright） | Tasks 4–7, 13, 16 |
| §11 验收清单 1–17 | Tasks 1, 9, 10, 13, 14, 15, 16 |

All spec sections covered.

### Placeholder scan

Searched plan for: TBD, TODO, "implement later", "add appropriate". None found in actual step content. One acknowledgment ("if API differs, check official docs") in Task 10 Step 10.1 — kept as legitimate forward-reference since TipTap v3 is recent.

### Type consistency

- `Chapter.last_involved_character_ids: number[]` and `last_location_id: number | null` — consistent across:
  - Task 1 (Pydantic schema)
  - Task 3 (TS type)
  - Task 6 (store.hydrateFromChapter signature)
  - Task 12 (ContextPanel consumer)
- `useGenerateParams` API (`setParams`, `hydrateFromChapter`, `reset`) — consistent across:
  - Task 6 (definition)
  - Task 12 (ContextPanel consumer)
  - Task 13 (GenerateForm consumer)
- `useGenerate` return shape (`events`, `generatedText`, `status`, `error`, `start`, `cancel`, `reset`) — consistent across:
  - Task 13 definition
  - Task 13 GenerateForm consumer
  - Task 13 StreamView consumer
  - Task 13 StreamView test mocks
- `api.listGenerationLogs` accepts `{ chapter_id?, project_id?, limit?, offset? }` — consistent across:
  - Task 4 (api.ts)
  - Task 7 (queries.ts `useGenerationLogsByChapter` / `useGenerationLogsByProject`)
- `WorkspaceShell` only renders ActivityBar + content area; pages render `ChapterWorkspaceGrid` for the three-column layout — consistent across Tasks 8, 11, 14, 15.

No inconsistencies.

### Known caveats

1. **TipTap v3 API**: `editor.storage.markdown.getMarkdown()` is the expected name based on v2 community package; v3 official package may differ. Task 10 Step 10.1 flags this — implementation engineer should verify on first run and adjust if needed.
2. **Playwright SSE mocking**: `route.fulfill()` with `body: string` works for short streams; for long-running real LLM streams in tests, use `body: ReadableStream`. Plan uses string for determinism.
3. **Next.js 15 `useParams()` in Client Components**: returns plain object (not Promise). Plan uses synchronous destructuring — verify at runtime.
4. **E2E tests assume fresh DB**: if existing data interferes, drop `data/novelai.db` before running.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-m2b-editor-frontend.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
