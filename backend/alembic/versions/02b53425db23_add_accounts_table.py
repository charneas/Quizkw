"""add accounts table

Revision ID: 02b53425db23
Revises: d9e0f1a2b3c4
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02b53425db23'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AD-19 : Account distinct de Player, résolu-ou-créé par discord_id ;
    # la contrainte unique DB est la sentinelle d'idempotence (pas de
    # check-then-insert applicatif).
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('discord_id', sa.String(), nullable=False),
        sa.Column('pseudo', sa.String(), nullable=False),
        sa.Column('avatar', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('discord_id', name='uq_accounts_discord_id'),
    )
    op.create_index(op.f('ix_accounts_id'), 'accounts', ['id'], unique=False)
    op.create_index(op.f('ix_accounts_discord_id'), 'accounts', ['discord_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_accounts_discord_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_table('accounts')
