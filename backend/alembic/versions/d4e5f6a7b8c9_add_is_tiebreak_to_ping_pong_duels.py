"""add is_tiebreak to ping_pong_duels

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Manche 1 est maintenant plafonnée à 20 questions ; une égalité gênante
    # sur la dernière place qualificative pour la Manche 2 est désormais
    # départagée par un duel ping-pong dédié, distingué des duels de roue
    # par ce flag (le gagnant reçoit +1 point pour lever l'ambiguïté du tri).
    op.add_column('ping_pong_duels', sa.Column('is_tiebreak', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.execute("UPDATE ping_pong_duels SET is_tiebreak = 0")
    with op.batch_alter_table('ping_pong_duels') as batch_op:
        batch_op.alter_column('is_tiebreak', existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    op.drop_column('ping_pong_duels', 'is_tiebreak')
