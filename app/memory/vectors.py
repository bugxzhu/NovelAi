"""sqlite-vec virtual table CRUD helpers.

vec_chunks is a sqlite-vec virtual table — SQLAlchemy ORM can't map it.
We pair it with chunk_meta (standard ORM table) via shared primary key.
"""
import struct

from sqlalchemy import bindparam, text as sql_text
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
    # Use expanding bindparam: SQLAlchemy replaces :rowids with ?, ?, ... at
    # execute time and accepts a list value (no executemany interpretation).
    db.execute(
        sql_text("DELETE FROM vec_chunks WHERE rowid IN (:rowids)").bindparams(
            bindparam("rowids", expanding=True)
        ),
        {"rowids": rowids},
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
