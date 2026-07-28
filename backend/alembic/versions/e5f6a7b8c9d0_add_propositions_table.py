"""add propositions table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AD-18 : Proposition est une table distincte de Question, jamais fusionnée
    # ni interrogée par le pool de jeu. Seule l'acceptation (Story F-ext-2.4,
    # hors périmètre ici) crée la Question correspondante.
    # `difficulty` (type déjà utilisé par `questions.difficulty`) et `status`
    # déclarés en `sa.Enum` générique, portable entre dialectes : sur MySQL
    # (cible réelle de prod, confirmée en revue — la spine documente encore
    # PostgreSQL/SQLite, à corriger séparément), un enum est inliné par colonne
    # sans type nommé partagé, donc aucun risque de CREATE TYPE en double ;
    # sur SQLite, dégénère en VARCHAR + CHECK.
    difficulty_enum = sa.Enum('EASY', 'MEDIUM', 'HARD', name='difficulty')
    proposition_status_enum = sa.Enum('PENDING', 'ACCEPTED', 'REJECTED', name='propositionstatus')

    op.create_table(
        'propositions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('correct_answer', sa.String(), nullable=False),
        sa.Column('wrong_answers', sa.String(), nullable=True),
        sa.Column('theme_id', sa.Integer(), nullable=True),
        sa.Column('difficulty', difficulty_enum, nullable=False),
        sa.Column('status', proposition_status_enum, nullable=False, server_default='PENDING'),
        sa.Column('rejection_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_propositions_id'), 'propositions', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_propositions_id'), table_name='propositions')
    op.drop_table('propositions')
    sa.Enum(name='propositionstatus').drop(op.get_bind(), checkfirst=True)
