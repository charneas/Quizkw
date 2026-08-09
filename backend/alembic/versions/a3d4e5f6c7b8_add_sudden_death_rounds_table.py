"""ajout table sudden_death_rounds (mort subite manche 3)

Revision ID: a3d4e5f6c7b8
Revises: 60b588c18e99
Create Date: 2026-08-09 00:00:00.000000

Story L.001 (BUG-305, issue GitHub #31) : la mort subite en fin de Manche 3
n'existait pas — calculate_winner détectait l'égalité mais rien ne créait de
tour de départage. Cette table porte l'état d'une manche de mort subite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3d4e5f6c7b8'
down_revision: Union[str, None] = '60b588c18e99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sudden_death_rounds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('memory_grid_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('tied_player_ids', sa.JSON(), nullable=False),
        sa.Column('eliminated_player_ids', sa.JSON(), nullable=False),
        sa.Column('winner_player_id', sa.Integer(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['memory_grid_id'], ['memory_grids.id']),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id']),
        sa.ForeignKeyConstraint(['winner_player_id'], ['players.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sudden_death_rounds_id'), 'sudden_death_rounds', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sudden_death_rounds_id'), table_name='sudden_death_rounds')
    op.drop_table('sudden_death_rounds')