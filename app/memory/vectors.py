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
    if rowids:
        db.execute(
            sql_text("DELETE FROM chunk_meta WHERE chapter_id = :cid"),
            {"cid": chapter_id},
        )
        placeholders = ",".join(f":r{i}" for i in range(len(rowids)))
        params = {f"r{i}": rid for i, rid in enumerate(rowids)}
        db.execute(
            sql_text(f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})"),
            params,
        )

    # Also clean up orphaned vec_chunks rows (rowids not in chunk_meta).
    # This happens when chunk_meta was deleted but vec_chunks wasn't
    # (e.g., previous finalize failed mid-way, or manual cleanup).
    all_meta_ids = db.execute(
        sql_text("SELECT id FROM chunk_meta"),
    ).scalars().all()
    if all_meta_ids:
        placeholders = ",".join(f":m{i}" for i in range(len(all_meta_ids)))
        params = {f"m{i}": mid for i, mid in enumerate(all_meta_ids)}
        db.execute(
            sql_text(
                f"DELETE FROM vec_chunks WHERE rowid NOT IN ({placeholders})"
            ),
            params,
        )
    else:
        # No chunk_meta rows at all — wipe vec_chunks clean
        db.execute(sql_text("DELETE FROM vec_chunks"))


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
