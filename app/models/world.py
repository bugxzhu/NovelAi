from pydantic import BaseModel

from app.models.common import ORMBase, TimestampMixin


class WorldOverviewBase(BaseModel):
    setting_era: str = ""
    geography_summary: str = ""
    history_summary: str = ""
    culture_summary: str = ""
    power_system: str = ""
    rules_and_taboos: str = ""


class WorldOverviewUpsert(WorldOverviewBase):
    pass


class WorldOverviewRead(WorldOverviewBase, ORMBase, TimestampMixin):
    id: int
    project_id: int
