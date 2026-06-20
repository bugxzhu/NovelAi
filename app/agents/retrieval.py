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

    # 3. Filter by threshold (sqlite-vec returns cosine distance → similarity = 1 - distance)
    candidates: list[tuple[int, float]] = []
    for rowid, distance in rows:
        score = 1.0 - distance
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
