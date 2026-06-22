"""add story_milestones

Revision ID: 037af14eaf66
Revises: 613de9862323
Create Date: 2026-06-22 19:52:37.527790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037af14eaf66'
down_revision: Union[str, Sequence[str], None] = '613de9862323'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'story_milestones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('type', sa.Text(), nullable=False, server_default='里程碑'),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('chapter_start', sa.Integer(), nullable=True),
        sa.Column('chapter_end', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='planned'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_milestones_project', 'story_milestones',
                    ['project_id', 'order_index'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_milestones_project', table_name='story_milestones')
    op.drop_table('story_milestones')
