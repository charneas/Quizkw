"""add games.mode

Une partie est soit "owner" (deviner à qui appartient le morceau), soit
"classic" (reconnaître le titre et l'artiste). Les parties existantes prennent
"owner" par défaut : leur comportement ne change pas.

Revision ID: c4d2f8a1e6b3
Revises: b7e1a2c9d4f0
Create Date: 2026-10-31 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d2f8a1e6b3"
down_revision: Union[str, None] = "b7e1a2c9d4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch_op:
        batch_op.add_column(sa.Column("mode", sa.String(), nullable=False, server_default="owner"))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch_op:
        batch_op.drop_column("mode")
