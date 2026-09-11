"""Mode "Manche 3 directe" (spec-manche-3-seule, story 1).

Seed les données de Manche 2 synthétiques nécessaires pour réutiliser tel
quel `get_finalists_from_round2` (memory_grid.py) et `_setup_turn_order`
(memory_grid_enhanced.py) sans modifier ce code partagé avec le flow
normal Manche 1/2/3.
"""
import random

from sqlalchemy.orm import Session

from app import models


def seed_solo_finale_round2_stats(db: Session, game: models.GameSession, teams: list[models.Team]) -> None:
    """Crée 4 `PlayerRound2Stats` synthétiques (FINALIST) pour les 4 joueurs
    des 4 équipes-de-1 d'une partie `is_solo_finale`.

    - `qualification_status=FINALIST` : requis par `_setup_turn_order`.
    - `score` : tiré au hasard, valeurs distinctes (ordre total) pour un
      ordre de passage déterministe une fois les scores fixés, et pour ne
      jamais créer d'égalité qui laisserait `get_finalists_from_round2`/
      `_setup_turn_order` dépendre d'un tie-break implicite.
    - `theme_id=NULL` : évite la contrainte d'unicité
      `(game_session_id, theme_id)` si jamais plusieurs lignes partageaient
      un theme_id non-NULL.
    """
    scores = random.sample(range(1, 1000), len(teams))

    for team, score in zip(teams, scores):
        player = db.query(models.Player).filter(models.Player.team_id == team.id).first()
        if player is None:
            continue
        db.add(models.PlayerRound2Stats(
            player_id=player.id,
            game_session_id=game.id,
            theme_id=None,
            score=score,
            qualification_status=models.QualificationStatus.FINALIST,
            round_number=2,
        ))
