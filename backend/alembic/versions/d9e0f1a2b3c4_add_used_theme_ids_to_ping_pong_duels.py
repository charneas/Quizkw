"""add used_theme_ids to ping_pong_duels

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-08-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bug playtest 2026-08-16 : quand la liste de réponses d'un thème
    # Ping-Pong est épuisée, le duel passe automatiquement à un autre thème
    # au lieu de faire perdre l'équipe suivante par manque de réponses —
    # cette colonne évite de retomber sur un thème déjà vidé dans ce duel.
    op.add_column(
        'ping_pong_duels',
        sa.Column('used_theme_ids', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table('ping_pong_duels') as batch_op:
        batch_op.drop_column('used_theme_ids')
