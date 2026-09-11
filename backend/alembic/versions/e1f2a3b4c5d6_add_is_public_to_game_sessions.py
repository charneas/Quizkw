"""add is_public to game_sessions (rooms publiques)

Revision ID: e1f2a3b4c5d6
Revises: a4b5c6d7e8f9
Create Date: 2026-09-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'game_sessions',
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('game_sessions', 'is_public')
