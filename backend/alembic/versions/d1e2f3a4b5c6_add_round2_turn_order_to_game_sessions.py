"""add round2 turn order to game_sessions

Revision ID: d1e2f3a4b5c6
Revises: 73db4f3bffcc
Create Date: 2026-08-12 00:00:00.000000

Manche 2 passe en tour par rôle : ordre de passage figé à la qualification
Manche 1 -> Manche 2, et joueur actuellement autorisé à jouer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = '73db4f3bffcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('game_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('round2_turn_order', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('round2_current_turn_player_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_game_sessions_round2_current_turn_player',
            'players', ['round2_current_turn_player_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('game_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_game_sessions_round2_current_turn_player', type_='foreignkey')
        batch_op.drop_column('round2_current_turn_player_id')
        batch_op.drop_column('round2_turn_order')
