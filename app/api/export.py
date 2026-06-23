"""Export chapter(s) as Markdown or plain text."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import Chapter, Project

router = APIRouter()


def _content_disposition(filename_stem: str, ext: str) -> str:
    """Build a Content-Disposition header that works for non-ASCII filenames.

    Uses RFC 5987 `filename*` form so CJK titles download correctly while
    still offering an ASCII fallback for older clients.
    """
    from urllib.parse import quote
    # ASCII-only fallback (replace any non-ASCII with `_`). HTTP headers
    # cannot carry raw non-ASCII bytes, so the legacy `filename=` must be
    # restricted to latin-1 range.
    safe = "".join(c if (c.isascii() and (c.isalnum() or c in (" ", "-", "_"))) else "_"
                   for c in filename_stem).strip() or "export"
    quoted = f"{safe}.{ext}".replace('"', "")
    # percent-encode for the UTF-8 form (handles CJK and other non-ASCII).
    encoded = quote(f"{filename_stem}.{ext}")
    return f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{encoded}"


@router.get("/{project_id}/export")
def export_project(
    project_id: int,
    format: str = Query("markdown", pattern="^(markdown|txt)$"),
    db: Session = Depends(get_db),
):
    """Export all chapters as a single document."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    chapters = list(db.scalars(
        select(Chapter).where(
            Chapter.project_id == project_id,
        ).order_by(Chapter.order_index)
    ))

    if format == "txt":
        lines = [f"{project.title}\n"]
        for ch in chapters:
            if ch.title:
                lines.append(f"\n{ch.title}\n")
            # Strip markdown for txt
            content = ch.content or ""
            lines.append(content)
            lines.append("\n")
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(project.title, "txt")},
        )

    # markdown
    lines = [f"# {project.title}\n"]
    for ch in chapters:
        title = ch.title or f"第 {ch.order_index} 章"
        lines.append(f"\n## {title}\n")
        lines.append(ch.content or "")
        lines.append("")
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(project.title, "md")},
    )

