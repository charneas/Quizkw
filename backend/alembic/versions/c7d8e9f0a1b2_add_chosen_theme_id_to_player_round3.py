"""add chosen_theme_id to player_round3_stats

Revision ID: c7d8e9f0a1b2
Revises: d1d2f5aff66c
Create Date: 2026-08-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'd1d2f5aff66c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bug playtest 2026-08-16 : sur les 3 thèmes soumis par un finaliste, le
    # serveur en tire désormais un seul au hasard — persisté ici pour ne pas
    # avoir à retirer le sort à chaque lecture.
    # Pas de contrainte FK nommée explicitement : SQLite (batch mode) exige un
    # nom de contrainte pour l'ajouter après coup ; le lien vers Theme reste
    # exprimé côté ORM (models.py) sans être appliqué au niveau SQLite ici,
    # comme selected_theme_ids juste au-dessus qui n'a pas de FK non plus.
    op.add_column(
        'player_round3_stats',
        sa.Column('chosen_theme_id', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table('player_round3_stats') as batch_op:
        batch_op.drop_column('chosen_theme_id')
