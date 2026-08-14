"""add created_at to memory_grid_rounds (phase de mémorisation Manche 3)

Revision ID: 0d828940032a
Revises: f834745b932d
Create Date: 2026-08-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0d828940032a'
down_revision = 'f834745b932d'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite n'accepte pas de DEFAULT non-constant sur ADD COLUMN (cf.
    # add_validated_at_to_answers) — pas de server_default ici, le modèle
    # applique déjà func.now() côté application aux nouvelles lignes.
    op.add_column(
        'memory_grid_rounds',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('memory_grid_rounds', 'created_at')
