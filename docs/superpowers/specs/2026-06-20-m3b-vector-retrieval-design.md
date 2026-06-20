# NovelAI M3b — 向量检索层设计文档

- **日期**：2026-06-20
- **状态**：草案（待用户审阅）
- **范围**：M3b = 章节内容 chunking + embedding + sqlite-vec 向量存储 + Writer 生成时自动召回相关过往场景
- **依赖**：M1（地基）、M2a（写作管线）、M2b（前端编辑器）、M3a（章节摘要 + 硬事实抽取）已完成；Alembic 已引入（M3a 后）

---

## 1. 目标与非目标

### 1.1 目标

让 Writer Agent 在生成长篇小说时**不再"失忆"**：自动从过往已定稿章节中召回与本段情节语义相关的场景/对话片段，注入 prompt 供参考，保证前后一致。

具体：

1. Extractor 在 finalize 章节时，除 M3a 的摘要 + 硬事实抽取外，**额外**做：
   - 把章节正文按段落切成 chunks（>800 字再按句号细分）
   - 启发式分类 chunk_type（dialogue / description / paragraph）
   - 调 embedding API 把所有 chunks 转为向量
   - 写入 `vec_chunks` 虚拟表（sqlite-vec）+ `chunk_meta` 元数据表
2. Writer 在生成前，用 `beat_text + 涉及人物名字` 作 embedding 查询，sqlite-vec KNN 检索 top-K=5 个相关 chunks，cosine > 0.4 过滤，排除当前章节
3. 检索结果作为 prompt 的"相关场景预览"段注入（在前情提要后、本次任务前）
4. SSE `context` 事件扩展含 `retrieved_chunks` 字段，让 StreamView 显示检索结果

### 1.2 非目标（M3b 不做）

- ContextBudget 自动裁剪（常驻层 + 检索层总 token 控制）— M3c+
- HNSW 索引（大规模数据优化）— M3c+
- 多查询融合 / 重排序 / 混合检索（向量 + BM25）— v2+
- chunk_type 过滤检索（用户选只召回对话）— M3c+
- 异步 embedding（M3b finalize 同步做）— M3d
- 真实 embedding API 集成测试（全部 mock）
- 维度变更自动清空（文档建议手动 `DELETE`）

### 1.3 关键决策

| # | 决策 | 理由 |
|---|---|---|
| Embedding 模型 | 复用 OpenAI-compatible endpoint（`.env` 加 `EMBEDDING_MODEL`） | 与 Writer/Extractor 同一套 provider；统一计费/代理 |
| Chunking 策略 | 段落（双换行）+ >800 字按句号切 | 保留段落语义；避免超长段落检索不细 |
| Embedding 触发时机 | finalize 同步做；失败回滚；重试覆盖 | 与 M3a finalize 原子语义一致；用户不需额外操作 |
| Writer 检索注入 | 默认自动注入（不可关闭） | 检索是默认价值，不该需用户手动启用 |
| 检索范围 + top-K | top-5 + cosine > 0.4 阈值；排除当前章节 | 5 chunks × ~200 tokens ≈ 1k token 检索层；不挤常驻层 |
| 查询构造 | beat_text + 涉及人物名字（空格拼接） | 让检索召回这些人物过去出现过的场景 |
| sqlite-vec 集成 | 两表分离（vec_chunks 虚拟表 + chunk_meta 元数据表） | 虚拟表不友好支持 TEXT；分表后 JOIN 简单 |
| 维度可配 | `EMBEDDING_DIMENSIONS` 默认 1536 | 不同模型维度不同（512/768/1024/1536） |
| Claude provider embed | 抛 NotImplementedError | Anthropic 不提供 embedding API；用户应明确切到 openai provider |

---

## 2. 模块划分与文件结构

```
app/
├── memory/
│   ├── schema.py                # 修改：加 ChunkMeta ORM
│   ├── session.py               # 修改：connection 钩子加载 vec0 扩展
│   └── vectors.py               # 新增：vec_chunks 虚拟表 CRUD + delete/insert helpers
├── llm/
│   ├── base.py                  # 修改：LLMProvider 协议加 embed() 方法
│   ├── router.py                # 修改：ModelRouter 加 embed() 转发
│   ├── chunking.py              # 新增：Markdown → chunks 纯函数
│   └── providers/
│       ├── openai.py            # 修改：实现 embed()（embeddings endpoint）
│       └── claude.py            # 修改：embed() 抛 NotImplementedError
├── agents/
│   ├── extractor.py             # 修改：finalize 后追加 chunking + embedding
│   ├── writer.py                # 修改：prepare_generation 调 retrieval 注入检索层
│   └── retrieval.py             # 新增：检索层（query embedding + KNN + 阈值过滤）
├── memory/retrieval.py          # 修改：ContextBundle 加 retrieved_chunks 字段
├── llm/prompts/writer/user.j2   # 修改：新增"相关场景预览"段
├── config.py                    # 修改：加 embedding_model / dimensions / top_k / threshold 配置
└── (无新增 API 端点)

tests/
├── test_chunking.py             # 新增
├── test_vectors.py              # 新增
├── test_retrieval.py            # 新增
├── test_extractor_agent.py      # 修改：扩展覆盖 chunk + embed
└── test_writer_agent.py         # 修改：扩展覆盖检索层注入

alembic/versions/
└── <hash>_add_vec_chunks.py     # 新增：vec_chunks 虚拟表 + chunk_meta 表
```

### 2.1 职责边界

- `llm/chunking.py`：纯函数，Markdown → `list[Chunk]`。**不调 LLM，不读写 DB**。
- `memory/vectors.py`：sqlite-vec 虚拟表管理。CRUD：`delete_chapter_chunks`、`insert_chunk`。**不调 LLM**。
- `agents/retrieval.py`：检索层编排。`assemble_retrieval_context` → `list[RetrievedChunk]`。调 LLM provider.embed() + vectors KNN。**不写 DB**。
- `agents/extractor.py`：M3a 既有 + 新增 chunking + embedding。仍然原子事务（embedding 失败整个 finalize 回滚）。
- `agents/writer.py`：M2a 既有 + 调 retrieval。把结果加到 `ContextBundle.retrieved_chunks`。

### 2.2 依赖方向

沿用 M2a/M3a 单向依赖：`api → agents → memory → llm → DB`。retrieval 是 agents 层（不是 memory 层），因为它调 LLM。

---

## 3. 数据库变更

### 3.1 新增虚拟表：`vec_chunks`

sqlite-vec 用 SQLite 虚拟表机制。SQLAlchemy 不直接支持虚拟表 DDL，**走 raw SQL**：

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
  embedding FLOAT[1024]   -- 默认维度；可被 EMBEDDING_DIMENSIONS 覆盖
);
```

**注意**：sqlite-vec 虚拟表只存向量 + rowid。chunks 元数据存在独立的 `chunk_meta` 表，通过 `chunk_id` 关联。

### 3.2 新增元数据表：`chunk_meta`

```sql
chunk_meta(
  id INTEGER PRIMARY KEY,              -- 同时是 vec_chunks.rowid
  chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,        -- 章节内顺序（0,1,2...）
  chunk_type VARCHAR(20) NOT NULL,     -- 'paragraph' / 'dialogue' / 'description'
  text TEXT NOT NULL,                  -- chunk 原文
  char_count INTEGER NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE(chapter_id, chunk_index)
);

CREATE INDEX idx_chunk_chapter ON chunk_meta(chapter_id);
```

### 3.3 为什么分两表

sqlite-vec 虚拟表查询接口受限（只支持 KNN 检索），不能存 TEXT/JSON 元数据。标准做法是：虚拟表存向量 + rowid，元数据表用 rowid JOIN。检索时先 KNN 拿到 top-K rowid，再 JOIN chunk_meta 取 text 和上下文。

### 3.4 ChunkMeta ORM

```python
# app/memory/schema.py 追加
from sqlalchemy import UniqueConstraint

class ChunkMeta(Base):
    __tablename__ = "chunk_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)

    __table_args__ = (
        UniqueConstraint("chapter_id", "chunk_index", name="uq_chunk_chapter_index"),
        Index("idx_chunk_chapter", "chapter_id"),
    )
```

### 3.5 sqlite-vec 扩展加载

`app/memory/session.py` 的 `_build_engine` 加 connection 钩子：

```python
def _build_engine(db_path: Path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

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

    return engine
```

### 3.6 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| 向量维度 `FLOAT[1024]` | 启动时按 `EMBEDDING_DIMENSIONS` 配置 | 不同模型维度不同；硬编码会爆 |
| 两表分离（vec_chunks + chunk_meta） | 不把 text 塞进虚拟表 | sqlite-vec 虚拟表不友好支持 TEXT |
| `chunk_index` UNIQUE 约束 | (chapter_id, chunk_index) 唯一 | 防止重复 finalize 写重复 row |
| `chunk_type` 启发式分类 | paragraph / dialogue / description | 简单规则；M3c 软事实抽取可按 type 选择性召回 |
| `vec_chunks` 不用 ORM | 用 raw SQL + sqlite-vec API | SQLAlchemy 不支持虚拟表 ORM mapping |
| 删除旧 chunks 重索引 | finalize 时 `delete_chapter_chunks` + 重插 | 沿用 M3a "重抽覆盖"语义 |
| Migration 用 raw SQL | Alembic `op.execute()` 直接写虚拟表 DDL | 虚拟表 DDL 不能 autogenerate |

### 3.7 迁移策略

M3b 第一次真实使用 Alembic：

```bash
# 1. 修改 schema.py 加 ChunkMeta
# 2. 生成迁移
alembic revision --autogenerate -m "add chunk_meta + vec_chunks virtual table"
# 3. 检查生成的迁移文件，手动加 vec_chunks 虚拟表 DDL（autogenerate 不会）
# 4. 应用
alembic upgrade head
```

迁移文件需要手动追加：

```python
def upgrade():
    # autogenerate 产生的 chunk_meta 表
    op.create_table("chunk_meta", ...)
    op.create_index("idx_chunk_chapter", ...)
    op.create_unique_constraint("uq_chunk_chapter_index", ...)

    # 手动追加：vec_chunks 虚拟表
    op.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding FLOAT[1024])")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vec_chunks")
    op.drop_table("chunk_meta")
```

---

## 4. Chunking + Embedding 设计

### 4.1 Chunking 纯函数

`app/llm/chunking.py`：

```python
import re
from dataclasses import dataclass

MAX_PARAGRAPH_CHARS = 800


@dataclass
class Chunk:
    text: str
    chunk_type: str  # 'paragraph' | 'dialogue' | 'description'
    char_count: int


def chunk_markdown(content: str) -> list[Chunk]:
    """Markdown 章节内容 → list[Chunk]。

    策略：
    1. 按双换行切段落（Markdown 自然单元）
    2. 跳过空段落（仅空白）
    3. 段落 > 800 字：按句号再切，每片 ≤ 800
    4. chunk_type 启发式分类：
       - 含 " 或 「 或 『 ≥ 3 次 → 'dialogue'
       - 含感官/外貌/动作词（看、看见、闻、听见、触摸、走、跑...）≥ 2 次 → 'description'
       - 其他 → 'paragraph'
    """
    if not content or not content.strip():
        return []
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    for para in paragraphs:
        if len(para) <= MAX_PARAGRAPH_CHARS:
            chunks.append(_classify(para))
        else:
            sentences = _split_sentences(para)
            buffer = ""
            for sent in sentences:
                if len(buffer) + len(sent) > MAX_PARAGRAPH_CHARS and buffer:
                    chunks.append(_classify(buffer))
                    buffer = sent
                else:
                    buffer += sent
            if buffer:
                chunks.append(_classify(buffer))
    return chunks


def _split_sentences(text: str) -> list[str]:
    """按 。！？.!? 切句，保留标点。"""
    parts = re.split(r"(?<=[。！？.!?])", text)
    return [p for p in parts if p]


def _classify(text: str) -> Chunk:
    dialogue_marks = (
        text.count('"') + text.count('"') + text.count('"')
        + text.count('「') + text.count('」')
        + text.count('『') + text.count('』')
    )
    if dialogue_marks >= 3:
        ctype = "dialogue"
    else:
        description_markers = [
            "看", "看见", "看到", "闻", "听见", "听到",
            "摸", "触摸", "走", "跑", "坐", "站",
        ]
        if sum(text.count(m) for m in description_markers) >= 2:
            ctype = "description"
        else:
            ctype = "paragraph"
    return Chunk(text=text, chunk_type=ctype, char_count=len(text))
```

### 4.2 Embedding Provider 接口

`app/llm/base.py` 加 `embed()` 方法：

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...
    def stream(self, request: LLMRequest, model: str) -> Iterator[StreamEvent]: ...
    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
```

### 4.3 OpenAIProvider.embed 实现

`app/llm/providers/openai.py`：

```python
def embed(self, texts: list[str], model: str) -> list[list[float]]:
    """OpenAI-compatible embeddings endpoint.

    Works with: OpenAI text-embedding-3-small/large, DashScope text-embedding-v2,
    Ollama bge-m3, vLLM, etc.
    """
    resp = self._client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]
```

### 4.4 ClaudeProvider.embed 实现

`app/llm/providers/claude.py`：

```python
def embed(self, texts: list[str], model: str) -> list[list[float]]:
    """Anthropic 不提供 embedding API。"""
    raise NotImplementedError(
        "Anthropic does not provide embeddings API. "
        "Set NOVELAI_LLM_PROVIDER=openai or configure a separate embedding endpoint."
    )
```

### 4.5 ModelRouter.embed 转发

`app/llm/router.py`：

```python
def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
    """Embed texts using configured provider.

    M3b 决策：复用 writer provider（用户已配置的 OpenAI-compatible endpoint）。
    model 从 settings.embedding_model 取，默认 None 时 fallback 到 'text-embedding-3-small'。
    """
    provider_name = self.default_provider
    provider = self._get_provider(provider_name)
    embed_model = model or settings.embedding_model or "text-embedding-3-small"
    return provider.embed(texts, embed_model)
```

### 4.6 配置扩展

`app/config.py`：

```python
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

### 4.7 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| Chunk 策略 | 段落 + >800 字再切句 | 保留段落语义 |
| chunk_type 启发式 | dialogue/description/paragraph | 不调 LLM 分类（YAGNI）；规则简单 |
| Embedding 批处理 | 一次 API 调用传所有 chunks（上限 50） | OpenAI embeddings 支持批量；省 API 调用 |
| 失败处理 | embed() 抛异常 → extractor 整体回滚 | finalize 原子 |
| Claude provider 不支持 embed | 抛 NotImplementedError + 清晰错误信息 | 用户切到 openai provider 即可 |
| 维度可配 | settings.embedding_dimensions | 不同模型维度不同 |
| 阈值可配 | settings.retrieval_threshold | 用户可调 |

---

## 5. 检索层 + Writer 集成

### 5.1 `agents/retrieval.py`：检索编排

```python
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
    score: float  # cosine 相似度


def assemble_retrieval_context(
    db: Session,
    *,
    current_chapter_id: int,
    query_text: str,
    router: ModelRouter = default_router,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[RetrievedChunk]:
    """检索与 query_text 相关的过往章节 chunks。

    流程：
    1. 用 router.embed() 把 query_text 转向量
    2. sqlite-vec KNN 检索 top-K*2（备阈值过滤）
    3. 过滤 score < threshold
    4. 排除 current_chapter_id 的 chunks（当前章节已在常驻层）
    5. JOIN chunk_meta + chapter 拿元数据
    """
    k = top_k or settings.retrieval_top_k
    th = threshold if threshold is not None else settings.retrieval_threshold

    # 1. Embed query
    query_vectors = router.embed([query_text])
    query_vec = query_vectors[0]

    # 2. KNN search via sqlite-vec (raw SQL)
    knn_sql = sql_text(
        "SELECT rowid, distance "
        "FROM vec_chunks "
        "WHERE embedding MATCH :vec AND k = :k "
        "ORDER BY distance"
    )
    rows = db.execute(
        knn_sql, {"vec": _serialize_vec(query_vec), "k": k * 2}
    ).fetchall()

    # 3. 过滤阈值
    candidates: list[tuple[int, float]] = []
    for rowid, distance in rows:
        score = 1.0 - distance  # cosine similarity
        if score < th:
            continue
        candidates.append((rowid, score))
        if len(candidates) >= k:
            break

    if not candidates:
        return []

    # 4. JOIN chunk_meta + chapter，排除当前章节
    rowids = [c[0] for c in candidates]
    score_map = {c[0]: c[1] for c in candidates}
    # 用 IN 子句（SQLite 限制 999 个参数，M3b 单次 K*2=10 个无问题）
    placeholders = ",".join(str(int(rid)) for rid in rowids)
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

    # 5. 按相似度降序
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:k]


def _serialize_vec(vec: list[float]) -> bytes:
    """Serialize vector as sqlite-vec expected format (raw float32 little-endian)."""
    return struct.pack(f"<{len(vec)}f", *vec)
```

### 5.2 ContextBundle 扩展

`app/memory/retrieval.py` 的 `ContextBundle` 加新字段：

```python
@dataclass
class ContextBundle:
    # ... existing fields (project, world_overview, characters, ...) ...
    retrieved_chunks: list["RetrievedChunk"] = field(default_factory=list)
```

`RetrievedChunk` 从 `app.agents.retrieval` 导入（避免循环依赖；`memory.retrieval` 只引用类型）。

### 5.3 Writer Agent 调用检索

`app/agents/writer.py` 的 `prepare_generation` 加检索步骤：

```python
# M2a: 常驻层
bundle = assemble_context(...)

# M3b 新增：检索层
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

# M2a: 渲染 prompt（user.j2 模板新增检索层段落）
user_prompt = render(
    "writer/user.j2",
    project=bundle.project,
    # ... existing ...
    retrieved_chunks=retrieved,  # 新增
)
```

### 5.4 Writer user.j2 模板新增段落

在 M2a 的"前情提要"段之后、"本次写作任务"段之前，插入：

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

### 5.5 Extractor Agent 集成 chunking + embedding

`app/agents/extractor.py` 的 `extract_chapter` 在事务内、commit 前追加：

```python
# M3a existing: delete old pending, write generation_log, insert pending, update chapter

# M3b 新增：chunking + embedding
chunks = chunk_markdown(chapter.content or "")
if chunks:
    BATCH = 50
    all_embeddings: list[list[float]] = []
    for i in range(0, len(chunks), BATCH):
        batch_texts = [c.text for c in chunks[i:i + BATCH]]
        all_embeddings.extend(router.embed(batch_texts))

    # 删旧 chunks
    delete_chapter_chunks(db, chapter_id)

    # 写新 chunks
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

db.commit()  # 与 M3a 写入一起提交（原子）
```

### 5.6 vectors.py CRUD helpers

`app/memory/vectors.py`：

```python
import struct
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.memory.schema import ChunkMeta


def delete_chapter_chunks(db: Session, chapter_id: int) -> None:
    """删除章节的所有 chunks（chunk_meta + vec_chunks 两表）。"""
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
    """插入一条 chunk（chunk_meta 拿 rowid 后写 vec_chunks）。"""
    meta = ChunkMeta(
        chapter_id=chapter_id,
        chunk_index=chunk_index,
        chunk_type=chunk_type,
        text=text,
        char_count=char_count,
    )
    db.add(meta)
    db.flush()  # 拿 meta.id
    db.execute(
        sql_text(
            "INSERT INTO vec_chunks(rowid, embedding) VALUES (:id, :vec)"
        ),
        {"id": meta.id, "vec": _serialize_vec(embedding)},
    )
    return meta.id


def _serialize_vec(vec: list[float]) -> bytes:
    """Serialize vector as raw float32 little-endian bytes."""
    return struct.pack(f"<{len(vec)}f", *vec)
```

### 5.7 关键设计

| 决策 | 选择 | 理由 |
|---|---|---|
| 查询 = beat + 人物名 | 字符串拼接（空格分隔） | Q6 决议；最简单 |
| KNN `LIMIT k*2` | 多取一倍以备阈值过滤 | 严格 K 后过滤可能不够 K |
| 排除当前章节 chunks | SQL `WHERE chapter_id != current` | 当前章节已在 prompt 主体，避免重复 |
| 检索层 prompt 段位置 | "前情提要"后、"本次任务"前 | 语义上属于"上下文"部分 |
| 相似度显示给 LLM | `%.2f` 格式 | 让 LLM 知道哪些是高/低相关 |
| sqlite-vec 序列化 | raw float32 LE bytes | sqlite-vec 推荐格式 |
| Extractor 写 chunks | 与 M3a pending 写入同一事务 | Q3 决议：finalize 原子 |
| Embedding batch 50 | OpenAI API 限制 + 防超时 | 长 chapter 自动分批 |

---

## 6. API 契约

**M3b 无新增 HTTP 端点**——完全后端内部扩展。

### 6.1 不变的契约

| 端点 | 变化 |
|---|---|
| `POST /api/chapters/{id}/finalize` | 响应字段不变，仍返回 `{chapter_id, summary, pending_created, log_id}`。内部多做了 chunking + embedding；耗时增加 1-3s。 |
| `POST /api/chapters/{id}/generate` (SSE) | 响应字段不变。`context` 事件多一个 `retrieved_chunks` 字段；`token` / `done` 不变。 |
| `GET /api/pending-updates` / `accept` / `reject` | 不变 |
| `GET /api/generation-logs/{id}` | 不变（user_prompt 字段会含新"相关场景预览"段，但结构同） |

### 6.2 SSE context 事件扩展

`context` 事件的 `context_bundle` JSON 新增字段（**可选**，没检索结果时为 `[]`）：

```json
{
  "context_bundle": {
    "project": {...},
    "world_overview": {...},
    "characters": [...],
    "relationships": [],
    "faction_lore": [...],
    "location_lore": [...],
    "recent_chapter_summaries": [...],
    "retrieved_chunks": [
      {
        "chunk_id": 42,
        "chapter_id": 3,
        "chapter_title": "第二章",
        "chunk_type": "dialogue",
        "text": "韩梅递过来一杯酒...",
        "score": 0.78
      }
    ]
  }
}
```

**前端无需改动**——M2b 的 StreamView 已经在 `<details>` 里渲染整个 `context_bundle`（`JSON.stringify`），新字段自动显示。

### 6.3 内部接口（非 HTTP）

```python
# app/llm/base.py
class LLMProvider(Protocol):
    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

# app/llm/router.py
class ModelRouter:
    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]: ...

# app/llm/chunking.py
def chunk_markdown(content: str) -> list[Chunk]: ...

# app/memory/vectors.py
def delete_chapter_chunks(db: Session, chapter_id: int) -> None: ...
def insert_chunk(db: Session, *, chapter_id: int, chunk_index: int, chunk_type: str, text: str, char_count: int, embedding: list[float]) -> int: ...

# app/agents/retrieval.py
def assemble_retrieval_context(db: Session, *, current_chapter_id: int, query_text: str, router: ModelRouter, top_k: int | None = None, threshold: float | None = None) -> list[RetrievedChunk]: ...
```

### 6.4 配置扩展（`.env`）

新增 4 个可选环境变量：

```
# Embedding 配置（M3b）
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
RETRIEVAL_TOP_K=5
RETRIEVAL_THRESHOLD=0.4
```

`.env.example` 加上对应文档；README 加一段说明 M3b 需要 `NOVELAI_LLM_PROVIDER=openai`（或兼容端点）。

### 6.5 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 不加新端点 | finalize / generate 内部扩展 | 保持 API 表面小；客户端无需改 |
| context 事件加 `retrieved_chunks` | SSE payload 扩展 | 让 StreamView 的预览能显示检索结果 |
| 不加"重建索引"端点 | finalize 自带覆盖 | 简化；用户改 finalize 即重索引 |
| 不加"禁用检索"开关 | Writer 总是调 retrieval | Q4 决议：默认开 |
| Claude provider 不支持 embed 时直接报错 | 不静默 fallback | 用户应明确知道切 provider |

---

## 7. 测试策略

### 7.1 测试金字塔

```
                ┌─────────────────┐
                │ Playwright E2E  │  不新增——finalize-pending 已覆盖关键流程
                └─────────────────┘
            ┌─────────────────────────┐
            │ Agent + 检索集成测试    │  mock LLMProvider.embed，验检索流程
            └─────────────────────────┘
        ┌───────────────────────────────┐
        │ 单元测试                      │
        │ - chunk_markdown 纯函数       │
        │ - vectors CRUD（sqlite-vec）  │
        │ - retrieval 检索逻辑          │
        └───────────────────────────────┘
```

### 7.2 单元测试：chunking

**`tests/test_chunking.py`**（纯函数，不依赖 DB / LLM）：

| 测试 | 验证 |
|---|---|
| `test_chunk_single_paragraph` | 单段落 → 1 个 chunk，type=paragraph |
| `test_chunk_multiple_paragraphs` | 3 个双换行分段 → 3 个 chunks |
| `test_chunk_empty_content` | 空字符串 → `[]` |
| `test_chunk_whitespace_only` | 仅空白 → `[]` |
| `test_chunk_long_paragraph_split` | 1500 字段落 → 切成 ≤800 字的多个 chunks |
| `test_chunk_dialogue_detection` | 含 3+ 引号 → chunk_type=dialogue |
| `test_chunk_description_detection` | 含 2+ 感官词 → chunk_type=description |
| `test_chunk_chinese_punctuation` | 中文句号「。」也能切长段 |
| `test_chunk_preserves_text` | chunk.text 与原文一致（不丢字符） |
| `test_chunk_char_count_correct` | char_count == len(text) |

### 7.3 单元测试：vectors CRUD

**`tests/test_vectors.py`**（依赖 sqlite-vec 扩展加载；用 tmp_path DB）：

| 测试 | 验证 |
|---|---|
| `test_insert_chunk_returns_id` | insert_chunk 返回 chunk_meta.id |
| `test_insert_chunk_writes_vec_table` | vec_chunks 表有对应 rowid + embedding |
| `test_delete_chapter_chunks_removes_both_tables` | delete 后 chunk_meta + vec_chunks 都没该 chapter_id |
| `test_delete_chapter_chunks_preserves_other_chapters` | 只删指定 chapter_id，其他保留 |
| `test_delete_nonexistent_chapter_noop` | chapter_id 不存在不报错 |

### 7.4 单元测试：retrieval

**`tests/test_retrieval.py`**（mock `router.embed`，真实 sqlite-vec KNN）：

| 测试 | 验证 |
|---|---|
| `test_retrieval_returns_relevant_chunks` | 准备 3 chunks，query embedding 接近其中 1 个 → 返回该 chunk |
| `test_retrieval_threshold_filters_low_score` | score < 0.4 的不返回 |
| `test_retrieval_excludes_current_chapter` | 当前 chapter_id 的 chunks 不在结果 |
| `test_retrieval_top_k_limits_count` | top_k=2 → 最多 2 条 |
| `test_retrieval_empty_when_no_chunks` | 表里无 chunks → `[]` |
| `test_retrieval_sorts_by_score_desc` | 返回按 score 降序 |
| `test_retrieval_joins_chapter_title` | 结果含 chapter_title |
| `test_retrieval_uses_settings_defaults` | 不传 top_k/threshold → 从 settings 取 |

### 7.5 集成测试：Extractor + chunking + embedding

**扩展 `tests/test_extractor_agent.py`**（mock router.complete + router.embed）：

| 测试 | 验证 |
|---|---|
| `test_extract_creates_chunks` | M3a 抽取后 chunk_meta 有 N 条（N=段落数）|
| `test_extract_writes_embeddings` | vec_chunks 表有 N 条对应 rowid |
| `test_extract_rerun_overwrites_chunks` | 重新 finalize 后旧 chunks 被删，新 chunks 入库 |
| `test_extract_no_content_no_chunks` | chapter.content 为空 → 不写 chunks（不报错） |
| `test_extract_embedding_failure_rolls_back` | router.embed raise → 整个 finalize 回滚 |
| `test_extract_batch_split_for_long_chapter` | 60 段落 → embed 调用 ≥ 2 次（batch=50） |

### 7.6 集成测试：Writer + retrieval

**扩展 `tests/test_writer_agent.py`**：

| 测试 | 验证 |
|---|---|
| `test_writer_prompt_includes_retrieved_chunks` | DB 准备 chunks；prepare_generation → user_prompt 含"相关场景预览"段 |
| `test_writer_prompt_omits_section_when_no_chunks` | DB 空 → user_prompt 不含"相关场景预览"段 |
| `test_writer_query_includes_character_names` | involved_characters → embed 调用参数含人物名 |
| `test_writer_skips_current_chapter_chunks` | DB 有当前 chapter_id 的 chunks → 不在 prompt 里 |

### 7.7 不测什么（YAGNI）

- 真实 embedding API（所有测试 mock embed()）
- 检索内容质量（人工验收）
- 不同 embedding 模型对比（M3c+ benchmark）
- 多用户并发检索
- 大规模索引性能（10 万 chunks 级）

### 7.8 覆盖率目标

| 模块 | 目标 |
|---|---|
| `app/llm/chunking.py` | 100%（纯函数） |
| `app/memory/vectors.py` | >90% |
| `app/agents/retrieval.py` | >85% |
| `app/agents/extractor.py`（扩展） | 维持 >90% |
| `app/agents/writer.py`（扩展） | 维持 >90% |

---

## 8. M3b 验收清单

| # | 验收项 | 验证方法 |
|---|---|---|
| 1 | `pip install sqlite-vec` 后服务能启动 | `uvicorn app.main:app` 不报错 |
| 2 | DB 启动时自动加载 vec0 扩展 | `SELECT vec_version()` SQL 返回版本 |
| 3 | Alembic migration 创建 `vec_chunks` 虚拟表 + `chunk_meta` 表 | `alembic upgrade head` + sqlite3 直查 |
| 4 | `chunk_markdown("段落1\n\n段落2")` 返回 2 个 Chunk | 单测 |
| 5 | 长段落（>800 字）按句号切 | 单测 |
| 6 | `chunk_type` 启发式分类正确 | 单测 |
| 7 | `OpenAIProvider.embed()` 返回 list[list[float]] | 单测（mock client） |
| 8 | `ClaudeProvider.embed()` 抛 NotImplementedError | 单测 |
| 9 | Extractor finalize 后 chunk_meta + vec_chunks 都有数据 | 集成测试 + sqlite3 直查 |
| 10 | 重新 finalize 覆盖旧 chunks（保留其他章节） | 集成测试 |
| 11 | Embedding 失败 → finalize 整体回滚 | 集成测试 |
| 12 | 长章节（>50 段）embedding 分批调用 | 集成测试 |
| 13 | Writer 生成时 prompt 含"相关场景预览"段（如果有 chunks） | 集成测试 |
| 14 | Writer 检索排除当前章节 chunks | 集成测试 |
| 15 | 检索 top-K=5 + threshold=0.4 过滤 | 集成测试 |
| 16 | SSE context 事件包含 `retrieved_chunks` 字段 | E2E（手动） |
| 17 | Claude provider 下触发生成 → SSE error 事件（NotImplementedError） | 单测 + 集成 |
| 18 | `.env.example` 含 4 个新配置项 | 文件检查 |
| 19 | 全部后端测试通过 | `pytest -v` |
| 20 | 全部前端测试通过（无变化） | `npm test` |

---

## 9. 待定 / 开放问题

1. **sqlite-vec 安装**：`pip install sqlite-vec` 在 macOS / Linux 都有预编译 wheel；Windows 用户需自编译。M3b 文档加一行说明。
2. **维度变更时的迁移**：用户切换 embedding 模型（如从 1536 维 text-embedding-3-small 换到 1024 维 bge-m3），`vec_chunks` 表维度不匹配，所有现有 chunks 失效。M3b 不自动处理——文档建议用户 `DELETE FROM vec_chunks + chunk_meta` 后重新 finalize 所有章节。M3c+ 可加"维度变更检测"自动清空。
3. **`chunk_type` 用途**：M3b 不基于 chunk_type 过滤检索，仅作为元数据存储。M3c 软事实抽取可能按 type 选择性召回（如只召回 dialogue 保持语言风格）。
4. **检索层 token 预算**：M3b 不实现自动裁剪。如果 5 chunks × 500 字 = 2500 字 ≈ 4000 tokens，加上常驻层可能超 context window。M3c+ 加 ContextBudget 自动降级。
5. **多语言检索**：当前 embedding 模型对中文小说支持较好（DashScope / bge-m3）。跨语言（中英混写）效果取决于模型——M3b 不专门处理。
6. **索引性能**：单机 SQLite + sqlite-vec，单项目 100 章节约 1000 chunks，KNN 检索 < 50ms。M3b 不做索引优化。如果项目规模到 1000 章，需要 HNSW 索引（M3c+）。

---

## 10. 未来扩展（v2+，不在 M3b 范围）

- **ContextBudget**：常驻层 + 检索层总 token 自动裁剪
- **HNSW 索引**：sqlite-vec 支持，但默认未启用；大规模数据需要
- **多查询融合**：除了 beat+人物名，加 chapter.outline 多查询召回
- **重排序**：用 cross-encoder 对 KNN 召回结果重排（提升精度）
- **混合检索**：向量 + 关键词 BM25 并联（专有名词/人名场景）
- **chunk_type 过滤**：用户可选只召回 dialogue / description
- **embedding 模型路由**：不同章节用不同 embedding 模型（开发期 A/B 测试）
