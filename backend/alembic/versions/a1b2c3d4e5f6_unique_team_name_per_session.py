"""unique team name per game session

Revision ID: a1b2c3d4e5f6
Revises: 70fc813ad257
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '70fc813ad257'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deux équipes portant le même nom dans la même session prêtaient à
    # confusion (impossible de les distinguer côté joueurs/host) — trouvé en
    # revue. Les doublons existants sont renommés avant de poser la contrainte
    # pour ne pas faire échouer la migration sur des données déjà en base.
    op.execute("""
        UPDATE teams
        SET name = name || ' (' || id || ')'
        WHERE id IN (
            SELECT t1.id FROM teams t1
            JOIN teams t2 ON t1.game_session_id = t2.game_session_id
                AND t1.name = t2.name AND t1.id > t2.id
        )
    """)
    with op.batch_alter_table('teams') as batch_op:
        batch_op.create_unique_constraint('uq_team_session_name', ['game_session_id', 'name'])


def downgrade() -> None:
    with op.batch_alter_table('teams') as batch_op:
        batch_op.drop_constraint('uq_team_session_name', type_='unique')
