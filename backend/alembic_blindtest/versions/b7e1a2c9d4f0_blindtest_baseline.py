"""blindtest baseline

Schéma de la DB blindtest tel qu'il existait avant l'introduction d'Alembic
(4 tables, créées jusque-là par `create_all`). Une DB existante sans
`alembic_version` est tamponnée à cette révision (voir
`app/blindtest/migrations.py`) : cette migration ne s'exécute donc que sur
une DB vide.

`playlists` -> `games` -> `tracks` -> `playlists` forment un cycle de FK ;
SQLite n'exige pas l'existence de la table référencée à la création, l'ordre
reproduit celui de `create_all`.

Revision ID: b7e1a2c9d4f0
Revises:
Create Date: 2026-09-29 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e1a2c9d4f0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("owner_pseudo", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playlists_id"), "playlists", ["id"], unique=False)

    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("artist", sa.String(), nullable=False),
        sa.Column("isrc", sa.String(), nullable=True),
        sa.Column("youtube_video_id", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tracks_id"), "tracks", ["id"], unique=False)

    op.create_table(
        "match_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("isrc", sa.String(), nullable=True),
        sa.Column("normalized_key", sa.String(), nullable=True),
        sa.Column("youtube_video_id", sa.String(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("isrc"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index(op.f("ix_match_cache_id"), "match_cache", ["id"], unique=False)

    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("host_pseudo", sa.String(), nullable=True),
        sa.Column("current_track_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["current_track_id"], ["tracks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_games_id"), "games", ["id"], unique=False)
    op.create_index(op.f("ix_games_code"), "games", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_games_code"), table_name="games")
    op.drop_index(op.f("ix_games_id"), table_name="games")
    op.drop_table("games")
    op.drop_index(op.f("ix_match_cache_id"), table_name="match_cache")
    op.drop_table("match_cache")
    op.drop_index(op.f("ix_tracks_id"), table_name="tracks")
    op.drop_table("tracks")
    op.drop_index(op.f("ix_playlists_id"), table_name="playlists")
    op.drop_table("playlists")
