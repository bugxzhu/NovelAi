# M1 — 地基（Foundation）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起 NovelAI 的后端地基——Python 项目结构、FastAPI 应用、SQLite 数据库（含 M1 所需 5 张表）、LLM 抽象层（含 Claude provider）和基础 CRUD。完成此计划后系统能创建项目/世界观/lore/人物/章节并调用 LLM。

**Architecture:** FastAPI 同步 SQLAlchemy 2.0 + SQLite（WAL 模式）；CRUD 通过依赖注入的 DB session；LLM 抽象层定义 `LLMProvider` 协议，Claude provider 是首个实现，`ModelRouter` 按任务路由。

**Tech Stack:** Python 3.11+、FastAPI、Uvicorn、SQLAlchemy 2.0（sync）、Pydantic v2、pydantic-settings、anthropic SDK、pytest、httpx、ruff。

**Reference spec:** `docs/superpowers/specs/2026-06-15-novel-ai-design.md`

---

## Scope Check

本计划只覆盖 M1 的 5 张表（`projects`、`world_overview`、`lore_entries`、`characters`、`chapters`）。其他表（`character_states`、`relationships`、`plot_lines`、`events`、`pending_updates`、`vec_chunks`）属于后续里程碑，遵循 YAGNI 不在本计划内建表。

---

## File Structure

```
novelAI/
├── pyproject.toml                  # 依赖与项目元数据
├── .env.example                    # 环境变量模板
├── .gitignore                      # 忽略 data/、.env、__pycache__ 等
├── README.md                       # 启动说明
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI 应用入口
│   ├── config.py                   # Settings（pydantic-settings）
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # get_db 依赖
│   │   ├── health.py               # /api/health
│   │   ├── projects.py             # /api/projects CRUD
│   │   ├── world.py                # /api/projects/{id}/world-overview
│   │   ├── lore.py                 # /api/lore CRUD
│   │   ├── characters.py           # /api/characters CRUD
│   │   ├── chapters.py             # /api/chapters CRUD
│   │   └── llm.py                  # /api/llm/ping
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── base.py                 # SQLAlchemy DeclarativeBase
│   │   ├── session.py              # engine + SessionLocal + init_db
│   │   └── schema.py               # ORM 模型
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                 # LLMProvider 协议 + 数据类
│   │   ├── router.py               # ModelRouter
│   │   └── providers/
│   │       ├── __init__.py
│   │       └── claude.py           # ClaudeProvider
│   └── models/                     # Pydantic schemas
│       ├── __init__.py
│       ├── common.py
│       ├── project.py
│       ├── world.py
│       ├── lore.py
│       ├── character.py
│       └── chapter.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # fixtures: client, db
│   ├── test_health.py
│   ├── test_projects.py
│   ├── test_world.py
│   ├── test_lore.py
│   ├── test_characters.py
│   ├── test_chapters.py
│   └── test_llm.py
└── data/                           # gitignored, SQLite 文件
    └── .gitkeep
```

**职责边界：**
- `app/memory/` 只管 ORM 与数据库会话
- `app/llm/` 只管 LLM 调用，不知道业务
- `app/models/` Pydantic 请求/响应 schema（命名约定：`XxxCreate` / `XxxUpdate` / `XxxRead`）
- `app/api/` 路由层，依赖注入 DB session，调用 ORM，返回 Pydantic
- Agent 编排层（`app/agents/`）在 M2 加入，M1 不创建

---

## Task 1: 项目初始化

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `app/__init__.py`（空）
- Create: `tests/__init__.py`（空）
- Create: `data/.gitkeep`

- [ ] **Step 1.1: 初始化 git 仓库**

```bash
cd /Users/bugx/novelAI
git init
git config user.name "$(git config user.name || echo 'bugx')"
git config user.email "$(git config user.email || echo 'bugx@local')"
```

- [ ] **Step 1.2: 写 `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.ruff_cache/

# Env / data
.env
data/*.db
data/*.db-shm
data/*.db-wal

# OS
.DS_Store
```

- [ ] **Step 1.3: 写 `pyproject.toml`**

```toml
[project]
name = "novelai"
version = "0.1.0"
description = "AI-assisted novel writing tool with structured memory"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy>=2.0",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "anthropic>=0.40",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 1.4: 写 `.env.example`**

```bash
# 数据库路径（相对项目根目录）
NOVELAI_DB_PATH=./data/novelai.db

# LLM Provider 配置
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 服务端口
NOVELAI_HOST=127.0.0.1
NOVELAI_PORT=8000
```

- [ ] **Step 1.5: 写 `README.md`**

```markdown
# NovelAI

AI 辅助小说写作工具（本地优先 Web 应用）。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

## 测试

```bash
pytest
```
```

- [ ] **Step 1.6: 创建空包文件**

```bash
mkdir -p app tests data
touch app/__init__.py tests/__init__.py data/.gitkeep
```

- [ ] **Step 1.7: 安装依赖并验证**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import fastapi, sqlalchemy, anthropic, pytest; print('ok')"
```

Expected: `ok`

- [ ] **Step 1.8: Commit**

```bash
git add .
git commit -m "chore: project init with pyproject, gitignore, env template"
```

---

## Task 2: FastAPI 应用骨架 + Health 端点

**Files:**
- Create: `app/config.py`
- Create: `app/main.py`
- Create: `app/api/__init__.py`
- Create: `app/api/health.py`
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`

- [ ] **Step 2.1: 写 `app/config.py`**

```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELAI_", env_file=".env", extra="ignore")

    db_path: Path = Path("./data/novelai.db")
    host: str = "127.0.0.1"
    port: int = 8000
    anthropic_api_key: str = ""  # 由 ANTHROPIC_API_KEY 环境变量读取，见下

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
```

注意：`ANTHROPIC_API_KEY` 没有 `NOVELAI_` 前缀，需在 `Settings` 中显式声明字段或用 `os.environ` 读取。为简单起见，Anthropic SDK 会自动读 `ANTHROPIC_API_KEY` 环境变量，无需在 Settings 里管。

- [ ] **Step 2.2: 写失败测试 `tests/test_health.py`**

```python
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2.3: 写 `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)
```

- [ ] **Step 2.4: 运行测试验证失败**

Run: `pytest tests/test_health.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.main'` 或路由 404）

- [ ] **Step 2.5: 写 `app/api/health.py`**

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 2.6: 写 `app/api/__init__.py`**

```python
```

- [ ] **Step 2.7: 写 `app/main.py`**

```python
from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0")
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 2.8: 运行测试验证通过**

Run: `pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 2.9: 手动启动验证**

```bash
source .venv/bin/activate
uvicorn app.main:app &
sleep 1
curl -s http://127.0.0.1:8000/api/health
kill %1
```

Expected: `{"status":"ok"}`

- [ ] **Step 2.10: Commit**

```bash
git add app/ tests/
git commit -m "feat: fastapi skeleton with health endpoint"
```

---

## Task 3: 数据库基础（engine / session / Base）

**Files:**
- Create: `app/memory/__init__.py`
- Create: `app/memory/base.py`
- Create: `app/memory/session.py`
- Create: `tests/test_db.py`

- [ ] **Step 3.1: 写失败测试 `tests/test_db.py`**

```python
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.memory.session import SessionLocal, init_db


def test_init_db_creates_file(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    init_db()
    assert db_file.exists()


def test_session_can_query_sqlite_version():
    init_db()
    with SessionLocal() as session:
        version = session.execute(text("SELECT sqlite_version()")).scalar()
        assert version is not None
```

- [ ] **Step 3.2: 运行测试验证失败**

Run: `pytest tests/test_db.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.memory.session'`）

- [ ] **Step 3.3: 写 `app/memory/__init__.py`**

```python
```

- [ ] **Step 3.4: 写 `app/memory/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 3.5: 写 `app/memory/session.py`**

```python
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.memory.base import Base


def _build_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _build_engine(settings.db_path)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    # 触发所有模型导入，确保 Base.metadata 已注册所有表
    import app.memory.schema  # noqa: F401
    Base.metadata.create_all(engine)
```

- [ ] **Step 3.6: 运行测试验证失败**

Run: `pytest tests/test_db.py -v`
Expected: FAIL（`init_db` 内 `import app.memory.schema` 失败——schema 还没写，预期）

- [ ] **Step 3.7: Commit（中间状态）**

```bash
git add app/memory/ tests/test_db.py
git commit -m "feat: db engine, session, base (schema import pending)"
```

---

## Task 4: SQLAlchemy 模型（M1 的 5 张表）

**Files:**
- Create: `app/memory/schema.py`
- Modify: `tests/test_db.py`（追加模型存在性测试）

- [ ] **Step 4.1: 在 `tests/test_db.py` 追加模型测试**

```python
def test_init_db_creates_m1_tables(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    init_db()
    from app.memory.base import Base
    expected = {"projects", "world_overview", "lore_entries", "characters", "chapters"}
    actual = set(Base.metadata.tables.keys())
    assert expected.issubset(actual), f"missing tables: {expected - actual}"
```

- [ ] **Step 4.2: 运行测试验证失败**

Run: `pytest tests/test_db.py::test_init_db_creates_m1_tables -v`
Expected: FAIL（`app.memory.schema` 不存在）

- [ ] **Step 4.3: 写 `app/memory/schema.py`**

```python
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.memory.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="")
    premise: Mapped[str] = mapped_column(Text, default="")
    main_theme: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    world_overview: Mapped["WorldOverview | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    lore_entries: Mapped[list["LoreEntry"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class WorldOverview(Base):
    __tablename__ = "world_overview"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    setting_era: Mapped[str] = mapped_column(Text, default="")
    geography_summary: Mapped[str] = mapped_column(Text, default="")
    history_summary: Mapped[str] = mapped_column(Text, default="")
    culture_summary: Mapped[str] = mapped_column(Text, default="")
    power_system: Mapped[str] = mapped_column(Text, default="")
    rules_and_taboos: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="world_overview")


class LoreEntry(Base):
    __tablename__ = "lore_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("lore_entries.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="lore_entries")
    parent: Mapped["LoreEntry | None"] = relationship(
        "LoreEntry", remote_side=[id], backref="children"
    )


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="")
    personality: Mapped[dict] = mapped_column(JSON, default=dict)
    speech_style: Mapped[str] = mapped_column(Text, default="")
    background: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[str] = mapped_column(Text, default="")
    current_state: Mapped[str] = mapped_column(Text, default="")
    affiliations: Mapped[list] = mapped_column(JSON, default=list)  # lore_entries.id 数组
    known_locations: Mapped[list] = mapped_column(JSON, default=list)  # lore_entries.id 数组
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="characters")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    outline: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    plot_line_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="chapters")
```

- [ ] **Step 4.4: 运行测试验证通过**

Run: `pytest tests/test_db.py -v`
Expected: PASS（两个测试都过）

- [ ] **Step 4.5: Commit**

```bash
git add app/memory/schema.py tests/test_db.py
git commit -m "feat: m1 orm models (projects, world_overview, lore_entries, characters, chapters)"
```

---

## Task 5: Pydantic Schemas（请求/响应模型）

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/common.py`
- Create: `app/models/project.py`
- Create: `app/models/world.py`
- Create: `app/models/lore.py`
- Create: `app/models/character.py`
- Create: `app/models/chapter.py`
- Create: `tests/test_models.py`

- [ ] **Step 5.1: 写失败测试 `tests/test_models.py`**

```python
from datetime import datetime
from app.models.project import ProjectCreate, ProjectRead


def test_project_create_minimal():
    p = ProjectCreate(title="My Novel")
    assert p.title == "My Novel"
    assert p.genre == ""
    assert p.premise == ""


def test_project_read_includes_id_and_timestamps():
    p = ProjectRead(
        id=1, title="X", genre="", premise="", main_theme="", tone="",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    assert p.id == 1
```

- [ ] **Step 5.2: 运行测试验证失败**

Run: `pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 5.3: 写 `app/models/__init__.py`**

```python
```

- [ ] **Step 5.4: 写 `app/models/common.py`**

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 5.5: 写 `app/models/project.py`**

```python
from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class ProjectBase(BaseModel):
    title: str
    genre: str = ""
    premise: str = ""
    main_theme: str = ""
    tone: str = ""


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    premise: str | None = None
    main_theme: str | None = None
    tone: str | None = None


class ProjectRead(ProjectBase, ORMBase, TimestampMixin):
    id: int
```

- [ ] **Step 5.6: 写 `app/models/world.py`**

```python
from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class WorldOverviewBase(BaseModel):
    setting_era: str = ""
    geography_summary: str = ""
    history_summary: str = ""
    culture_summary: str = ""
    power_system: str = ""
    rules_and_taboos: str = ""


class WorldOverviewUpsert(WorldOverviewBase):
    pass


class WorldOverviewRead(WorldOverviewBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
```

- [ ] **Step 5.7: 写 `app/models/lore.py`**

```python
from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class LoreEntryBase(BaseModel):
    type: str
    name: str
    title: str = ""
    description: str = ""
    attributes: dict = {}
    parent_id: int | None = None
    tags: list[str] = []


class LoreEntryCreate(LoreEntryBase):
    project_id: int


class LoreEntryUpdate(BaseModel):
    type: str | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None
    attributes: dict | None = None
    parent_id: int | None = None
    tags: list[str] | None = None


class LoreEntryRead(LoreEntryBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
```

- [ ] **Step 5.8: 写 `app/models/character.py`**

```python
from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class CharacterBase(BaseModel):
    name: str
    role: str = ""
    personality: dict = {}
    speech_style: str = ""
    background: str = ""
    motivation: str = ""
    appearance: str = ""
    current_state: str = ""
    affiliations: list[int] = []
    known_locations: list[int] = []


class CharacterCreate(CharacterBase):
    project_id: int


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    personality: dict | None = None
    speech_style: str | None = None
    background: str | None = None
    motivation: str | None = None
    appearance: str | None = None
    current_state: str | None = None
    affiliations: list[int] | None = None
    known_locations: list[int] | None = None


class CharacterRead(CharacterBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
```

- [ ] **Step 5.9: 写 `app/models/chapter.py`**

```python
from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class ChapterBase(BaseModel):
    order_index: int = 0
    title: str = ""
    outline: str = ""
    content: str = ""
    status: str = "draft"
    plot_line_ids: list[int] = []
    summary: str = ""
    content_hash: str = ""


class ChapterCreate(ChapterBase):
    project_id: int


class ChapterUpdate(BaseModel):
    order_index: int | None = None
    title: str | None = None
    outline: str | None = None
    content: str | None = None
    status: str | None = None
    plot_line_ids: list[int] | None = None
    summary: str | None = None
    content_hash: str | None = None


class ChapterRead(ChapterBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
```

- [ ] **Step 5.10: 运行测试验证通过**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5.11: Commit**

```bash
git add app/models/ tests/test_models.py
git commit -m "feat: pydantic schemas for m1 entities"
```

---

## Task 6: DB 依赖注入 + init_db 在启动时调用

**Files:**
- Create: `app/api/deps.py`
- Modify: `app/main.py`（启动时调用 init_db）
- Modify: `tests/conftest.py`（追加 db fixture，使用 tmp 数据库）

- [ ] **Step 6.1: 写 `app/api/deps.py`**

```python
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.memory.session import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6.2: 修改 `app/main.py` 启动时建表**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.memory.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 6.3: 修改 `tests/conftest.py`，使用 tmp 数据库**

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.settings.db_path", db_file)
    # 重新构建 engine 与 SessionLocal 绑定到 tmp_path
    from app.memory import session as session_module
    from app.memory.session import _build_engine
    from sqlalchemy.orm import sessionmaker
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    monkeypatch.setattr("app.api.deps.SessionLocal", new_session)

    from app.main import app
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 6.4: 运行所有测试验证未破坏**

Run: `pytest -v`
Expected: 之前所有测试仍 PASS

- [ ] **Step 6.5: Commit**

```bash
git add app/api/deps.py app/main.py tests/conftest.py
git commit -m "feat: db dependency injection + lifespan init_db"
```

---

## Task 7: Projects CRUD

**Files:**
- Create: `app/api/projects.py`
- Modify: `app/main.py`（注册 router）
- Create: `tests/test_projects.py`

- [ ] **Step 7.1: 写失败测试 `tests/test_projects.py`**

```python
def test_create_project(client):
    r = client.post("/api/projects", json={"title": "My Novel", "genre": "fantasy"})
    assert r.status_code == 201
    data = r.json()
    assert data["id"] > 0
    assert data["title"] == "My Novel"
    assert data["genre"] == "fantasy"


def test_list_projects(client):
    client.post("/api/projects", json={"title": "A"})
    client.post("/api/projects", json={"title": "B"})
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_project(client):
    r = client.post("/api/projects", json={"title": "X"})
    pid = r.json()["id"]
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["title"] == "X"


def test_get_project_not_found(client):
    r = client.get("/api/projects/9999")
    assert r.status_code == 404


def test_update_project(client):
    r = client.post("/api/projects", json={"title": "Old"})
    pid = r.json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"


def test_delete_project(client):
    r = client.post("/api/projects", json={"title": "X"})
    pid = r.json()["id"]
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
```

- [ ] **Step 7.2: 运行测试验证失败**

Run: `pytest tests/test_projects.py -v`
Expected: FAIL（404 / 路由不存在）

- [ ] **Step 7.3: 写 `app/api/projects.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Project
from app.models.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    obj = Project(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return list(db.scalars(select(Project).order_by(Project.id)))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    obj = db.get(Project, project_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="project not found")
    return obj


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    obj = db.get(Project, project_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="project not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    obj = db.get(Project, project_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="project not found")
    db.delete(obj)
    db.commit()
```

- [ ] **Step 7.4: 在 `app/main.py` 注册 router**

修改 `create_app`：

```python
from app.api import health, projects


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    return app
```

- [ ] **Step 7.5: 运行测试验证通过**

Run: `pytest tests/test_projects.py -v`
Expected: 全部 PASS

- [ ] **Step 7.6: Commit**

```bash
git add app/api/projects.py app/main.py tests/test_projects.py
git commit -m "feat: projects crud endpoints"
```

---

## Task 8: World Overview CRUD

**Files:**
- Create: `app/api/world.py`
- Modify: `app/main.py`
- Create: `tests/test_world.py`

- [ ] **Step 8.1: 写失败测试 `tests/test_world.py`**

```python
def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_upsert_world_overview_creates(client):
    pid = _make_project(client)
    r = client.put(
        f"/api/projects/{pid}/world-overview",
        json={"setting_era": "中古", "power_system": "魔法"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert data["setting_era"] == "中古"
    assert data["power_system"] == "魔法"


def test_upsert_world_overview_updates(client):
    pid = _make_project(client)
    client.put(f"/api/projects/{pid}/world-overview", json={"setting_era": "A"})
    r = client.put(f"/api/projects/{pid}/world-overview", json={"setting_era": "B"})
    assert r.status_code == 200
    assert r.json()["setting_era"] == "B"


def test_get_world_overview(client):
    pid = _make_project(client)
    client.put(f"/api/projects/{pid}/world-overview", json={"geography_summary": "山海之间"})
    r = client.get(f"/api/projects/{pid}/world-overview")
    assert r.status_code == 200
    assert r.json()["geography_summary"] == "山海之间"


def test_get_world_overview_not_found(client):
    pid = _make_project(client)
    r = client.get(f"/api/projects/{pid}/world-overview")
    assert r.status_code == 404


def test_get_world_overview_project_not_found(client):
    r = client.get("/api/projects/9999/world-overview")
    assert r.status_code == 404
```

- [ ] **Step 8.2: 运行测试验证失败**

Run: `pytest tests/test_world.py -v`
Expected: FAIL

- [ ] **Step 8.3: 写 `app/api/world.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Project, WorldOverview
from app.models.world import WorldOverviewRead, WorldOverviewUpsert

router = APIRouter()


def _get_project_or_404(db: Session, project_id: int) -> Project:
    obj = db.get(Project, project_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="project not found")
    return obj


@router.put("/{project_id}/world-overview", response_model=WorldOverviewRead)
def upsert_world_overview(
    project_id: int, payload: WorldOverviewUpsert, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    obj = db.scalar(select(WorldOverview).where(WorldOverview.project_id == project_id))
    if obj is None:
        obj = WorldOverview(project_id=project_id, **payload.model_dump())
        db.add(obj)
    else:
        for field, value in payload.model_dump().items():
            setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{project_id}/world-overview", response_model=WorldOverviewRead)
def get_world_overview(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    obj = db.scalar(select(WorldOverview).where(WorldOverview.project_id == project_id))
    if obj is None:
        raise HTTPException(status_code=404, detail="world overview not set")
    return obj
```

- [ ] **Step 8.4: 在 `app/main.py` 注册 router**

修改 import 与 `create_app`：

```python
from app.api import health, projects, world


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(world.router, prefix="/api/projects", tags=["world"])
    return app
```

- [ ] **Step 8.5: 运行测试验证通过**

Run: `pytest tests/test_world.py -v`
Expected: 全部 PASS

- [ ] **Step 8.6: Commit**

```bash
git add app/api/world.py app/main.py tests/test_world.py
git commit -m "feat: world overview upsert/get endpoints"
```

---

## Task 9: Lore Entries CRUD

**Files:**
- Create: `app/api/lore.py`
- Modify: `app/main.py`
- Create: `tests/test_lore.py`

- [ ] **Step 9.1: 写失败测试 `tests/test_lore.py`**

```python
def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_lore_entry(client):
    pid = _make_project(client)
    r = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "青石镇", "tags": ["北方"]},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "青石镇"
    assert r.json()["tags"] == ["北方"]


def test_list_lore_by_project(client):
    pid = _make_project(client)
    client.post("/api/lore", json={"project_id": pid, "type": "location", "name": "A"})
    client.post("/api/lore", json={"project_id": pid, "type": "faction", "name": "B"})
    # 另一个项目
    pid2 = _make_project(client)
    client.post("/api/lore", json={"project_id": pid2, "type": "location", "name": "C"})
    r = client.get(f"/api/lore?project_id={pid}")
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert names == {"A", "B"}


def test_list_lore_filter_by_type(client):
    pid = _make_project(client)
    client.post("/api/lore", json={"project_id": pid, "type": "location", "name": "A"})
    client.post("/api/lore", json={"project_id": pid, "type": "faction", "name": "B"})
    r = client.get(f"/api/lore?project_id={pid}&type=faction")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "B"


def test_lore_parent_hierarchy(client):
    pid = _make_project(client)
    parent = client.post(
        "/api/lore", json={"project_id": pid, "type": "location", "name": "王国"}
    ).json()["id"]
    child = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王城", "parent_id": parent},
    ).json()
    assert child["parent_id"] == parent


def test_update_lore_entry(client):
    pid = _make_project(client)
    lid = client.post(
        "/api/lore", json={"project_id": pid, "type": "item", "name": "Old"}
    ).json()["id"]
    r = client.patch(f"/api/lore/{lid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


def test_delete_lore_entry(client):
    pid = _make_project(client)
    lid = client.post(
        "/api/lore", json={"project_id": pid, "type": "item", "name": "X"}
    ).json()["id"]
    r = client.delete(f"/api/lore/{lid}")
    assert r.status_code == 204
```

- [ ] **Step 9.2: 运行测试验证失败**

Run: `pytest tests/test_lore.py -v`
Expected: FAIL

- [ ] **Step 9.3: 写 `app/api/lore.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import LoreEntry
from app.models.lore import LoreEntryCreate, LoreEntryRead, LoreEntryUpdate

router = APIRouter()


@router.post("", response_model=LoreEntryRead, status_code=status.HTTP_201_CREATED)
def create_lore(payload: LoreEntryCreate, db: Session = Depends(get_db)):
    obj = LoreEntry(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[LoreEntryRead])
def list_lore(
    project_id: int = Query(...),
    type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(LoreEntry).where(LoreEntry.project_id == project_id)
    if type is not None:
        stmt = stmt.where(LoreEntry.type == type)
    stmt = stmt.order_by(LoreEntry.id)
    return list(db.scalars(stmt))


@router.get("/{lore_id}", response_model=LoreEntryRead)
def get_lore(lore_id: int, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    return obj


@router.patch("/{lore_id}", response_model=LoreEntryRead)
def update_lore(lore_id: int, payload: LoreEntryUpdate, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{lore_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lore(lore_id: int, db: Session = Depends(get_db)):
    obj = db.get(LoreEntry, lore_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="lore entry not found")
    db.delete(obj)
    db.commit()
```

- [ ] **Step 9.4: 在 `app/main.py` 注册 router**

修改 import：

```python
from app.api import health, projects, world, lore
```

在 `create_app` 末尾追加：

```python
    app.include_router(lore.router, prefix="/api/lore", tags=["lore"])
```

- [ ] **Step 9.5: 运行测试验证通过**

Run: `pytest tests/test_lore.py -v`
Expected: 全部 PASS

- [ ] **Step 9.6: Commit**

```bash
git add app/api/lore.py app/main.py tests/test_lore.py
git commit -m "feat: lore entries crud with project and type filters"
```

---

## Task 10: Characters CRUD

**Files:**
- Create: `app/api/characters.py`
- Modify: `app/main.py`
- Create: `tests/test_characters.py`

- [ ] **Step 10.1: 写失败测试 `tests/test_characters.py`**

```python
def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_character(client):
    pid = _make_project(client)
    r = client.post(
        "/api/characters",
        json={
            "project_id": pid,
            "name": "李雷",
            "role": "主角",
            "personality": {"mbti": "INTJ", "traits": ["冷静", "固执"]},
            "speech_style": "短句，常引古文",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "李雷"
    assert data["personality"]["mbti"] == "INTJ"
    assert data["speech_style"] == "短句，常引古文"


def test_list_characters_by_project(client):
    pid = _make_project(client)
    client.post("/api/characters", json={"project_id": pid, "name": "A"})
    client.post("/api/characters", json={"project_id": pid, "name": "B"})
    pid2 = _make_project(client)
    client.post("/api/characters", json={"project_id": pid2, "name": "C"})
    r = client.get(f"/api/characters?project_id={pid}")
    assert len(r.json()) == 2


def test_get_character_not_found(client):
    r = client.get("/api/characters/9999")
    assert r.status_code == 404


def test_update_character_partial(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/characters", json={"project_id": pid, "name": "Old", "role": "配角"}
    ).json()["id"]
    r = client.patch(f"/api/characters/{cid}", json={"role": "主角"})
    assert r.status_code == 200
    assert r.json()["role"] == "主角"
    assert r.json()["name"] == "Old"


def test_delete_character(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/characters", json={"project_id": pid, "name": "X"}
    ).json()["id"]
    assert client.delete(f"/api/characters/{cid}").status_code == 204
```

- [ ] **Step 10.2: 运行测试验证失败**

Run: `pytest tests/test_characters.py -v`
Expected: FAIL

- [ ] **Step 10.3: 写 `app/api/characters.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Character
from app.models.character import CharacterCreate, CharacterRead, CharacterUpdate

router = APIRouter()


@router.post("", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
def create_character(payload: CharacterCreate, db: Session = Depends(get_db)):
    obj = Character(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[CharacterRead])
def list_characters(project_id: int = Query(...), db: Session = Depends(get_db)):
    stmt = select(Character).where(Character.project_id == project_id).order_by(Character.id)
    return list(db.scalars(stmt))


@router.get("/{character_id}", response_model=CharacterRead)
def get_character(character_id: int, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    return obj


@router.patch("/{character_id}", response_model=CharacterRead)
def update_character(character_id: int, payload: CharacterUpdate, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: int, db: Session = Depends(get_db)):
    obj = db.get(Character, character_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="character not found")
    db.delete(obj)
    db.commit()
```

- [ ] **Step 10.4: 在 `app/main.py` 注册 router**

修改 import：

```python
from app.api import health, projects, world, lore, characters
```

在 `create_app` 末尾追加：

```python
    app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
```

- [ ] **Step 10.5: 运行测试验证通过**

Run: `pytest tests/test_characters.py -v`
Expected: 全部 PASS

- [ ] **Step 10.6: Commit**

```bash
git add app/api/characters.py app/main.py tests/test_characters.py
git commit -m "feat: characters crud endpoints"
```

---

## Task 11: Chapters CRUD

**Files:**
- Create: `app/api/chapters.py`
- Modify: `app/main.py`
- Create: `tests/test_chapters.py`

- [ ] **Step 11.1: 写失败测试 `tests/test_chapters.py`**

```python
def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_chapter(client):
    pid = _make_project(client)
    r = client.post(
        "/api/chapters",
        json={
            "project_id": pid,
            "order_index": 1,
            "title": "第一章",
            "outline": "主角离家",
        },
    )
    assert r.status_code == 201
    assert r.json()["title"] == "第一章"
    assert r.json()["status"] == "draft"


def test_list_chapters_ordered(client):
    pid = _make_project(client)
    client.post("/api/chapters", json={"project_id": pid, "order_index": 2, "title": "B"})
    client.post("/api/chapters", json={"project_id": pid, "order_index": 1, "title": "A"})
    r = client.get(f"/api/chapters?project_id={pid}")
    assert [c["title"] for c in r.json()] == ["A", "B"]


def test_update_chapter_content(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/chapters", json={"project_id": pid, "order_index": 1, "title": "T"}
    ).json()["id"]
    r = client.patch(
        f"/api/chapters/{cid}",
        json={"content": "主角推开门，看见...", "status": "writing"},
    )
    assert r.status_code == 200
    assert r.json()["content"].startswith("主角推开门")
    assert r.json()["status"] == "writing"


def test_delete_chapter(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/chapters", json={"project_id": pid, "order_index": 1, "title": "T"}
    ).json()["id"]
    assert client.delete(f"/api/chapters/{cid}").status_code == 204
```

- [ ] **Step 11.2: 运行测试验证失败**

Run: `pytest tests/test_chapters.py -v`
Expected: FAIL

- [ ] **Step 11.3: 写 `app/api/chapters.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Chapter
from app.models.chapter import ChapterCreate, ChapterRead, ChapterUpdate

router = APIRouter()


@router.post("", response_model=ChapterRead, status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db)):
    obj = Chapter(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=list[ChapterRead])
def list_chapters(project_id: int = Query(...), db: Session = Depends(get_db)):
    stmt = (
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order_index, Chapter.id)
    )
    return list(db.scalars(stmt))


@router.get("/{chapter_id}", response_model=ChapterRead)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    return obj


@router.patch("/{chapter_id}", response_model=ChapterRead)
def update_chapter(chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: int, db: Session = Depends(get_db)):
    obj = db.get(Chapter, chapter_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    db.delete(obj)
    db.commit()
```

- [ ] **Step 11.4: 在 `app/main.py` 注册 router**

修改 import：

```python
from app.api import health, projects, world, lore, characters, chapters
```

在 `create_app` 末尾追加：

```python
    app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
```

- [ ] **Step 11.5: 运行测试验证通过**

Run: `pytest tests/test_chapters.py -v`
Expected: 全部 PASS

- [ ] **Step 11.6: Commit**

```bash
git add app/api/chapters.py app/main.py tests/test_chapters.py
git commit -m "feat: chapters crud endpoints"
```

---

## Task 12: LLM 抽象层（base + Claude provider + router）

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/base.py`
- Create: `app/llm/providers/__init__.py`
- Create: `app/llm/providers/claude.py`
- Create: `app/llm/router.py`
- Create: `tests/test_llm_base.py`

- [ ] **Step 12.1: 写失败测试 `tests/test_llm_base.py`**

```python
from unittest.mock import MagicMock

from app.llm.base import LLMRequest, LLMResponse
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import ModelRouter


def test_llm_request_dataclass():
    req = LLMRequest(model_task="writer_short", system="S", user="U", max_tokens=100)
    assert req.model_task == "writer_short"
    assert req.user == "U"


def test_claude_provider_calls_sdk(monkeypatch):
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="hello world")]
    fake_resp.usage.input_tokens = 10
    fake_resp.usage.output_tokens = 5
    fake_resp.stop_reason = "end_turn"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    resp = provider.complete(LLMRequest(model_task="writer_short", user="hi"))
    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5


def test_model_router_resolves_task_to_model():
    router = ModelRouter(default_provider="claude")
    assert router.resolve_model("writer_long") == ("claude", "claude-sonnet-4-6")


def test_model_router_unknown_task_falls_back():
    router = ModelRouter(default_provider="claude")
    provider, model = router.resolve_model("nonexistent_task")
    assert provider == "claude"
```

- [ ] **Step 12.2: 运行测试验证失败**

Run: `pytest tests/test_llm_base.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.llm'`）

- [ ] **Step 12.3: 写 `app/llm/__init__.py`**

```python
```

- [ ] **Step 12.4: 写 `app/llm/base.py`**

```python
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMRequest:
    model_task: str             # writer_long / writer_short / reviewer / discuss / extractor / embedding
    user: str
    system: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    raw: object = None


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...
```

- [ ] **Step 12.5: 写 `app/llm/providers/__init__.py`**

```python
```

- [ ] **Step 12.6: 写 `app/llm/providers/claude.py`**

```python
import os

from anthropic import Anthropic

from app.llm.base import LLMRequest, LLMResponse


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""))

    def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        kwargs = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system:
            kwargs["system"] = request.system
        resp = self._client.messages.create(**kwargs)
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return LLMResponse(
            text=text,
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
            stop_reason=getattr(resp, "stop_reason", ""),
            raw=resp,
        )
```

注：`Anthropic` 这里被引用为模块级符号，便于 monkeypatch。

- [ ] **Step 12.7: 写 `app/llm/router.py`**

```python
from app.llm.base import LLMProvider
from app.llm.providers.claude import ClaudeProvider

DEFAULT_ROUTES = {
    "writer_long":  ("claude", "claude-sonnet-4-6"),
    "writer_short": ("claude", "claude-haiku-4-5"),
    "reviewer":     ("claude", "claude-sonnet-4-6"),
    "discuss":      ("claude", "claude-sonnet-4-6"),
    "extractor":    ("claude", "claude-haiku-4-5"),
}


class ModelRouter:
    def __init__(self, default_provider: str = "claude", routes: dict | None = None):
        self.default_provider = default_provider
        self.routes = routes or DEFAULT_ROUTES
        self._providers: dict[str, LLMProvider] = {}

    def _get_provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            if name == "claude":
                self._providers[name] = ClaudeProvider()
            else:
                raise ValueError(f"unknown provider: {name}")
        return self._providers[name]

    def resolve_model(self, task: str) -> tuple[str, str]:
        if task in self.routes:
            return self.routes[task]
        # 未知任务 fallback：用默认 provider + 一个保守的模型
        return (self.default_provider, "claude-haiku-4-5")

    def complete(self, request) -> "LLMResponse":
        from app.llm.base import LLMResponse  # 局部导入避免循环
        provider_name, model = self.resolve_model(request.model_task)
        provider = self._get_provider(provider_name)
        return provider.complete(request, model)
```

- [ ] **Step 12.8: 运行测试验证通过**

Run: `pytest tests/test_llm_base.py -v`
Expected: 全部 PASS

- [ ] **Step 12.9: Commit**

```bash
git add app/llm/ tests/test_llm_base.py
git commit -m "feat: llm abstraction layer with claude provider and router"
```

---

## Task 13: LLM Ping 端点

**Files:**
- Create: `app/api/llm.py`
- Modify: `app/main.py`
- Create: `tests/test_llm_api.py`

- [ ] **Step 13.1: 写失败测试 `tests/test_llm_api.py`**

```python
from unittest.mock import MagicMock

from app.llm.base import LLMResponse


def test_llm_ping_returns_text(client, monkeypatch):
    fake_resp = LLMResponse(text="pong", input_tokens=1, output_tokens=1)
    monkeypatch.setattr(
        "app.api.llm.ModelRouter",
        lambda *a, **kw: MagicMock(complete=MagicMock(return_value=fake_resp)),
    )
    r = client.post("/api/llm/ping", json={"prompt": "say hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "pong"
    assert data["input_tokens"] == 1


def test_llm_ping_handles_provider_error(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr("app.api.llm.ModelRouter", lambda *a, **kw: MagicMock(complete=boom))
    r = client.post("/api/llm/ping", json={"prompt": "x"})
    assert r.status_code == 502
    assert "provider down" in r.json()["detail"]
```

- [ ] **Step 13.2: 运行测试验证失败**

Run: `pytest tests/test_llm_api.py -v`
Expected: FAIL

- [ ] **Step 13.3: 写 `app/api/llm.py`**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.llm.base import LLMRequest
from app.llm.router import ModelRouter

router = APIRouter()


class PingRequest(BaseModel):
    prompt: str
    model_task: str = "writer_short"


class PingResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int


@router.post("/ping", response_model=PingResponse)
def ping(payload: PingRequest):
    router_ = ModelRouter()
    try:
        resp = router_.complete(
            LLMRequest(model_task=payload.model_task, user=payload.prompt, max_tokens=64)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return PingResponse(
        text=resp.text,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
    )
```

- [ ] **Step 13.4: 在 `app/main.py` 注册 router**

修改 import：

```python
from app.api import health, projects, world, lore, characters, chapters, llm
```

在 `create_app` 末尾追加：

```python
    app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
```

- [ ] **Step 13.5: 运行测试验证通过**

Run: `pytest tests/test_llm_api.py -v`
Expected: 全部 PASS

- [ ] **Step 13.6: Commit**

```bash
git add app/api/llm.py app/main.py tests/test_llm_api.py
git commit -m "feat: llm ping endpoint with error handling"
```

---

## Task 14: 端到端集成测试 + README 完善

**Files:**
- Create: `tests/test_integration_m1.py`
- Modify: `README.md`（追加 API 列表与示例）

- [ ] **Step 14.1: 写集成测试 `tests/test_integration_m1.py`**

```python
def test_full_m1_workflow(client):
    # 1. 建项目
    pid = client.post("/api/projects", json={"title": "Demo", "genre": "fantasy"}).json()["id"]

    # 2. 写世界观
    wo = client.put(
        f"/api/projects/{pid}/world-overview",
        json={"setting_era": "中古", "power_system": "魔法"},
    ).json()
    assert wo["project_id"] == pid

    # 3. 建 lore：王国 -> 城市
    kingdom = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王国"},
    ).json()["id"]
    city = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王城", "parent_id": kingdom},
    ).json()["id"]

    # 4. 建势力
    faction = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "faction", "name": "守夜人"},
    ).json()["id"]

    # 5. 建人物（关联 lore）
    char = client.post(
        "/api/characters",
        json={
            "project_id": pid,
            "name": "李雷",
            "role": "主角",
            "affiliations": [faction],
            "known_locations": [city],
        },
    ).json()
    assert char["affiliations"] == [faction]

    # 6. 建章节
    ch = client.post(
        "/api/chapters",
        json={
            "project_id": pid,
            "order_index": 1,
            "title": "第一章",
            "outline": "主角在王城遇守夜人",
        },
    ).json()
    assert ch["status"] == "draft"

    # 7. 列表查询
    assert len(client.get(f"/api/lore?project_id={pid}").json()) == 3
    assert len(client.get(f"/api/characters?project_id={pid}").json()) == 1
    assert len(client.get(f"/api/chapters?project_id={pid}").json()) == 1

    # 8. 删除项目级联清理
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/lore?project_id={pid}").json() == []
    assert client.get(f"/api/characters?project_id={pid}").json() == []
```

- [ ] **Step 14.2: 运行集成测试**

Run: `pytest tests/test_integration_m1.py -v`
Expected: PASS

- [ ] **Step 14.3: 运行全部测试**

Run: `pytest -v`
Expected: 全部 PASS（13 个测试文件全过）

- [ ] **Step 14.4: 完善 `README.md`**

```markdown
# NovelAI

AI 辅助小说写作工具（本地优先 Web 应用）。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

访问 http://127.0.0.1:8000/docs 查看 OpenAPI 文档。

## 测试

```bash
pytest
```

## M1 API 一览

| 资源 | 端点 |
|---|---|
| 项目 | `POST/GET/PATCH/DELETE /api/projects` |
| 世界观 | `PUT/GET /api/projects/{id}/world-overview` |
| Lore | `POST/GET/PATCH/DELETE /api/lore` |
| 人物 | `POST/GET/PATCH/DELETE /api/characters` |
| 章节 | `POST/GET/PATCH/DELETE /api/chapters` |
| LLM | `POST /api/llm/ping` |
```

- [ ] **Step 14.5: Commit**

```bash
git add tests/test_integration_m1.py README.md
git commit -m "test: m1 end-to-end integration + readme api listing"
```

---

## Self-Review 结果

**1. Spec coverage（M1 验收："能创建项目、世界观、人物、lore 条目、章节，能调 LLM 返回响应"）**

| Spec 要求 | 对应 Task |
|---|---|
| DB schema（5 张表） | Task 4 |
| FastAPI 骨架 | Task 2 |
| LLM 抽象层（先接一个提供商） | Task 12 |
| 基础 CRUD（projects） | Task 7 |
| 基础 CRUD（world_overview） | Task 8 |
| 基础 CRUD（lore_entries） | Task 9 |
| 基础 CRUD（characters） | Task 10 |
| 基础 CRUD（chapters） | Task 11 |
| 能调 LLM 返回响应 | Task 13（/api/llm/ping） |

全部覆盖。

**2. Placeholder scan**：扫描全文，无 TBD / TODO / "implement later" / "similar to"。每一步都有具体代码。

**3. Type consistency**：
- `LLMProvider.complete(request, model)` 在 base 与 Claude provider 一致 ✓
- `ModelRouter.resolve_model` / `complete` 一致 ✓
- 所有 Pydantic schema 命名（`XxxCreate` / `XxxUpdate` / `XxxRead`）跨任务一致 ✓
- ORM 字段名跨任务与 schema 一致 ✓

无矛盾。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-06-15-m1-foundation.md`. Two execution options:

**1. Subagent-Driven (推荐)** — 每个 task 派一个新 subagent，任务间 review，迭代快

**2. Inline Execution** — 在当前会话执行，批量推进 + 检查点 review

请选择哪种方式？
