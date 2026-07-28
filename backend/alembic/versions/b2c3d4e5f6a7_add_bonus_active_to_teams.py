"""add bonus_active to teams

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Le jeton BONUS ("double les points de la question") n'avait aucun effet
    # persisté : le doublement n'existait que côté client et était écrasé dès
    # la validation des réponses par l'host — trouvé en revue (bug utilisateur).
    # Ce flag porte l'état "bonus actif" côté serveur, consommé à la prochaine
    # validation de réponse pour cette équipe.
    op.add_column('teams', sa.Column('bonus_active', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.execute("UPDATE teams SET bonus_active = 0")
    with op.batch_alter_table('teams') as batch_op:
        batch_op.alter_column('bonus_active', existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    op.drop_column('teams', 'bonus_active')
