"""add icon to teams

Revision ID: 73db4f3bffcc
Revises: 13934e90b313
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73db4f3bffcc'
down_revision: Union[str, None] = '13934e90b313'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('icon', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('teams', 'icon')
