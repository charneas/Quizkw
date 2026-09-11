"""add is_solo_finale to game_sessions (Manche 3 directe)

Revision ID: a4b5c6d7e8f9
Revises: de594dc6e282
Create Date: 2026-09-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e8f9'
down_revision = 'de594dc6e282'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'game_sessions',
        sa.Column('is_solo_finale', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('game_sessions', 'is_solo_finale')
