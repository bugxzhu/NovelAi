"""add plot_lines

Revision ID: 613de9862323
Revises: e8b2d6d7d6ba
Create Date: 2026-06-21 20:03:19.032805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '613de9862323'
down_revision: Union[str, Sequence[str], None] = 'e8b2d6d7d6ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create plot_lines table (M3c-D).

    Manually managed main/sub plot lines with status lifecycle. FK cascades
    so deleting a project cleans up its plot_line rows.
    """
    op.create_table(
        'plot_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False, server_default='sub'),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.Text(), nullable=False, server_default='planned'),
        sa.Column('start_chapter', sa.Integer(), nullable=True),
        sa.Column('end_chapter', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_plot_lines_project', 'plot_lines',
                    ['project_id', 'status'], unique=False)


def downgrade() -> None:
    """Drop plot_lines table."""
    op.drop_index('idx_plot_lines_project', table_name='plot_lines')
    op.drop_table('plot_lines')
