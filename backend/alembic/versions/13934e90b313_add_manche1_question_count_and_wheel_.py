"""add manche1_question_count and wheel_frequency to game_sessions

Revision ID: 13934e90b313
Revises: d5e6f7a8b9c0
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13934e90b313'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_sessions', sa.Column('manche1_question_count', sa.Integer(), nullable=False, server_default='20'))
    op.add_column('game_sessions', sa.Column('wheel_frequency', sa.Integer(), nullable=False, server_default='5'))


def downgrade() -> None:
    op.drop_column('game_sessions', 'wheel_frequency')
    op.drop_column('game_sessions', 'manche1_question_count')
