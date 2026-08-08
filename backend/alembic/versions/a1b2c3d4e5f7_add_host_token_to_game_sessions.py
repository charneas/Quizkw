"""add host_token to game_sessions, drop has_host

Revision ID: a1b2c3d4e5f7
Revises: 60a3c41aa69f
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = '60a3c41aa69f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BUG-103 : le rôle host n'était qu'un booléen (`has_host`) posé par un
    # endpoint sans authentification — n'importe qui pouvait s'auto-déclarer
    # host. On remplace par un token secret, généré à la création de la
    # partie et connu du seul créateur.
    op.add_column('game_sessions', sa.Column('host_token', sa.String(), nullable=True))

    game_sessions = table('game_sessions', column('id', sa.Integer), column('host_token', sa.String))
    conn = op.get_bind()
    for (session_id,) in conn.execute(sa.select(game_sessions.c.id)):
        conn.execute(
            game_sessions.update()
            .where(game_sessions.c.id == session_id)
            .values(host_token=secrets.token_urlsafe(24))
        )

    with op.batch_alter_table('game_sessions') as batch_op:
        batch_op.alter_column('host_token', existing_type=sa.String(), nullable=False)
        batch_op.drop_column('has_host')


def downgrade() -> None:
    with op.batch_alter_table('game_sessions') as batch_op:
        batch_op.add_column(sa.Column('has_host', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.drop_column('host_token')
