"""manche 2: round_number (deux thèmes par joueur)

Revision ID: ce30f546f898
Revises: d1e2f3a4b5c6
Create Date: 2026-08-12 00:00:00.000000

Manche 2 passe d'un thème unique (10 questions) à deux thèmes successifs (10
questions chacun) par joueur avant qualification. round_number (1 ou 2)
distingue le round en cours ; theme_id/current_question_index/theme_selected_at
sont remis à zéro par round2_manager._maybe_start_round2 au passage du round 1
au round 2, score/questions_answered/correct_answers restant cumulatifs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce30f546f898'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('player_round2_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('round_number', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('player_round2_stats', schema=None) as batch_op:
        batch_op.drop_column('round_number')
