"""manche 3: tour par joueur + themes du finaliste

Revision ID: ff493f1b1c62
Revises: 92b6a559fd92
Create Date: 2026-07-25 13:24:08.977641

AD-0 : la Manche 3 est individuelle — le tour appartient à un joueur, et les
3 thèmes de Manche 3 sont choisis par chaque finaliste, plus par une équipe.

Comme la révision précédente : écrite à la main, SQLite ne sachant pas
supprimer une contrainte anonyme. batch_alter_table recrée la table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff493f1b1c62'
down_revision: Union[str, None] = '92b6a559fd92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('memory_grid_rounds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_player_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_memory_grid_rounds_current_player',
                                    'players', ['current_player_id'], ['id'])
        batch_op.drop_column('current_team_id')

    with op.batch_alter_table('player_round3_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('selected_theme_ids', sa.JSON(), nullable=True))

    # teams.selected_theme_ids TEXT -> JSON volontairement omis : no-op en
    # SQLite, cf. la révision 151a691eefd6.


def downgrade() -> None:
    with op.batch_alter_table('player_round3_stats', schema=None) as batch_op:
        batch_op.drop_column('selected_theme_ids')

    with op.batch_alter_table('memory_grid_rounds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_team_id', sa.INTEGER(), nullable=True))
        batch_op.create_foreign_key('fk_memory_grid_rounds_current_team',
                                    'teams', ['current_team_id'], ['id'])
        batch_op.drop_column('current_player_id')
