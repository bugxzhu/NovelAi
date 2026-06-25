"""Chapter version history — snapshots + restore.

Endpoints:
  POST   /api/chapters/{chapter_id}/versions       create snapshot
  GET    /api/chapters/{chapter_id}/versions       list (newest first)
  GET    /api/chapter-versions/{version_id}        fetch one (with content)
  POST   /api/chapter-versions/{version_id}/restore
                                                   transactional rollback

The router is registered with prefix="/api" in main.py, so routes below
include the leading "/chapters" or "/chapter-versions" segment.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Chapter, ChapterVersion
from app.models.chapter_version import (
    ChapterVersionCreate,
    ChapterVersionListItem,
    ChapterVersionRead,
    ChapterVersionRestoreResponse,
)

router = APIRouter()


@router.post(
    "/chapters/{chapter_id}/versions",
    response_model=ChapterVersionRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    chapter_id: int,
    body: ChapterVersionCreate,
    db: Session = Depends(get_db),
):
    """Snapshot current state. Content must be supplied by the caller
    (frontend reads from window.__chapterEditor before mutation). The
    response omits `content` — use GET /chapter-versions/{id} to fetch it.
    """
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"chapter {chapter_id} not found")
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=body.content,
        char_count=len(body.content),
        reason=body.reason,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return ChapterVersionRead(
        id=version.id,
        chapter_id=version.chapter_id,
        char_count=version.char_count,
        reason=version.reason,
        created_at=version.created_at,
        content=None,
    )


@router.get(
    "/chapters/{chapter_id}/versions",
    response_model=list[ChapterVersionListItem],
)
def list_versions(
    chapter_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List versions newest-first.

    delta_char_count is computed against the *next-newer* neighbor:
      - For the newest version, the neighbor is the chapter's current
        content length (the "live" state).
      - For older versions, the neighbor is the immediately newer sibling.
    A negative delta means content shrank from the neighbor to this version.
    """
    rows = list(
        db.scalars(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter_id)
            .order_by(ChapterVersion.created_at.desc())
            .limit(limit)
        )
    )
    if not rows:
        return []

    chapter = db.get(Chapter, chapter_id)
    current_count = len(chapter.content) if chapter and chapter.content else 0

    items: list[ChapterVersionListItem] = []
    for i, v in enumerate(rows):
        newer_count = current_count if i == 0 else rows[i - 1].char_count
        items.append(
            ChapterVersionListItem(
                id=v.id,
                chapter_id=v.chapter_id,
                char_count=v.char_count,
                delta_char_count=newer_count - v.char_count,
                reason=v.reason,
                created_at=v.created_at,
            )
        )
    return items


@router.get("/chapter-versions/{version_id}", response_model=ChapterVersionRead)
def get_version(version_id: int, db: Session = Depends(get_db)):
    """Fetch a single version including its content payload."""
    v = db.get(ChapterVersion, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail=f"version {version_id} not found")
    return ChapterVersionRead(
        id=v.id,
        chapter_id=v.chapter_id,
        char_count=v.char_count,
        reason=v.reason,
        created_at=v.created_at,
        content=v.content,
    )


@router.post(
    "/chapter-versions/{version_id}/restore",
    response_model=ChapterVersionRestoreResponse,
)
def restore_version(version_id: int, db: Session = Depends(get_db)):
    """Restore chapter.content to this version's content.

    Transactional sequence:
      (1) snapshot current chapter.content as a pre_restore version
          (so the operation itself is reversible),
      (2) overwrite chapter.content with version.content,
      (3) single commit covers both writes.
    If anything throws between (1) and (3), SQLAlchemy's session rollback
    discards both pending changes — no half-applied state.
    """
    v = db.get(ChapterVersion, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail=f"version {version_id} not found")
    chapter = db.get(Chapter, v.chapter_id)
    if chapter is None:
        # Orphan version (shouldn't happen with the CASCADE FK but be defensive).
        raise HTTPException(status_code=404, detail="owning chapter missing")

    current_content = chapter.content or ""
    pre_restore = ChapterVersion(
        chapter_id=chapter.id,
        content=current_content,
        char_count=len(current_content),
        reason="pre_restore",
    )
    db.add(pre_restore)
    chapter.content = v.content
    db.commit()
    db.refresh(pre_restore)

    return ChapterVersionRestoreResponse(
        restored_version_id=v.id,
        new_pre_restore_id=pre_restore.id,
        new_char_count=len(v.content),
    )
