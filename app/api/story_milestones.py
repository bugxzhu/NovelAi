"""M4b-1: /api/story-milestones — CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import StoryMilestone
from app.models.story_milestone import (
    StoryMilestoneCreate,
    StoryMilestoneRead,
    StoryMilestoneUpdate,
)

router = APIRouter()


@router.get("", response_model=list[StoryMilestoneRead])
def list_story_milestones(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
):
    stmt = select(StoryMilestone).where(StoryMilestone.project_id == project_id)
    stmt = stmt.order_by(
        StoryMilestone.order_index.asc(),
        StoryMilestone.id,
    )
    return list(db.scalars(stmt))


@router.post("", response_model=StoryMilestoneRead,
             status_code=status.HTTP_201_CREATED)
def create_story_milestone(
    payload: StoryMilestoneCreate, db: Session = Depends(get_db)
):
    m = StoryMilestone(**payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.patch("/{milestone_id}", response_model=StoryMilestoneRead)
def update_story_milestone(
    milestone_id: int,
    payload: StoryMilestoneUpdate,
    db: Session = Depends(get_db),
):
    m = db.get(StoryMilestone, milestone_id)
    if m is None:
        raise HTTPException(status_code=404, detail="story_milestone not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story_milestone(milestone_id: int, db: Session = Depends(get_db)):
    m = db.get(StoryMilestone, milestone_id)
    if m is None:
        raise HTTPException(status_code=404, detail="story_milestone not found")
    db.delete(m)
    db.commit()
