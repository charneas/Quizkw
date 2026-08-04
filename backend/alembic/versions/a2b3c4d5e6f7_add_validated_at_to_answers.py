"""add validated_at to answers

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f7
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BUG-110 : la réponse d'une équipe peut être corrigée par n'importe quel
    # coéquipier tant que l'host n'a pas validé (dernière soumission retenue).
    # Une fois validée, la réponse est verrouillée pour préserver le score attribué.
    op.add_column('answers', sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True))

    # D'anciens doublons ont pu être créés avant ce fix (l'ancien code
    # rejetait les doublons applicativement, sans contrainte DB) : ne garder
    # que la ligne la plus récente par (question_id, team_id) avant d'ajouter
    # l'index unique, sinon sa création échouerait.
    op.execute("""
        DELETE FROM answers
        WHERE id NOT IN (
            SELECT MAX(id) FROM answers GROUP BY question_id, team_id
        )
    """)
    # batch_alter_table (cf. is_tiebreak) : SQLite ne supporte pas ALTER TABLE
    # ADD CONSTRAINT directement, cette contrainte doit correspondre exactement
    # au UniqueConstraint déclaré dans app/models.py (même nom).
    with op.batch_alter_table('answers') as batch_op:
        batch_op.create_unique_constraint(
            'ix_answers_question_team_unique',
            ['question_id', 'team_id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('answers') as batch_op:
        batch_op.drop_constraint('ix_answers_question_team_unique', type_='unique')
    op.drop_column('answers', 'validated_at')
