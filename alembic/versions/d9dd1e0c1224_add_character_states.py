"""add character_states

Revision ID: d9dd1e0c1224
Revises: f3a6512d59c3
Create Date: 2026-06-20 20:25:56.408696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9dd1e0c1224'
down_revision: Union[str, Sequence[str], None] = 'f3a6512d59c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create character_states table (M3c-B).

    Append-only temporal log of a character's state at the end of each
    chapter where they experienced a significant change. FKs cascade so
    deleting a character or chapter cleans up their state rows.
    """
    op.create_table(
        'character_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('state_snapshot', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_char_state_char_chapter', 'character_states',
                    ['character_id', 'chapter_id'], unique=False)
    op.create_index('idx_char_state_chapter', 'character_states',
                    ['chapter_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_char_state_chapter', table_name='character_states')
    op.drop_index('idx_char_state_char_chapter', table_name='character_states')
    op.drop_table('character_states')
