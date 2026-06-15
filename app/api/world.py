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
