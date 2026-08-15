"""add player_token to players

Revision ID: d1d2f5aff66c
Revises: 0d828940032a
Create Date: 2026-08-15 00:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1d2f5aff66c'
down_revision: Union[str, None] = '0d828940032a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Les endpoints Manche 2/3 (select-theme, /round2/{code}/answer, ...)
    # acceptaient un player_id non authentifié — n'importe quel client
    # connaissant l'id pouvait agir pour un autre joueur. player_token est le
    # secret qui les authentifie désormais (même modèle que Team.team_token).
    op.add_column('players', sa.Column('player_token', sa.String(), nullable=True))

    # Backfill : chaque joueur existant reçoit un token distinct (ne peut pas
    # être une valeur constante ni un server_default SQL).
    conn = op.get_bind()
    players = conn.execute(sa.text("SELECT id FROM players")).fetchall()
    for (player_id,) in players:
        conn.execute(
            sa.text("UPDATE players SET player_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(24), "id": player_id},
        )

    with op.batch_alter_table('players') as batch_op:
        batch_op.alter_column('player_token', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('players') as batch_op:
        batch_op.drop_column('player_token')
