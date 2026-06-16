from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.memory.schema import Project


def get_project_or_404(db: Session, project_id: int) -> Project:
    obj = db.get(Project, project_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="project not found")
    return obj
