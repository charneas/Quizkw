"""unique theme per round2 game session

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deux joueurs de la même session Manche 2 pouvaient se voir attribuer le
    # même thème (BUG-210, code review de #18/#26/#24) faute de contrainte en
    # base — la vérification applicative seule est vulnérable à une race
    # condition entre deux sélections concurrentes. On garde le premier
    # joueur à avoir choisi chaque thème (plus petit id) et on renvoie les
    # autres à une nouvelle sélection avant de poser la contrainte, pour ne
    # pas faire échouer la migration sur des doublons déjà en base.
    op.execute("""
        UPDATE player_round2_stats
        SET theme_id = NULL, theme_selected_at = NULL
        WHERE theme_id IS NOT NULL
        AND id NOT IN (
            SELECT MIN(id) FROM player_round2_stats
            WHERE theme_id IS NOT NULL
            GROUP BY game_session_id, theme_id
        )
    """)
    with op.batch_alter_table('player_round2_stats') as batch_op:
        batch_op.create_unique_constraint('uq_round2_session_theme', ['game_session_id', 'theme_id'])


def downgrade() -> None:
    with op.batch_alter_table('player_round2_stats') as batch_op:
        batch_op.drop_constraint('uq_round2_session_theme', type_='unique')
