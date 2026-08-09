"""ajout is_cancelled a ping_pong_duels (annulation host BUG-101g)

Revision ID: b4c5d6e7f8a9
Revises: a3d4e5f6c7b8
Create Date: 2026-08-09 00:00:00.000000

Story J.002 (BUG-101g, issue GitHub #62) : un duel ping-pong abandonné
verrouille définitivement les deux équipes depuis le fix de #54 (garde
anti-double-duel). is_cancelled distingue une annulation host d'une fin
normale (winner_team_id reste None dans les deux cas).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3d4e5f6c7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('ping_pong_duels', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_cancelled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('ping_pong_duels', schema=None) as batch_op:
        batch_op.drop_column('is_cancelled')