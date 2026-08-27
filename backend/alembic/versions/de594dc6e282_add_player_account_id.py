"""add player account_id

Revision ID: de594dc6e282
Revises: 02b53425db23
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de594dc6e282'
down_revision: Union[str, None] = '02b53425db23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AD-19/AD-21 : lien Player -> Account, écrit une seule fois à la création
    # du Player, ON DELETE SET NULL porté par la DDL (jamais un CASCADE).
    # batch_alter_table pour la portabilité SQLite (ajout de colonne + FK).
    with op.batch_alter_table('players') as batch_op:
        batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_players_account_id_accounts',
            'accounts',
            ['account_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('players') as batch_op:
        batch_op.drop_constraint('fk_players_account_id_accounts', type_='foreignkey')
        batch_op.drop_column('account_id')
