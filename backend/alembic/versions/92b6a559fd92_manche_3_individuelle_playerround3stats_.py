"""manche 3 individuelle: PlayerRound3Stats + GridCell par joueur (AD-0, AD-1, AD-15)

Revision ID: 92b6a559fd92
Revises: 151a691eefd6
Create Date: 2026-07-25 13:19:40.291885

AD-0 : la Manche 3 est individuelle, exactement 4 finalistes. Le schéma la
modélisait par équipes.
AD-1 : trois axes de score cloisonnés — la Manche 3 gagne le sien
(player_round3_stats) et cesse d'écrire Team.score.
AD-15 : grid_cells.points_awarded est la sentinelle d'idempotence de
l'attribution.

Écrite à la main plutôt qu'en autogenerate brut : SQLite ne sait pas
supprimer une contrainte anonyme ni ajouter une colonne NOT NULL sans
défaut sur une table peuplée. batch_alter_table recrée la table.

NOTE de perte de données : les colonnes assigned_team_id / answered_by_team_id
de grid_cells sont supprimées. Les grilles de parties existantes perdent leur
attribution — ce sont des parties de développement, et le modèle par équipes
était de toute façon incorrect.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92b6a559fd92'
down_revision: Union[str, None] = '151a691eefd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Axe de score individuel de la Manche 3 (AD-1) ---
    op.create_table(
        'player_round3_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('game_session_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cells_claimed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['game_session_id'], ['game_sessions.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_player_round3_stats_id'), 'player_round3_stats', ['id'], unique=False)

    # --- grid_cells : équipes -> joueurs, + sentinelle AD-15 ---
    with op.batch_alter_table('grid_cells', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_player_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('answered_by_player_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('points_awarded', sa.Integer(),
                                      server_default='0', nullable=False))
        batch_op.create_foreign_key('fk_grid_cells_assigned_player',
                                    'players', ['assigned_player_id'], ['id'])
        batch_op.create_foreign_key('fk_grid_cells_answered_by_player',
                                    'players', ['answered_by_player_id'], ['id'])
        batch_op.drop_column('assigned_team_id')
        batch_op.drop_column('answered_by_team_id')

    # --- Table morte, 0 ligne, supersédée par ping_pong_duels / ping_pong_turns ---
    op.drop_index('ix_ping_pong_answers_id', table_name='ping_pong_answers')
    op.drop_table('ping_pong_answers')

    # NOTE : autogenerate propose aussi teams.selected_theme_ids TEXT -> JSON.
    # Volontairement omis : la révision 151a691eefd6 documente que SQLite traite
    # déjà TEXT avec l'affinité JSON et que la conversion est un no-op. La
    # proposition réapparaîtra à chaque autogenerate ; l'ignorer est correct.


def downgrade() -> None:
    op.create_table(
        'ping_pong_answers',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('game_session_id', sa.INTEGER(), nullable=True),
        sa.Column('theme_id', sa.INTEGER(), nullable=True),
        sa.Column('team_id', sa.INTEGER(), nullable=True),
        sa.Column('answers_given', sa.JSON(), nullable=False),
        sa.Column('correct_count', sa.INTEGER(), nullable=True),
        sa.Column('points_earned', sa.INTEGER(), nullable=True),
        sa.Column('answered_at', sa.DATETIME(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['game_session_id'], ['game_sessions.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['theme_id'], ['ping_pong_themes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ping_pong_answers_id', 'ping_pong_answers', ['id'], unique=False)

    with op.batch_alter_table('grid_cells', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_team_id', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('answered_by_team_id', sa.INTEGER(), nullable=True))
        batch_op.create_foreign_key('fk_grid_cells_assigned_team',
                                    'teams', ['assigned_team_id'], ['id'])
        batch_op.create_foreign_key('fk_grid_cells_answered_by_team',
                                    'teams', ['answered_by_team_id'], ['id'])
        batch_op.drop_column('points_awarded')
        batch_op.drop_column('answered_by_player_id')
        batch_op.drop_column('assigned_player_id')

    op.drop_index(op.f('ix_player_round3_stats_id'), table_name='player_round3_stats')
    op.drop_table('player_round3_stats')
