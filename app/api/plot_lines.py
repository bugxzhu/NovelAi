"""M3c-D: /api/plot-lines — CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.memory.schema import PlotLine
from app.models.plot_line import PlotLineCreate, PlotLineRead, PlotLineUpdate

router = APIRouter()


@router.get("", response_model=list[PlotLineRead])
def list_plot_lines(
    project_id: int = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = select(PlotLine).where(PlotLine.project_id == project_id)
    if status_filter is not None:
        stmt = stmt.where(PlotLine.status == status_filter)
    # Sort: main before sub. "main" < "sub" alphabetically, so ASC puts main first.
    stmt = stmt.order_by(
        PlotLine.type.asc(),
        PlotLine.id,
    )
    return list(db.scalars(stmt))


@router.post("", response_model=PlotLineRead,
             status_code=status.HTTP_201_CREATED)
def create_plot_line(payload: PlotLineCreate, db: Session = Depends(get_db)):
    pl = PlotLine(**payload.model_dump())
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


@router.patch("/{plot_line_id}", response_model=PlotLineRead)
def update_plot_line(
    plot_line_id: int,
    payload: PlotLineUpdate,
    db: Session = Depends(get_db),
):
    pl = db.get(PlotLine, plot_line_id)
    if pl is None:
        raise HTTPException(status_code=404, detail="plot_line not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pl, field, value)
    db.commit()
    db.refresh(pl)
    return pl


@router.delete("/{plot_line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plot_line(plot_line_id: int, db: Session = Depends(get_db)):
    pl = db.get(PlotLine, plot_line_id)
    if pl is None:
        raise HTTPException(status_code=404, detail="plot_line not found")
    db.delete(pl)
    db.commit()
