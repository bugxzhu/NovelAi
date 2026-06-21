from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.memory.base import Base


def _now_utc() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="")
    premise: Mapped[str] = mapped_column(Text, default="")
    main_theme: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    world_overview: Mapped["WorldOverview | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    lore_entries: Mapped[list["LoreEntry"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class WorldOverview(Base):
    __tablename__ = "world_overview"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    setting_era: Mapped[str] = mapped_column(Text, default="")
    geography_summary: Mapped[str] = mapped_column(Text, default="")
    history_summary: Mapped[str] = mapped_column(Text, default="")
    culture_summary: Mapped[str] = mapped_column(Text, default="")
    power_system: Mapped[str] = mapped_column(Text, default="")
    rules_and_taboos: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    project: Mapped["Project"] = relationship(back_populates="world_overview")


class LoreEntry(Base):
    __tablename__ = "lore_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("lore_entries.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    project: Mapped["Project"] = relationship(back_populates="lore_entries")
    parent: Mapped["LoreEntry | None"] = relationship(
        "LoreEntry", remote_side=[id], backref="children"
    )


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="")
    personality: Mapped[dict] = mapped_column(JSON, default=dict)
    speech_style: Mapped[str] = mapped_column(Text, default="")
    background: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[str] = mapped_column(Text, default="")
    current_state: Mapped[str] = mapped_column(Text, default="")
    affiliations: Mapped[list] = mapped_column(JSON, default=list)
    known_locations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    project: Mapped["Project"] = relationship(back_populates="characters")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    outline: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    plot_line_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    last_involved_character_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    project: Mapped["Project"] = relationship(back_populates="chapters")


class GenerationLog(Base):
    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    # 输入
    beat_text: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, default="")
    involved_character_ids: Mapped[list] = mapped_column(JSON, default=list)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 组装的 prompt
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context_summary: Mapped[dict] = mapped_column(JSON, default=dict)

    # 输出
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_task: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 用量
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="streaming")
    started_at: Mapped[datetime] = mapped_column(default=_now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)


class PendingUpdate(Base):
    __tablename__ = "pending_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    update_type: Mapped[str] = mapped_column(String(20), nullable=False, default="hard_fact")
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # 'create' | 'update'
    target_table: Mapped[str] = mapped_column(String(50), nullable=False)  # 'characters' | 'lore_entries'
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    proposed_change: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")

    # auto=True: hard_fact (high confidence; visually distinct in pending UI; user may still reject)
    # auto=False: soft_fact (lower confidence; needs explicit user accept)
    # All Extractor-proposed pendings set this flag per their fact type:
    # new_characters/new_lore/events → True; state_changes/relationship_changes → False.
    auto: Mapped[bool] = mapped_column(default=True)
    extractor_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extractor_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_logs.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        Index("idx_pending_project_status", "project_id", "status"),
        Index("idx_pending_chapter", "chapter_id"),
    )


class ChunkMeta(Base):
    """Chunk metadata table. Each row corresponds to a row in the vec_chunks
    virtual table (same primary key). M3b pairs this with sqlite-vec for
    semantic retrieval of past chapter content."""
    __tablename__ = "chunk_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)  # paragraph | dialogue | description
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)

    __table_args__ = (
        UniqueConstraint("chapter_id", "chunk_index", name="uq_chunk_chapter_index"),
        Index("idx_chunk_chapter", "chapter_id"),
    )


class CharacterState(Base):
    """Temporal log of a character's state at the end of each chapter where
    they experienced a significant change. M3c-B: append-only, diff-style
    (rows only created when Extractor detects a notable change). The latest
    snapshot for a character is mirrored to characters.current_state."""
    __tablename__ = "character_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    state_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Audit fields (nullable; future manual creation paths may leave these null)
    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_update_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        Index("idx_char_state_char_chapter", "character_id", "chapter_id"),
        Index("idx_char_state_chapter", "chapter_id"),
    )


class Relationship(Base):
    """Temporal log of directed relationships between characters. M3c-A:
    append-only version log — accept handler soft-closes the previous current-valid
    row (sets valid_to_chapter) before INSERTing a new one. The partial unique
    index uq_rel_current guarantees at most one current-valid row per direction."""
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_char_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    to_char_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(nullable=False, default=0.0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    valid_from_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_update_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        # Partial indexes on SQLite — declared via sqlite_where in Index.
        Index(
            "idx_rel_from_to_current",
            "from_char_id", "to_char_id",
            sqlite_where=text("valid_to_chapter IS NULL"),
        ),
        Index("idx_rel_project", "project_id", "from_char_id"),
        # Partial UNIQUE: same direction can only have one current-valid row.
        Index(
            "uq_rel_current", "from_char_id", "to_char_id",
            unique=True,
            sqlite_where=text("valid_to_chapter IS NULL"),
        ),
    )


class Event(Base):
    """Significant events that occur in chapters, with cross-chapter foreshadow
    links. M3c-C: append-only (no version switch, no upsert); foreshadows is a
    single-direction JSON array of event IDs; payoff_of is derived (not stored)."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    involved_characters: Mapped[list] = mapped_column(JSON, default=list)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plot_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    foreshadows: Mapped[list] = mapped_column(JSON, default=list)

    extractor_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_update_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    __table_args__ = (
        Index("idx_events_project", "project_id", "chapter_id"),
        Index("idx_events_chapter", "chapter_id"),
    )
