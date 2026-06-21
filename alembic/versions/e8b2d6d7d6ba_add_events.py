"""add events

Revision ID: e8b2d6d7d6ba
Revises: 716543ecde93
Create Date: 2026-06-21 12:44:48.139858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b2d6d7d6ba'
down_revision: Union[str, Sequence[str], None] = '716543ecde93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create events table (M3c-C).

    Append-only log of significant chapter events with a single-direction
    foreshadows JSON array of event IDs. FKs cascade so deleting a
    chapter/project cleans up their event rows.
    """
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('involved_characters', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('plot_line_id', sa.Integer(), nullable=True),
        sa.Column('foreshadows', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_events_project', 'events',
                    ['project_id', 'chapter_id'], unique=False)
    op.create_index('idx_events_chapter', 'events',
                    ['chapter_id'], unique=False)


def downgrade() -> None:
    """Drop events table."""
    op.drop_index('idx_events_chapter', table_name='events')
    op.drop_index('idx_events_project', table_name='events')
    op.drop_table('events')
