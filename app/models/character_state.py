from app.models.common import ORMBase, TimestampMixin


class CharacterStateRead(ORMBase, TimestampMixin):
    id: int
    character_id: int
    chapter_id: int
    chapter_title: str        # JOIN chapters.title
    chapter_order: int        # JOIN chapters.order_index
    state_snapshot: str
    change_summary: str
    extractor_log_id: int | None
    pending_update_id: int | None
