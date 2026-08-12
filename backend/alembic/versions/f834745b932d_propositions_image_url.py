"""propositions: image_url

Revision ID: a1b2c3d4e5f6
Revises: ce30f546f898
Create Date: 2026-08-12 00:00:00.000000

Les propositions de question publiques n'avaient pas de champ image_url,
contrairement à Question qui en a un — impossible pour un proposant de
joindre un lien d'image. accept_proposition (main_admin.py) reporte
désormais ce champ sur la Question créée à l'acceptation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f834745b932d'
down_revision: Union[str, None] = 'ce30f546f898'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('propositions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('propositions', schema=None) as batch_op:
        batch_op.drop_column('image_url')
