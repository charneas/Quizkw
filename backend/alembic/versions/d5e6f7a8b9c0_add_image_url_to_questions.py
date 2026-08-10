"""add image_url to questions

Revision ID: d5e6f7a8b9c0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('questions', sa.Column('image_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('questions', 'image_url')
