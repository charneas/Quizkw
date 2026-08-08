"""add team_token to teams

Revision ID: 60b588c18e99
Revises: b3c4d5e6f7a8
Create Date: 2026-08-08 00:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60b588c18e99'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BUG-101d : /tokens/use acceptait un team_id non authentifié — n'importe
    # quel client connaissant l'id pouvait consommer les jetons d'une équipe
    # qui n'est pas la sienne. team_token est le secret qui les authentifie
    # désormais (même modèle que GameSession.host_token).
    op.add_column('teams', sa.Column('team_token', sa.String(), nullable=True))

    # Backfill : chaque équipe existante reçoit un token distinct (ne peut
    # pas être une valeur constante ni un server_default SQL).
    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT id FROM teams")).fetchall()
    for (team_id,) in teams:
        conn.execute(
            sa.text("UPDATE teams SET team_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(24), "id": team_id},
        )

    with op.batch_alter_table('teams') as batch_op:
        batch_op.alter_column('team_token', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('teams') as batch_op:
        batch_op.drop_column('team_token')
