# M3b — Vector Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add vector-embedding-based retrieval so the Writer Agent recalls semantically relevant past scenes when generating new chapter content.

**Architecture:** Extractor extends its finalize transaction to chunk + embed chapter content into a sqlite-vec virtual table (`vec_chunks`) paired with a metadata table (`chunk_meta`). Writer calls a retrieval module that embeds the query (beat_text + character names), runs KNN search, filters by cosine threshold, joins metadata, and injects results into the prompt as a new "相关场景预览" section. No new HTTP endpoints; SSE `context` event gains a `retrieved_chunks` field.

**Tech Stack:** sqlite-vec (Python wheel + loadable SQLite extension), SQLAlchemy 2.0 + Alembic (raw SQL for virtual table), OpenAI-compatible embeddings API, existing FastAPI + Jinja2 prompt templates.

**Reference spec:** `docs/superpowers/specs/2026-06-20-m3b-vector-retrieval-design.md`

**Working directory:** `/Users/bugx/novelAI`

---

## Scope Check

M3b is one cohesive subsystem (chunking + embedding + vector storage + retrieval + writer integration). No decomposition needed.

---

## File Structure

### Backend (modify + create)

```
app/
├── memory/
│   ├── schema.py              # modify: add ChunkMeta ORM
│   ├── session.py             # modify: load sqlite-vec extension on connect
│   └── vectors.py             # create: vec_chunks CRUD helpers
├── llm/
│   ├── base.py                # modify: LLMProvider.embed() protocol method
│   ├── router.py              # modify: ModelRouter.embed() forwarder
│   ├── chunking.py            # create: chunk_markdown pure function
│   └── providers/
│       ├── openai.py          # modify: implement embed()
│       └── claude.py          # modify: embed() raises NotImplementedError
├── agents/
│   ├── extractor.py           # modify: finalize adds chunking + embedding
│   ├── writer.py              # modify: prepare_generation calls retrieval
│   └── retrieval.py           # create: assemble_retrieval_context + RetrievedChunk
├── memory/retrieval.py        # modify: ContextBundle gains retrieved_chunks
├── llm/prompts/writer/user.j2 # modify: new "相关场景预览" section
└── config.py                  # modify: 4 new settings

alembic/versions/
└── <hash>_add_vec_chunks.py   # create: virtual table + chunk_meta

tests/
├── test_chunking.py           # create
├── test_vectors.py            # create
├── test_retrieval.py          # create
├── test_extractor_agent.py    # extend
└── test_writer_agent.py       # extend
```

### Frontend

No changes (StreamView already pretty-prints `context_bundle` JSON, new field surfaces automatically).

---

## Task 1: Install sqlite-vec + load extension in session.py

**Files:**
- Modify: `pyproject.toml` (add `sqlite-vec`)
- Modify: `app/memory/session.py` (load extension on connect)
- Create: `tests/test_sqlite_vec_extension.py`

- [ ] **Step 1.1: Add `sqlite-vec` dependency**

In `pyproject.toml`, append to `dependencies`:

```toml
"sqlite-vec>=0.1.6",
```

Then:

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
pip install -e ".[dev]"
python -c "import sqlite_vec; print(sqlite_vec.loadable_version())"
```

Expected: prints version ≥ 0.1.6.

- [ ] **Step 1.2: Write failing test**

Create `tests/test_sqlite_vec_extension.py`:

```python
def test_extension_loads_via_session(tmp_path, monkeypatch):
    """The session engine should auto-load vec0 on connect."""
    from sqlalchemy import create_engine, text

    from app.memory import session as session_module
    from app.memory.session import _build_engine

    db_file = tmp_path / "ext_test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    monkeypatch.setattr(session_module, "engine", new_engine)

    with new_engine.connect() as conn:
        version = conn.execute(text("SELECT vec_version()")).scalar()
    assert version is not None
    assert len(version) > 0
```

- [ ] **Step 1.3: Run → verify fails**

```bash
pytest tests/test_sqlite_vec_extension.py -v
```

Expected: FAIL — `no such function: vec_version`.

- [ ] **Step 1.4: Modify `app/memory/session.py`**

In `_build_engine`, inside the existing `@event.listens_for(engine, "connect")` handler, after the PRAGMA statements and before the `finally`, add:

```python
            # M3b: load sqlite-vec extension
            import sqlite_vec
            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)
```

The full handler should look like:

```python
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # M3b: load sqlite-vec extension
            import sqlite_vec
            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)
        finally:
            cursor.close()
```

- [ ] **Step 1.5: Run test → verify passes**

```bash
pytest tests/test_sqlite_vec_extension.py -v
```

Expected: PASS.

- [ ] **Step 1.6: Run full suite (regression)**

```bash
pytest -v 2>&1 | tail -10
```

Expected: All prior tests pass; new test green.

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml app/memory/session.py tests/test_sqlite_vec_extension.py
git commit -m "feat(m3b): load sqlite-vec extension on DB connect"
```

---

## Task 2: ChunkMeta ORM + Alembic migration

**Files:**
- Modify: `app/memory/schema.py` (add ChunkMeta class)
- Create: `alembic/versions/<hash>_add_vec_chunks.py` (via autogenerate, then manually extend)
- Create: `tests/test_chunkmeta_schema.py`

- [ ] **Step 2.1: Write failing test**

Create `tests/test_chunkmeta_schema.py`:

```python
def test_chunk_meta_table_registered():
    import app.memory.schema  # noqa: F401
    from app.memory.base import Base
    assert "chunk_meta" in Base.metadata.tables


def test_chunk_meta_unique_constraint():
    """The (chapter_id, chunk_index) unique constraint should be present."""
    import app.memory.schema  # noqa: F401
    from app.memory.base import Base
    table = Base.metadata.tables["chunk_meta"]
    constraint_names = {c.name for c in table.constraints}
    assert "uq_chunk_chapter_index" in constraint_names
```

- [ ] **Step 2.2: Run → verify fails**

```bash
pytest tests/test_chunkmeta_schema.py -v
```

Expected: FAIL — table not registered.

- [ ] **Step 2.3: Append `ChunkMeta` to `app/memory/schema.py`**

First ensure `UniqueConstraint` is imported. Update the `from sqlalchemy import ...` line:

```python
from sqlalchemy import ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint
```

Then append after `PendingUpdate` class:

```python
class ChunkMeta(Base):
    """Chunk metadata table. Each row corresponds to a row in the vec_chunks
    virtual table (same primary key). M3b pairs this with sqlite-vec for
    semantic retrieval of past chapter content."""
    __tablename__ = "chunk_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)  # paragraph | dialogue | description
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)

    __table_args__ = (
        UniqueConstraint("chapter_id", "chunk_index", name="uq_chunk_chapter_index"),
        Index("idx_chunk_chapter", "chapter_id"),
    )
```

- [ ] **Step 2.4: Run tests → verify passes**

```bash
pytest tests/test_chunkmeta_schema.py -v
```

Expected: 2 PASS.

- [ ] **Step 2.5: Generate Alembic migration**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
alembic revision --autogenerate -m "add chunk_meta and vec_chunks"
```

This creates `alembic/versions/<hash>_add_chunk_meta_and_vec_chunks.py`. **Open the file** — autogenerate will produce `chunk_meta` create_table + indexes, but NOT the `vec_chunks` virtual table.

- [ ] **Step 2.6: Manually add `vec_chunks` virtual table to migration**

Open the generated migration file. In `upgrade()`, after the `chunk_meta` create_table calls (created by autogenerate), add:

```python
    # M3b: vec_chunks virtual table (sqlite-vec). SQLAlchemy can't autogenerate this.
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
        "embedding FLOAT[1024])"
    )
```

In `downgrade()`, before the `chunk_meta` drop_table, add:

```python
    op.execute("DROP TABLE IF EXISTS vec_chunks")
```

The default dimension is 1024 (matches DashScope text-embedding-v3 / bge-m3). The dimension declared here is what sqlite-vec enforces on inserts; if you switch to a different dimension later you must drop + recreate this virtual table.

- [ ] **Step 2.7: Apply migration to existing dev DB**

```bash
alembic upgrade head
sqlite3 data/novelai.db "SELECT name FROM sqlite_master WHERE name IN ('vec_chunks', 'chunk_meta') ORDER BY name"
```

Expected: prints both `chunk_meta` and `vec_chunks`.

- [ ] **Step 2.8: Verify round-trip (no schema diff)**

```bash
alembic revision --autogenerate -m "test_empty_m3b" 2>&1 | head -20
```

Expected: message like "No changes in schema detected" or a migration with `pass` in upgrade/downgrade. **Delete** the test_empty file if generated.

- [ ] **Step 2.9: Run full backend tests**

```bash
pytest -v 2>&1 | tail -10
```

Expected: All tests pass. (Tests using `Base.metadata.create_all` will skip the migration and create `chunk_meta` from ORM, but `vec_chunks` virtual table is NOT auto-created by `create_all`. The next task's vectors helpers will ensure tests create the virtual table manually.)

**Important:** any test fixture that uses a fresh tmp DB and needs vector operations must manually `CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding FLOAT[1024])`. Documented in Task 4 (test_vectors.py).

- [ ] **Step 2.10: Commit**

```bash
git add app/memory/schema.py alembic/versions/ tests/test_chunkmeta_schema.py
git commit -m "feat(m3b): chunk_meta ORM + alembic migration with vec_chunks virtual table"
```

---

## Task 3: Chunking pure function

**Files:**
- Create: `app/llm/chunking.py`
- Create: `tests/test_chunking.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_chunking.py`:

```python
from app.llm.chunking import chunk_markdown, Chunk


def test_chunk_single_paragraph():
    chunks = chunk_markdown("一段文字。")
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "paragraph"
    assert chunks[0].text == "一段文字。"
    assert chunks[0].char_count == 5


def test_chunk_multiple_paragraphs():
    chunks = chunk_markdown("第一段。\n\n第二段。\n\n第三段。")
    assert len(chunks) == 3
    assert [c.text for c in chunks] == ["第一段。", "第二段。", "第三段。"]


def test_chunk_empty_content():
    assert chunk_markdown("") == []


def test_chunk_whitespace_only():
    assert chunk_markdown("\n\n   \n\n") == []


def test_chunk_long_paragraph_split():
    # 1500 字段落 > MAX_PARAGRAPH_CHARS(800)
    long_para = "字" * 1500
    chunks = chunk_markdown(long_para)
    assert len(chunks) >= 2
    # 每片应该 ≤ 800 (除了最后可能短的)
    for c in chunks:
        assert c.char_count <= 800


def test_chunk_dialogue_detection():
    text = '他说："你好。"她答："你好。"'
    chunks = chunk_markdown(text)
    assert chunks[0].chunk_type == "dialogue"


def test_chunk_description_detection():
    text = "他看见远处的山。她闻到花香。听见鸟鸣。"
    chunks = chunk_markdown(text)
    assert chunks[0].chunk_type == "description"


def test_chunk_chinese_punctuation_split():
    """长段落按中文句号切。"""
    text = "字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字。" * 20  # > 800
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2


def test_chunk_preserves_text():
    text = "abc测试def"
    chunks = chunk_markdown(text)
    assert chunks[0].text == text


def test_chunk_char_count_correct():
    text = "abc"
    chunks = chunk_markdown(text)
    assert chunks[0].char_count == 3
```

- [ ] **Step 3.2: Run → verify fails**

```bash
pytest tests/test_chunking.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3.3: Create `app/llm/chunking.py`**

```python
"""Chunk Markdown chapter content into retrieval-ready pieces.

Pure functions. No LLM calls, no DB I/O.
"""
import re
from dataclasses import dataclass

MAX_PARAGRAPH_CHARS = 800

_DESCRIPTION_MARKERS = (
    "看", "看见", "看到", "闻", "听见", "听到",
    "摸", "触摸", "走", "跑", "坐", "站",
)


@dataclass
class Chunk:
    text: str
    chunk_type: str  # 'paragraph' | 'dialogue' | 'description'
    char_count: int


def chunk_markdown(content: str) -> list[Chunk]:
    """Split Markdown content into chunks.

    Strategy:
    1. Split by double-newline (Markdown paragraph boundaries).
    2. Skip whitespace-only paragraphs.
    3. Paragraphs > MAX_PARAGRAPH_CHARS: re-split by sentence terminators。
    4. Classify chunk_type by simple heuristics.
    """
    if not content or not content.strip():
        return []
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    for para in paragraphs:
        if len(para) <= MAX_PARAGRAPH_CHARS:
            chunks.append(_classify(para))
        else:
            for piece in _split_long_paragraph(para):
                chunks.append(_classify(piece))
    return chunks


def _split_long_paragraph(text: str) -> list[str]:
    """Split a long paragraph into pieces <= MAX_PARAGRAPH_CHARS.

    Splits by sentence terminators (。！？.!?), accumulates sentences until
    adding the next would exceed the limit, then starts a new piece.
    """
    sentences = _split_sentences(text)
    pieces: list[str] = []
    buffer = ""
    for sent in sentences:
        if len(buffer) + len(sent) > MAX_PARAGRAPH_CHARS and buffer:
            pieces.append(buffer)
            buffer = sent
        else:
            buffer += sent
    if buffer:
        pieces.append(buffer)
    # Edge case: a single sentence longer than MAX. Accept it as-is rather
    # than truncate mid-character; embedding APIs handle long inputs.
    return pieces or [text]


def _split_sentences(text: str) -> list[str]:
    """Split on 。！？.!? keeping the terminator. Filters empty fragments."""
    parts = re.split(r"(?<=[。！？.!?])", text)
    return [p for p in parts if p]


def _classify(text: str) -> Chunk:
    """Heuristically classify a chunk as paragraph / dialogue / description."""
    dialogue_marks = (
        text.count('"') + text.count('"') + text.count('"')
        + text.count('「') + text.count('」')
        + text.count('『') + text.count('』')
    )
    if dialogue_marks >= 3:
        ctype = "dialogue"
    elif sum(text.count(m) for m in _DESCRIPTION_MARKERS) >= 2:
        ctype = "description"
    else:
        ctype = "paragraph"
    return Chunk(text=text, chunk_type=ctype, char_count=len(text))
```

- [ ] **Step 3.4: Run tests → verify passes**

```bash
pytest tests/test_chunking.py -v
```

Expected: 10 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add app/llm/chunking.py tests/test_chunking.py
git commit -m "feat(m3b): chunk_markdown pure function with paragraph splitting and chunk_type heuristics"
```

---

## Task 4: vectors.py CRUD helpers

**Files:**
- Create: `app/memory/vectors.py`
- Create: `tests/test_vectors.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_vectors.py`:

```python
import struct

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401 register all ORM classes


def _make_vec(values: list[float]) -> bytes:
    """Serialize vector as raw float32 LE bytes (sqlite-vec format)."""
    return struct.pack(f"<{len(values)}f", *values)


@pytest.fixture
def db_session(tmp_path):
    """In-memory-style DB with vec_chunks virtual table created manually."""
    db_file = tmp_path / "vectors_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    # Load sqlite-vec on each connection
    import sqlite_vec
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _load_vec(dbapi_conn, _record):
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    # Create all ORM tables + vec_chunks virtual table
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024])"
        ))
        conn.commit()

    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def _seed_chapter(db_session):
    """Minimal chapter row so chunk_meta FK is valid."""
    from app.memory.schema import Chapter, Project
    p = Project(title="P")
    db_session.add(p)
    db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch)
    db_session.commit()
    return ch.id


def test_insert_chunk_returns_id(db_session):
    from app.memory.vectors import insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="hello", char_count=5,
        embedding=[0.1] * 1024,
    )
    db_session.commit()
    assert rid > 0


def test_insert_chunk_writes_vec_table(db_session):
    from app.memory.vectors import insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="hello", char_count=5,
        embedding=[0.5] * 1024,
    )
    db_session.commit()
    # Verify vec_chunks has the row
    rows = db_session.execute(
        text("SELECT rowid FROM vec_chunks WHERE rowid = :rid"),
        {"rid": rid},
    ).fetchall()
    assert len(rows) == 1


def test_delete_chapter_chunks_removes_both_tables(db_session):
    from app.memory.vectors import delete_chapter_chunks, insert_chunk
    cid = _seed_chapter(db_session)
    rid = insert_chunk(
        db_session, chapter_id=cid, chunk_index=0,
        chunk_type="paragraph", text="x", char_count=1,
        embedding=[0.1] * 1024,
    )
    db_session.commit()
    delete_chapter_chunks(db_session, cid)
    db_session.commit()

    from app.memory.schema import ChunkMeta
    assert db_session.query(ChunkMeta).filter_by(chapter_id=cid).count() == 0
    rows = db_session.execute(
        text("SELECT rowid FROM vec_chunks WHERE rowid = :rid"), {"rid": rid}
    ).fetchall()
    assert len(rows) == 0


def test_delete_chapter_chunks_preserves_other_chapters(db_session):
    from app.memory.schema import Chapter, Project, ChunkMeta
    from app.memory.vectors import delete_chapter_chunks, insert_chunk

    p = Project(title="P")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="C1")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2")
    db_session.add_all([ch1, ch2]); db_session.commit()

    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="a", char_count=1,
                 embedding=[0.1] * 1024)
    insert_chunk(db_session, chapter_id=ch2.id, chunk_index=0,
                 chunk_type="paragraph", text="b", char_count=1,
                 embedding=[0.2] * 1024)
    db_session.commit()

    delete_chapter_chunks(db_session, ch1.id)
    db_session.commit()

    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch1.id).count() == 0
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch2.id).count() == 1


def test_delete_nonexistent_chapter_noop(db_session):
    from app.memory.vectors import delete_chapter_chunks
    # No exception
    delete_chapter_chunks(db_session, 99999)
    db_session.commit()
```

- [ ] **Step 4.2: Run → verify fails**

```bash
pytest tests/test_vectors.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4.3: Create `app/memory/vectors.py`**

```python
"""sqlite-vec virtual table CRUD helpers.

vec_chunks is a sqlite-vec virtual table — SQLAlchemy ORM can't map it.
We pair it with chunk_meta (standard ORM table) via shared primary key.
"""
import struct

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.memory.schema import ChunkMeta


def delete_chapter_chunks(db: Session, chapter_id: int) -> None:
    """Delete all chunks for a chapter from both chunk_meta and vec_chunks."""
    rowids = db.execute(
        sql_text("SELECT id FROM chunk_meta WHERE chapter_id = :cid"),
        {"cid": chapter_id},
    ).scalars().all()
    if not rowids:
        return
    db.execute(
        sql_text("DELETE FROM chunk_meta WHERE chapter_id = :cid"),
        {"cid": chapter_id},
    )
    placeholders = ",".join("?" * len(rowids))
    db.execute(
        sql_text(f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})"),
        list(rowids),
    )


def insert_chunk(
    db: Session,
    *,
    chapter_id: int,
    chunk_index: int,
    chunk_type: str,
    text: str,
    char_count: int,
    embedding: list[float],
) -> int:
    """Insert a chunk into chunk_meta + vec_chunks. Returns the chunk_meta.id."""
    meta = ChunkMeta(
        chapter_id=chapter_id,
        chunk_index=chunk_index,
        chunk_type=chunk_type,
        text=text,
        char_count=char_count,
    )
    db.add(meta)
    db.flush()  # populate meta.id
    db.execute(
        sql_text("INSERT INTO vec_chunks(rowid, embedding) VALUES (:id, :vec)"),
        {"id": meta.id, "vec": _serialize_vec(embedding)},
    )
    return meta.id


def _serialize_vec(vec: list[float]) -> bytes:
    """Serialize vector as raw float32 little-endian bytes (sqlite-vec format)."""
    return struct.pack(f"<{len(vec)}f", *vec)
```

- [ ] **Step 4.4: Run tests → verify passes**

```bash
pytest tests/test_vectors.py -v
```

Expected: 5 PASS.

- [ ] **Step 4.5: Commit**

```bash
git add app/memory/vectors.py tests/test_vectors.py
git commit -m "feat(m3b): vectors.py CRUD helpers (delete_chapter_chunks + insert_chunk)"
```

---

## Task 5: LLMProvider.embed protocol + Provider implementations

**Files:**
- Modify: `app/llm/base.py` (add embed to Protocol)
- Modify: `app/llm/providers/openai.py` (implement embed)
- Modify: `app/llm/providers/claude.py` (raise NotImplementedError)
- Create: `tests/test_provider_embed.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_provider_embed.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.claude import ClaudeProvider


def test_openai_provider_embed_returns_vectors(monkeypatch):
    """embed() should call OpenAI embeddings endpoint and return list[list[float]]."""
    fake_client = MagicMock()
    fake_data = MagicMock()
    fake_data.embedding = [0.1, 0.2, 0.3]
    fake_client.embeddings.create.return_value = MagicMock(data=[fake_data, fake_data])

    provider = OpenAIProvider(api_key="fake")
    provider._client = fake_client  # bypass constructor

    result = provider.embed(["hello", "world"], "text-embedding-3-small")
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small", input=["hello", "world"]
    )


def test_claude_provider_embed_raises_not_implemented():
    """Claude has no embeddings API; raise NotImplementedError."""
    provider = ClaudeProvider(api_key="fake")
    with pytest.raises(NotImplementedError):
        provider.embed(["hello"], "any-model")
```

- [ ] **Step 5.2: Run → verify fails**

```bash
pytest tests/test_provider_embed.py -v
```

Expected: FAIL — `embed` attribute not found.

- [ ] **Step 5.3: Add `embed` to `LLMProvider` protocol in `app/llm/base.py`**

Find the `LLMProvider` protocol class and add `embed`:

```python
class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...

    def stream(self, request: LLMRequest, model: str) -> Iterator[StreamEvent]: ...

    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
```

- [ ] **Step 5.4: Add `embed` to `OpenAIProvider`**

In `app/llm/providers/openai.py`, append at the end of the class:

```python
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """OpenAI-compatible embeddings endpoint.

        Works with: OpenAI text-embedding-3-small/large, DashScope text-embedding-v2,
        Ollama bge-m3, vLLM, LM Studio, etc.
        """
        resp = self._client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]
```

- [ ] **Step 5.5: Add `embed` to `ClaudeProvider`**

In `app/llm/providers/claude.py`, append at the end of the class:

```python
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Anthropic does not provide an embeddings API."""
        raise NotImplementedError(
            "Anthropic does not provide embeddings API. "
            "Set NOVELAI_LLM_PROVIDER=openai or configure a separate embedding endpoint."
        )
```

- [ ] **Step 5.6: Run tests → verify passes**

```bash
pytest tests/test_provider_embed.py -v
```

Expected: 2 PASS.

- [ ] **Step 5.7: Commit**

```bash
git add app/llm/base.py app/llm/providers/openai.py app/llm/providers/claude.py \
        tests/test_provider_embed.py
git commit -m "feat(m3b): embed() protocol method + openai/claude providers"
```

---

## Task 6: ModelRouter.embed + config extension

**Files:**
- Modify: `app/llm/router.py` (add embed forwarder)
- Modify: `app/config.py` (4 new settings)
- Modify: `app/llm/providers/__init__.py` if needed (verify imports still work)
- Modify: `.env.example`
- Create: `tests/test_router_embed.py`

- [ ] **Step 6.1: Write failing test**

Create `tests/test_router_embed.py`:

```python
from unittest.mock import MagicMock


def test_router_embed_delegates_to_provider():
    """Router.embed should call the resolved provider's embed with configured model."""
    from app.llm.router import ModelRouter

    fake_provider = MagicMock()
    fake_provider.embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

    router = ModelRouter()
    router._providers = {"openai": fake_provider}  # bypass __init__ provider creation

    result = router.embed(["hello", "world"], "text-embedding-3-small")
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    fake_provider.embed.assert_called_once_with(["hello", "world"], "text-embedding-3-small")


def test_router_embed_defaults_model_from_settings():
    """If model is None, router falls back to settings.embedding_model."""
    from app.llm.router import ModelRouter

    fake_provider = MagicMock()
    fake_provider.embed.return_value = [[0.1]]

    router = ModelRouter()
    router._providers = {"openai": fake_provider}

    router.embed(["x"])  # no model arg
    args = fake_provider.embed.call_args
    assert args[0][1] is not None  # second positional arg is model; default applied
```

- [ ] **Step 6.2: Run → verify fails**

```bash
pytest tests/test_router_embed.py -v
```

Expected: FAIL — `embed` attribute not found on ModelRouter.

- [ ] **Step 6.3: Extend `app/config.py`**

Add 4 settings fields to the `Settings` class (alongside existing `embedding_*` if any, or new):

```python
    # M3b: Embedding + retrieval
    embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "NOVELAI_EMBEDDING_MODEL"),
    )
    embedding_dimensions: int = Field(
        default=1536,
        validation_alias=AliasChoices("EMBEDDING_DIMENSIONS", "NOVELAI_EMBEDDING_DIMENSIONS"),
    )
    retrieval_top_k: int = Field(
        default=5,
        validation_alias=AliasChoices("RETRIEVAL_TOP_K", "NOVELAI_RETRIEVAL_TOP_K"),
    )
    retrieval_threshold: float = Field(
        default=0.4,
        validation_alias=AliasChoices("RETRIEVAL_THRESHOLD", "NOVELAI_RETRIEVAL_THRESHOLD"),
    )
```

- [ ] **Step 6.4: Add `embed` to `ModelRouter` in `app/llm/router.py`**

Add a new method to the `ModelRouter` class:

```python
    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Embed texts using the configured provider.

        M3b: reuses the writer provider (user-configured OpenAI-compatible endpoint).
        """
        provider = self._get_provider(self.default_provider)
        embed_model = model or settings.embedding_model or "text-embedding-3-small"
        return provider.embed(texts, embed_model)
```

Ensure `from app.config import settings` is already imported at top of file (it is, per M2a code).

- [ ] **Step 6.5: Update `.env.example`**

Append to `/Users/bugx/novelAI/.env.example`:

```
# === Embedding + 向量检索（M3b）===
# Embedding 模型名（OpenAI-compatible 端点；与 NOVELAI_LLM_PROVIDER 共用一套配置）
EMBEDDING_MODEL=text-embedding-3-small
# 向量维度（必须和 EMBEDDING_MODEL 一致；切换模型时需重建 vec_chunks 表）
EMBEDDING_DIMENSIONS=1536
# 检索 top-K（默认召回多少 chunks）
RETRIEVAL_TOP_K=5
# 检索 cosine 阈值（< 此值的 chunk 不召回）
RETRIEVAL_THRESHOLD=0.4
```

- [ ] **Step 6.6: Run tests → verify passes**

```bash
pytest tests/test_router_embed.py -v
```

Expected: 2 PASS.

- [ ] **Step 6.7: Commit**

```bash
git add app/llm/router.py app/config.py .env.example tests/test_router_embed.py
git commit -m "feat(m3b): ModelRouter.embed + 4 embedding/retrieval settings"
```

---

## Task 7: retrieval.py (assemble_retrieval_context)

**Files:**
- Create: `app/agents/retrieval.py`
- Create: `tests/test_retrieval.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_retrieval.py`:

```python
import struct

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.memory.base import Base
import app.memory.schema  # noqa: F401


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "retrieval_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    import sqlite_vec

    @event.listens_for(engine, "connect")
    def _load_vec(dbapi_conn, _record):
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024])"
        ))
        conn.commit()

    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def _seed_two_chapters_with_chunks(db_session):
    """Seed 2 chapters; chapter 1 has 2 chunks, chapter 2 has 1 chunk."""
    from app.memory.schema import Chapter, Project
    from app.memory.vectors import insert_chunk

    p = Project(title="P")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="第一章")
    ch2 = Chapter(project_id=p.id, order_index=2, title="第二章")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # chapter 1 chunk A: vector close to query (cosine ~ 0.9)
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="chapter1 chunk A", char_count=15,
                 embedding=[0.9] * 1024)
    # chapter 1 chunk B: vector orthogonal to query
    orthogonal = [0.0] * 1024
    orthogonal[0] = 1.0
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=1,
                 chunk_type="paragraph", text="chapter1 chunk B", char_count=15,
                 embedding=orthogonal)
    # chapter 2 chunk: similar to query too
    insert_chunk(db_session, chapter_id=ch2.id, chunk_index=0,
                 chunk_type="paragraph", text="chapter2 chunk", char_count=14,
                 embedding=[0.85] * 1024)
    db_session.commit()
    return ch1.id, ch2.id


def _fake_router_returning(query_vec):
    """Build a router whose embed() returns the given query vector."""
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.embed.return_value = [query_vec]
    return fake


def test_retrieval_returns_relevant_chunks(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    # query vector close to chunk A and chapter2 chunk
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999,  # exclude nothing
        query_text="anything", router=fake_router,
    )
    texts = [r.text for r in results]
    assert "chapter1 chunk A" in texts
    assert "chapter2 chunk" in texts
    # chunk B is orthogonal (cosine ~ 0); filtered by threshold 0.4
    assert "chapter1 chunk B" not in texts


def test_retrieval_threshold_filters_low_score(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    # query orthogonal to everything
    orthogonal = [0.0] * 1024
    orthogonal[0] = 1.0
    fake_router = _fake_router_returning(orthogonal)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    # All chunks orthogonal to query → filtered by threshold 0.4
    assert len(results) == 0


def test_retrieval_excludes_current_chapter(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=ch1, query_text="x", router=fake_router,
    )
    chapter_ids = {r.chapter_id for r in results}
    assert ch1 not in chapter_ids
    assert ch2 in chapter_ids


def test_retrieval_top_k_limits_count(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
        top_k=1,
    )
    assert len(results) == 1


def test_retrieval_empty_when_no_chunks(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    fake_router = _fake_router_returning([0.5] * 1024)
    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    assert results == []


def test_retrieval_sorts_by_score_desc(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    if len(results) >= 2:
        assert results[0].score >= results[1].score


def test_retrieval_joins_chapter_title(db_session):
    from app.agents.retrieval import assemble_retrieval_context
    ch1, ch2 = _seed_two_chapters_with_chunks(db_session)
    fake_router = _fake_router_returning([0.9] * 1024)

    results = assemble_retrieval_context(
        db_session, current_chapter_id=999, query_text="x", router=fake_router,
    )
    titles = {r.chapter_title for r in results}
    assert "第一章" in titles or "第二章" in titles
```

- [ ] **Step 7.2: Run → verify fails**

```bash
pytest tests/test_retrieval.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 7.3: Create `app/agents/retrieval.py`**

```python
"""Vector retrieval layer for the Writer Agent.

Given a query (typically beat_text + character names), embeds the query and
runs a KNN search against the vec_chunks virtual table. Returns chunks from
PAST chapters (excluding the current one) above a cosine similarity threshold.
"""
import struct
from dataclasses import dataclass

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.router import ModelRouter, default_router


@dataclass
class RetrievedChunk:
    chunk_id: int
    chapter_id: int
    chapter_title: str
    chunk_type: str
    text: str
    score: float  # cosine similarity


def assemble_retrieval_context(
    db: Session,
    *,
    current_chapter_id: int,
    query_text: str,
    router: ModelRouter = default_router,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[RetrievedChunk]:
    """Embed the query, run KNN, filter by threshold, exclude current chapter."""
    k = top_k if top_k is not None else settings.retrieval_top_k
    th = threshold if threshold is not None else settings.retrieval_threshold

    # 1. Embed query
    query_vectors = router.embed([query_text])
    query_vec = query_vectors[0]

    # 2. KNN search (take k*2 to give threshold filter slack)
    knn_sql = sql_text(
        "SELECT rowid, distance "
        "FROM vec_chunks "
        "WHERE embedding MATCH :vec AND k = :k "
        "ORDER BY distance"
    )
    rows = db.execute(
        knn_sql,
        {"vec": _serialize_vec(query_vec), "k": k * 2},
    ).fetchall()

    # 3. Filter by threshold
    candidates: list[tuple[int, float]] = []
    for rowid, distance in rows:
        score = 1.0 - distance  # sqlite-vec returns cosine distance
        if score < th:
            continue
        candidates.append((rowid, score))
        if len(candidates) >= k:
            break

    if not candidates:
        return []

    # 4. JOIN chunk_meta + chapter, exclude current chapter
    score_map = {rid: score for rid, score in candidates}
    placeholders = ",".join(str(int(rid)) for rid in score_map.keys())
    meta_rows = db.execute(
        sql_text(
            f"SELECT cm.id, cm.chapter_id, cm.chunk_type, cm.text, "
            f"c.title AS chapter_title "
            f"FROM chunk_meta cm "
            f"JOIN chapters c ON c.id = cm.chapter_id "
            f"WHERE cm.id IN ({placeholders}) "
            f"AND cm.chapter_id != :current"
        ),
        {"current": current_chapter_id},
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in meta_rows:
        results.append(RetrievedChunk(
            chunk_id=row.id,
            chapter_id=row.chapter_id,
            chapter_title=row.chapter_title or f"Chapter {row.chapter_id}",
            chunk_type=row.chunk_type,
            text=row.text,
            score=score_map.get(row.id, 0.0),
        ))

    # 5. Sort by similarity desc
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:k]


def _serialize_vec(vec: list[float]) -> bytes:
    """Serialize vector as raw float32 little-endian bytes (sqlite-vec format)."""
    return struct.pack(f"<{len(vec)}f", *vec)
```

- [ ] **Step 7.4: Run tests → verify passes**

```bash
pytest tests/test_retrieval.py -v
```

Expected: 7 PASS.

If `test_retrieval_threshold_filters_low_score` fails (chunks returned despite low score), verify sqlite-vec returns `distance` not `similarity` — if it returns similarity, change `score = 1.0 - distance` to `score = distance`.

- [ ] **Step 7.5: Commit**

```bash
git add app/agents/retrieval.py tests/test_retrieval.py
git commit -m "feat(m3b): assemble_retrieval_context (KNN + threshold + chapter join)"
```

---

## Task 8: Extend extractor.py with chunking + embedding

**Files:**
- Modify: `app/agents/extractor.py` (add chunking + embedding step in transaction)
- Modify: `tests/test_extractor_agent.py` (extend with new tests)

- [ ] **Step 8.1: Extend test fixtures to create vec_chunks virtual table**

In `tests/test_extractor_agent.py`, the existing `db_session` fixture uses `init_db()` which calls `Base.metadata.create_all`. This does NOT create the `vec_chunks` virtual table.

Update the `db_session` fixture in `tests/test_extractor_agent.py` to manually create the virtual table after `init_db()`:

```python
@pytest.fixture
def db_session(tmp_path, monkeypatch):
    """Isolated DB session for extractor tests."""
    from app.memory import session as session_module
    from app.memory.session import _build_engine, init_db
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
    # M3b: create vec_chunks virtual table (Base.metadata.create_all doesn't)
    with new_engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024])"
        ))
        conn.commit()
    with new_session() as s:
        yield s
```

- [ ] **Step 8.2: Add new tests for chunking + embedding**

Append to `tests/test_extractor_agent.py`:

```python
def test_extract_creates_chunks(db_session):
    """After extract_chapter, chunk_meta should have rows for the chapter."""
    from app.memory.schema import ChunkMeta
    from sqlalchemy import text

    p, ch = _seed_chapter(db_session, content="第一段。\n\n第二段。\n\n第三段。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    # embed returns 3 vectors (one per chunk)
    fake_router.embed = MagicMock(return_value=[[0.1] * 1024] * 3)

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    chunks = db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).all()
    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_extract_writes_embeddings(db_session):
    """After extract_chapter, vec_chunks should have rows for each chunk."""
    from sqlalchemy import text
    p, ch = _seed_chapter(db_session, content="段落一。\n\n段落二。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024, [0.6] * 1024])

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    rows = db_session.execute(text("SELECT count() FROM vec_chunks")).scalar()
    assert rows == 2


def test_extract_rerun_overwrites_chunks(db_session):
    """Re-finalize should delete old chunks and write new ones."""
    from app.memory.schema import ChunkMeta
    p, ch = _seed_chapter(db_session, content="段落一。\n\n段落二。")
    fake_router = _fake_router(json.dumps({
        "summary": "first",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock(return_value=[[0.1] * 1024] * 2)
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 2

    # Re-run with different content
    ch.content = "新内容。\n\n段落二。\n\n段落三。\n\n段落四。"
    db_session.commit()
    fake_router.embed = MagicMock(return_value=[[0.2] * 1024] * 4)
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"summary": "second", "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}}),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)
    # 4 new chunks (3 old deleted + 4 new written)
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 4


def test_extract_no_content_no_chunks(db_session):
    """Empty chapter content → 0 chunks, no embedding call."""
    from app.memory.schema import ChunkMeta
    p, ch = _seed_chapter(db_session, content="")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock()

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 0
    fake_router.embed.assert_not_called()


def test_extract_embedding_failure_rolls_back(db_session):
    """If embed() raises, the entire finalize should roll back."""
    from app.memory.schema import ChunkMeta, PendingUpdate
    p, ch = _seed_chapter(db_session, content="段落内容。")
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [{"name": "X", "role": "extra", "description": "y"}],
                     "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    fake_router.embed = MagicMock(side_effect=RuntimeError("embedding API down"))

    with pytest.raises(RuntimeError):
        extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    # Nothing should be committed
    db_session.expire_all()
    assert db_session.query(PendingUpdate).filter_by(chapter_id=ch.id).count() == 0
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 0
    chapter = db_session.get(Chapter, ch.id)
    assert chapter.summary == ""  # not set
    assert chapter.status != "final"


def test_extract_batch_split_for_long_chapter(db_session):
    """Chapter with > 50 paragraphs → embed() called multiple times (batch=50)."""
    from app.memory.schema import ChunkMeta
    # 60 paragraphs
    content = "\n\n".join(f"段落 {i}。" for i in range(60))
    p, ch = _seed_chapter(db_session, content=content)
    fake_router = _fake_router(json.dumps({
        "summary": "x",
        "entities": {"new_characters": [], "updated_characters": [], "new_lore": [], "updated_lore": []}
    }))
    # Each batch returns 50 vectors
    fake_router.embed = MagicMock(
        side_effect=[[ [0.1] * 1024 ] * 50, [ [0.2] * 1024 ] * 10]
    )

    extract_chapter(db_session, chapter_id=ch.id, router=fake_router)

    assert fake_router.embed.call_count == 2
    assert db_session.query(ChunkMeta).filter_by(chapter_id=ch.id).count() == 60
```

- [ ] **Step 8.3: Run → verify fails**

```bash
pytest tests/test_extractor_agent.py -v -k "chunk or embed"
```

Expected: FAIL — chunks not created (extractor not extended yet).

- [ ] **Step 8.4: Modify `app/agents/extractor.py`**

Add imports at top:

```python
from app.llm.chunking import chunk_markdown
from app.memory.vectors import delete_chapter_chunks, insert_chunk
```

In `extract_chapter`, find the `db.commit()` call near the end. BEFORE that commit, insert the chunking + embedding block:

```python
    # M3b: chunking + embedding (part of the atomic transaction)
    chunks = chunk_markdown(chapter.content or "")
    if chunks:
        BATCH = 50
        all_embeddings: list[list[float]] = []
        for i in range(0, len(chunks), BATCH):
            batch_texts = [c.text for c in chunks[i:i + BATCH]]
            all_embeddings.extend(router.embed(batch_texts))

        # Delete old chunks for this chapter
        delete_chapter_chunks(db, chapter_id)

        # Insert new chunks
        for idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            insert_chunk(
                db,
                chapter_id=chapter_id,
                chunk_index=idx,
                chunk_type=chunk.chunk_type,
                text=chunk.text,
                char_count=chunk.char_count,
                embedding=embedding,
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
```

Make sure this is INSIDE the existing try/except block (before `db.commit()`). The chunking and embedding happen in the same transaction as the pending_updates writes — if embed() fails, the entire transaction rolls back.

The exact structure of the end of `extract_chapter` should be:

```python
    try:
        db.add(log)
        db.flush()
        for p in pending_rows:
            p.extractor_log_id = log.id

        db.execute(delete(PendingUpdate).where(
            PendingUpdate.chapter_id == chapter_id,
            PendingUpdate.status == "pending",
        ))

        for p in pending_rows:
            db.add(p)

        chapter.summary = summary
        chapter.content_hash = new_hash
        chapter.status = "final"

        # M3b: chunking + embedding
        chunks = chunk_markdown(chapter.content or "")
        if chunks:
            BATCH = 50
            all_embeddings: list[list[float]] = []
            for i in range(0, len(chunks), BATCH):
                batch_texts = [c.text for c in chunks[i:i + BATCH]]
                all_embeddings.extend(router.embed(batch_texts))

            delete_chapter_chunks(db, chapter_id)
            for idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
                insert_chunk(
                    db,
                    chapter_id=chapter_id,
                    chunk_index=idx,
                    chunk_type=chunk.chunk_type,
                    text=chunk.text,
                    char_count=chunk.char_count,
                    embedding=embedding,
                )

        db.commit()
    except Exception:
        db.rollback()
        raise
```

**Important:** the existing test `test_extract_creates_summary_and_pending` passes a `_fake_router` that does NOT have an `embed` attribute. The new code will call `router.embed(...)` which will fail with AttributeError. Update the existing `_fake_router` helper to include `embed`:

In `tests/test_extractor_agent.py`, modify `_fake_router`:

```python
def _fake_router(response_text: str):
    """Build a fake router that returns a fixed LLMResponse + embeddings."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(
        return_value=LLMResponse(
            text=response_text,
            input_tokens=100,
            output_tokens=200,
            stop_reason="end_turn",
        )
    )
    # M3b: default embed returns 1024-dim vectors; tests override per-case
    fake.embed = MagicMock(return_value=[[0.1] * 1024])
    return fake
```

This default returns 1 vector per call. For tests with multiple chunks, the per-test override (`fake_router.embed = MagicMock(return_value=[...] * N)`) takes precedence.

- [ ] **Step 8.5: Run tests → verify passes**

```bash
pytest tests/test_extractor_agent.py -v
```

Expected: All 12 M3a tests + 6 new M3b tests = 18 PASS.

- [ ] **Step 8.6: Run full backend suite**

```bash
pytest -v 2>&1 | tail -10
```

Expected: All pass.

- [ ] **Step 8.7: Commit**

```bash
git add app/agents/extractor.py tests/test_extractor_agent.py
git commit -m "feat(m3b): extractor finalizes chunking + embedding atomically"
```

---

## Task 9: Writer integration (retrieval + prompt section)

**Files:**
- Modify: `app/agents/writer.py` (call retrieval in prepare_generation)
- Modify: `app/llm/prompts/writer/user.j2` (new "相关场景预览" section)
- Modify: `app/memory/retrieval.py` (ContextBundle add retrieved_chunks)
- Modify: `tests/test_writer_agent.py`

- [ ] **Step 9.1: Extend ContextBundle**

In `app/memory/retrieval.py`, add `retrieved_chunks` field to `ContextBundle`:

```python
@dataclass
class ContextBundle:
    project: Project
    world_overview: WorldOverview | None
    characters: list[Character]
    character_states: dict[int, CharacterStateSnapshot]
    relationships: list[RelationshipView]
    lore_entries: list[LoreEntry]
    faction_lore: list[LoreEntry]
    location_lore: list[LoreEntry]
    plot_lines: list[Any]
    recent_chapter_summaries: list[ChapterSummary]
    retrieved_chunks: list[Any] = field(default_factory=list)  # M3b: list[RetrievedChunk]
```

Ensure `field` is imported: `from dataclasses import dataclass, field`.

`list[Any]` is used instead of `list[RetrievedChunk]` to avoid circular import (`RetrievedChunk` lives in `app.agents.retrieval` which imports from `app.memory`). Use TYPE_CHECKING guard if strict typing desired:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.agents.retrieval import RetrievedChunk
```

But `list[Any]` is fine for M3b.

- [ ] **Step 9.2: Add "相关场景预览" section to user.j2**

In `app/llm/prompts/writer/user.j2`, after the `{% if recent_chapter_summaries %}...{% endif %}` block and BEFORE the `# 本次写作任务` section, insert:

```jinja
{% if retrieved_chunks %}
# 相关场景预览（向量检索召回）

以下是与本段情节语义相关的过往章节片段，供参考保持前后一致：

{% for chunk in retrieved_chunks %}
## [{{ chunk.chapter_title }}]（相似度 {{ "%.2f"|format(chunk.score) }}）
> {{ chunk.text }}

{% endfor %}
{% endif %}
```

- [ ] **Step 9.3: Modify `prepare_generation` in `app/agents/writer.py`**

Add import at top:

```python
from app.agents.retrieval import assemble_retrieval_context
```

In `prepare_generation`, after the `bundle = assemble_context(...)` call and BEFORE the `user_prompt = render(...)` call, insert:

```python
    # M3b: vector retrieval layer
    character_names = [c.name for c in bundle.characters]
    query_text = beat_text
    if character_names:
        query_text = beat_text + " " + " ".join(character_names)

    retrieved = assemble_retrieval_context(
        db,
        current_chapter_id=chapter_id,
        query_text=query_text,
        router=router,
    )
    bundle.retrieved_chunks = retrieved
```

Then in the `render(...)` call, add the new template variable:

```python
    user_prompt = render(
        "writer/user.j2",
        project=bundle.project,
        world_overview=bundle.world_overview,
        characters=bundle.characters,
        character_states=bundle.character_states,
        relationships=bundle.relationships,
        faction_lore=bundle.faction_lore,
        location_lore=bundle.location_lore,
        recent_chapter_summaries=bundle.recent_chapter_summaries,
        beat_text=beat_text,
        instruction=instruction,
        retrieved_chunks=retrieved,  # M3b new
    )
```

- [ ] **Step 9.4: Extend test fixtures for writer agent tests**

In `tests/test_writer_agent.py`, update the `db_session` fixture to create vec_chunks (same as extractor tests):

```python
@pytest.fixture
def db_session(tmp_path, monkeypatch):
    # ... existing setup ...
    init_db()
    # M3b: create vec_chunks virtual table
    from sqlalchemy import text
    with new_engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024])"
        ))
        conn.commit()
    with new_session() as s:
        yield s
```

Also update `FakeRouter` to include `embed`:

```python
class FakeRouter:
    def __init__(self, events):
        self._events = events
        self.model_for_task = "claude-sonnet-4-6"
    def resolve_model(self, task):
        return ("claude", self.model_for_task)
    def stream(self, request):
        for e in self._events:
            yield e
    # M3b: default embed returns empty (no retrieval in most tests)
    def embed(self, texts, model=None):
        return [[0.1] * 1024] * len(texts)
```

- [ ] **Step 9.5: Add new tests for retrieval integration**

Append to `tests/test_writer_agent.py`:

```python
def test_writer_prompt_includes_retrieved_chunks(db_session):
    """When chunks exist in DB, writer prompt should contain '相关场景预览' section."""
    from app.memory.schema import Chapter, Project
    from app.memory.vectors import insert_chunk
    from app.agents.writer import prepare_generation
    from app.llm.streaming import StreamEvent
    from sqlalchemy import text

    # Seed project + 2 chapters
    p = Project(title="P", genre="g", premise="p")
    db_session.add(p); db_session.flush()
    ch1 = Chapter(project_id=p.id, order_index=1, title="第一章", content="past chapter content")
    ch2 = Chapter(project_id=p.id, order_index=2, title="第二章", content="current chapter")
    db_session.add_all([ch1, ch2]); db_session.flush()

    # Add a chunk to chapter 1 (the past chapter)
    insert_chunk(db_session, chapter_id=ch1.id, chunk_index=0,
                 chunk_type="paragraph", text="past chunk text", char_count=15,
                 embedding=[0.9] * 1024)
    db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="token", text="output"),
        StreamEvent(type="done", input_tokens=10, output_tokens=2, stop_reason="end_turn"),
    ])
    # embed returns a vector close to the chunk's vector
    fake_router.embed = MagicMock(return_value=[[0.9] * 1024])

    prep = prepare_generation(
        db_session, chapter_id=ch2.id, beat_text="test beat",
        instruction="", involved_character_ids=[], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )

    assert "相关场景预览" in prep.user_prompt
    assert "past chunk text" in prep.user_prompt


def test_writer_prompt_omits_section_when_no_chunks(db_session):
    """When no chunks exist, writer prompt should NOT contain '相关场景预览'."""
    from app.memory.schema import Chapter, Project
    from app.agents.writer import prepare_generation
    from app.llm.streaming import StreamEvent

    p = Project(title="P"); db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024])

    prep = prepare_generation(
        db_session, chapter_id=ch.id, beat_text="x", instruction="",
        involved_character_ids=[], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )
    assert "相关场景预览" not in prep.user_prompt


def test_writer_query_includes_character_names(db_session):
    """The embed query should include character names from involved characters."""
    from app.memory.schema import Chapter, Project, Character
    from app.agents.writer import prepare_generation
    from app.llm.streaming import StreamEvent

    p = Project(title="P"); db_session.add(p); db_session.flush()
    c = Character(project_id=p.id, name="李雷", role="protagonist")
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add_all([c, ch]); db_session.commit()

    fake_router = FakeRouter([
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    fake_router.embed = MagicMock(return_value=[[0.5] * 1024])

    prepare_generation(
        db_session, chapter_id=ch.id, beat_text="beat text",
        instruction="", involved_character_ids=[c.id], location_id=None,
        model_task="writer_long", max_tokens=4096, router=fake_router,
    )

    # embed should have been called with a query containing the character name
    call_args = fake_router.embed.call_args
    query = call_args[0][0][0]  # first arg = texts list, first text
    assert "李雷" in query
    assert "beat text" in query
```

- [ ] **Step 9.6: Run tests → verify passes**

```bash
pytest tests/test_writer_agent.py -v
```

Expected: All existing + 3 new PASS.

- [ ] **Step 9.7: Commit**

```bash
git add app/agents/writer.py app/llm/prompts/writer/user.j2 app/memory/retrieval.py \
        tests/test_writer_agent.py
git commit -m "feat(m3b): writer integrates retrieval + '相关场景预览' prompt section"
```

---

## Task 10: SSE context event serialization + final regression

**Files:**
- Modify: `app/agents/writer.py` (`_serialize_context_bundle` to include `retrieved_chunks`)
- Modify: `.env.example` (verify EMBEDDING_* documented)
- Modify: `README.md` (M3b prerequisites)

- [ ] **Step 10.1: Extend `_serialize_context_bundle`**

In `app/agents/writer.py`, find the `_serialize_context_bundle` function. Add `retrieved_chunks` serialization:

```python
def _serialize_context_bundle(bundle: ContextBundle) -> dict:
    """Full serialization for the SSE context event."""
    return {
        "project": { ... },  # existing
        "world_overview": { ... },  # existing
        "characters": [ ... ],  # existing
        "relationships": [ ... ],  # existing
        "faction_lore": [ ... ],  # existing
        "location_lore": [ ... ],  # existing
        "recent_chapter_summaries": [ ... ],  # existing
        # M3b: retrieved chunks from vector search
        "retrieved_chunks": [
            {
                "chunk_id": rc.chunk_id,
                "chapter_id": rc.chapter_id,
                "chapter_title": rc.chapter_title,
                "chunk_type": rc.chunk_type,
                "text": rc.text,
                "score": round(rc.score, 4),
            }
            for rc in bundle.retrieved_chunks
        ],
    }
```

- [ ] **Step 10.2: Run all backend tests**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
pytest -v 2>&1 | tail -15
```

Expected: All pass. Total should be prior count + new M3b tests.

- [ ] **Step 10.3: Run frontend tests (should be unchanged)**

```bash
cd /Users/bugx/novelAI/web && npm test 2>&1 | tail -5
```

Expected: 51 tests pass (no change).

- [ ] **Step 10.4: Run E2E tests**

```bash
npm run test:e2e 2>&1 | tail -15
```

Expected: All 5 E2E pass (M2b + M3a). M3b doesn't change HTTP contract.

- [ ] **Step 10.5: Manual smoke test**

```bash
cd /Users/bugx/novelAI && source .venv/bin/activate
# Ensure DB is migrated
alembic upgrade head
# Start backend
uvicorn app.main:app --port 8005 &
sleep 2
# Verify vec extension loaded
sqlite3 data/novelai.db "SELECT vec_version()"
# Verify tables exist
sqlite3 data/novelai.db "SELECT name FROM sqlite_master WHERE name IN ('vec_chunks','chunk_meta') ORDER BY name"
kill %1
```

Expected: vec_version prints; both tables exist.

- [ ] **Step 10.6: Update README**

In `/Users/bugx/novelAI/README.md`, after the existing "## 数据库迁移（Alembic）" section, add:

```markdown
## 向量检索（M3b）

M3b 引入了基于 sqlite-vec 的语义检索层。Writer Agent 生成时会自动召回过往章节中与本段情节相关的场景。

### 前置条件

1. `pip install sqlite-vec`（已在 pyproject.toml 中）
2. `NOVELAI_LLM_PROVIDER=openai`（或兼容端点）—— Anthropic 不提供 embedding API
3. `.env` 中配置 `EMBEDDING_MODEL`（默认 text-embedding-3-small）

### 配置

```bash
EMBEDDING_MODEL=text-embedding-3-small     # 模型名
EMBEDDING_DIMENSIONS=1536                   # 维度（必须和模型一致）
RETRIEVAL_TOP_K=5                           # 召回数量
RETRIEVAL_THRESHOLD=0.4                     # cosine 阈值
```

### 切换 embedding 模型

如果切换 `EMBEDDING_MODEL`（维度变化），需手动清空向量表并重新索引：

```bash
sqlite3 data/novelai.db "DELETE FROM vec_chunks; DELETE FROM chunk_meta;"
# 然后重新 finalize 每个章节
```
```

- [ ] **Step 10.7: Commit**

```bash
git add app/agents/writer.py README.md
git commit -m "feat(m3b): SSE context event includes retrieved_chunks + README docs"
```

---

## Self-Review

### Spec coverage

| Spec § | Coverage |
|---|---|
| §1.3 Embedding 模型 = OpenAI-compatible | Task 5 (provider embed) + Task 6 (router) |
| §1.3 Chunking = 段落 + >800 切 | Task 3 |
| §1.3 finalize 同步 + 重试覆盖 | Task 8 |
| §1.3 Writer 默认注入 | Task 9 |
| §1.3 top-5 + cosine > 0.4 | Task 7 (retrieval) |
| §1.3 查询 = beat + 人物名 | Task 9 |
| §1.3 两表分离 | Task 2 (schema + migration) |
| §2 文件结构 | All tasks |
| §3 vec_chunks + chunk_meta + sqlite-vec | Task 1 + Task 2 |
| §3.5 sqlite-vec 加载 | Task 1 |
| §3.7 Alembic migration | Task 2 |
| §4 chunking 纯函数 | Task 3 |
| §4 Provider.embed | Task 5 |
| §4 ModelRouter.embed | Task 6 |
| §4 配置扩展 | Task 6 |
| §5 retrieval | Task 7 |
| §5 ContextBundle 扩展 | Task 9 |
| §5 Writer 集成 | Task 9 |
| §5 user.j2 模板 | Task 9 |
| §5 Extractor 集成 | Task 8 |
| §5 vectors.py CRUD | Task 4 |
| §6 SSE context 扩展 | Task 10 |
| §6 .env 配置 | Task 6 + Task 10 |
| §7 测试 | All tasks TDD |
| §8 验收清单 1-20 | Tasks 1-10 |

All covered.

### Placeholder scan

No TBD/TODO. All code blocks complete.

### Type consistency

- `Chunk(text, chunk_type, char_count)` — Task 3 (definition), Task 4 (used via chunk_markdown in Task 8), Task 8 (used in extractor)
- `RetrievedChunk(chunk_id, chapter_id, chapter_title, chunk_type, text, score)` — Task 7 (definition), Task 9 (used in writer), Task 10 (serialized in SSE)
- `insert_chunk(db, *, chapter_id, chunk_index, chunk_type, text, char_count, embedding)` — Task 4 (definition), Task 8 (extractor), Task 9 (writer test fixture)
- `delete_chapter_chunks(db, chapter_id)` — Task 4 (definition), Task 8 (extractor)
- `assemble_retrieval_context(db, *, current_chapter_id, query_text, router, top_k, threshold)` — Task 7 (definition), Task 9 (writer calls)
- `_serialize_vec(vec)` — Task 4 (vectors.py), Task 7 (retrieval.py) — **duplicated intentionally** (different modules, small function, avoids cross-module dependency)
- `ContextBundle.retrieved_chunks` — Task 9 (added), Task 10 (serialized)

No inconsistencies.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-m3b-vector-retrieval.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
