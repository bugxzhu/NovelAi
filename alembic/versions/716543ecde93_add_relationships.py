"""add relationships

Revision ID: 716543ecde93
Revises: d9dd1e0c1224
Create Date: 2026-06-20 22:19:03.819616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '716543ecde93'
down_revision: Union[str, Sequence[str], None] = 'd9dd1e0c1224'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create relationships table (M3c-A).

    Append-only temporal log of directed relationships between characters.
    The partial unique index uq_rel_current guarantees at most one
    current-valid (valid_to_chapter IS NULL) row per from→to direction;
    the accept handler soft-closes the previous row before INSERTing a
    new one. FKs cascade so deleting a character/project cleans up
    their relationship rows.
    """
    op.create_table(
        'relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('from_char_id', sa.Integer(), nullable=False),
        sa.Column('to_char_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('strength', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('valid_from_chapter', sa.Integer(), nullable=False),
        sa.Column('valid_to_chapter', sa.Integer(), nullable=True),
        sa.Column('change_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('extractor_log_id', sa.Integer(), nullable=True),
        sa.Column('pending_update_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_char_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['to_char_id'], ['characters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "CREATE INDEX idx_rel_from_to_current "
        "ON relationships(from_char_id, to_char_id) "
        "WHERE valid_to_chapter IS NULL"
    )
    op.create_index('idx_rel_project', 'relationships',
                    ['project_id', 'from_char_id'], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_rel_current "
        "ON relationships(from_char_id, to_char_id) "
        "WHERE valid_to_chapter IS NULL"
    )


def downgrade() -> None:
    """Drop relationships table."""
    op.execute("DROP INDEX IF EXISTS uq_rel_current")
    op.drop_index('idx_rel_project', table_name='relationships')
    op.execute("DROP INDEX IF EXISTS idx_rel_from_to_current")
    op.drop_table('relationships')
