"""story F.2 : tables content_suggestions, content_flags, content_history

Revision ID: f91ecd2421ca
Revises: ff493f1b1c62
Create Date: 2026-07-26 22:30:00.000000

Ne crée QUE 3 nouvelles tables (op.create_table), n'altère aucune table
existante. Compatible même sans révision de baseline pour le schéma
préexistant (voir Dev Notes de la story F.2 et la spine § AD-14 : aucune
révision de base n'existe pour les ~15 tables actuelles, ce que cette
révision n'a pas besoin de résoudre puisqu'elle ne dépend de l'état
d'aucune table existante).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f91ecd2421ca'
down_revision: Union[str, None] = 'ff493f1b1c62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `themecategory` existe déjà (créé par la table `themes`, révision antérieure).
    # create_type=False évite CREATE TYPE en double sur PostgreSQL — sans ça, la
    # révision échoue avec DuplicateObject en production (invisible sous SQLite,
    # où Enum dégénère en VARCHAR + CHECK ; trouvé en revue de code).
    theme_category_enum = postgresql.ENUM(
        'SERIOUS', 'POP_CULTURE', 'WHIMSICAL', name='themecategory', create_type=False,
    )
    suggestion_status_enum = sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='suggestionstatus')

    op.create_table(
        'content_suggestions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('wikipedia_extract', sa.String(), nullable=False),
        sa.Column('generated_theme_name', sa.String(), nullable=False),
        sa.Column('generated_category', theme_category_enum, nullable=False),
        sa.Column('generated_questions', sa.JSON(), nullable=False),
        sa.Column('status', suggestion_status_enum, nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(), nullable=True),
        sa.Column('created_theme_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_theme_id'], ['themes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_suggestions_id'), 'content_suggestions', ['id'], unique=False)

    op.create_table(
        'content_flags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('flagged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_note', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_flags_id'), 'content_flags', ['id'], unique=False)

    op.create_table(
        'content_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('detail', sa.String(), nullable=True),
        sa.Column('actor', sa.String(), nullable=False, server_default='admin'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_history_id'), 'content_history', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_content_history_id'), table_name='content_history')
    op.drop_table('content_history')

    op.drop_index(op.f('ix_content_flags_id'), table_name='content_flags')
    op.drop_table('content_flags')

    op.drop_index(op.f('ix_content_suggestions_id'), table_name='content_suggestions')
    op.drop_table('content_suggestions')
