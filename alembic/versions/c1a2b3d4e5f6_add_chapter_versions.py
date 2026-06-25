"""add chapter_versions

Revision ID: c1a2b3d4e5f6
Revises: 037af14eaf66
Create Date: 2026-06-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '037af14eaf66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create chapter_versions table.

    Append-only content snapshots for chapter rollback. FKs cascade so
    deleting a chapter removes its versions. Indexed by (chapter_id,
    created_at DESC) for fast "list newest first" queries.
    """
    op.create_table(
        'chapter_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_versions_chapter',
        'chapter_versions',
        ['chapter_id', sa.text('created_at DESC')],
        unique=False,
    )


def downgrade() -> None:
    """Drop chapter_versions table."""
    op.drop_index('idx_versions_chapter', table_name='chapter_versions')
    op.drop_table('chapter_versions')
