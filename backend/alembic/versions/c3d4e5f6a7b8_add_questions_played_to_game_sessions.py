"""add questions_played to game_sessions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La roue de fortune (tous les 5 tours, ping-pong/bonus/malus) n'existait
    # que côté client sur un écran "un seul appareil" (Game.tsx) : le vrai
    # flux multi-appareils (TeamScreen.tsx + /next-question) ne comptait
    # jamais les tours joués, donc rien ne se déclenchait — bug utilisateur.
    op.add_column('game_sessions', sa.Column('questions_played', sa.Integer(), nullable=True, server_default='0'))
    op.execute("UPDATE game_sessions SET questions_played = 0")
    with op.batch_alter_table('game_sessions') as batch_op:
        batch_op.alter_column('questions_played', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_column('game_sessions', 'questions_played')
