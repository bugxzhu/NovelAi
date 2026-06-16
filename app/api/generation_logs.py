from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import GenerationLog
from app.models.generation import GenerationLogDetail, GenerationLogRead

router = APIRouter()


@router.get("", response_model=list[GenerationLogRead])
def list_logs(
    chapter_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = (
        select(GenerationLog)
        .where(GenerationLog.chapter_id == chapter_id)
        .order_by(GenerationLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


@router.get("/{log_id}", response_model=GenerationLogDetail)
def get_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(GenerationLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="generation log not found")
    return log
