"""BUG-101e : les scores (Team.score, PlayerRound2Stats.score,
PlayerRound3Stats.score) sont touchés par de nombreux chemins indépendants
(validation de réponse, effets de roue, victoire de duel ping-pong, jeton
PENALTY déjà fixé par #53, réponses individuelles Manche 2/3) pouvant
plausiblement se chevaucher sur la même ligne. Un read-modify-write Python
(`obj.score += x`) perdrait silencieusement l'une des deux écritures si
l'autre commite entre la lecture et l'écriture. apply_score_delta()
centralise la mise à jour atomique (UPDATE ... SET score = CASE ...) pour
que tous ces appelants partagent la même protection, sans duplication ni
import circulaire avec main.py (ping_pong_manager.py ne peut pas importer
main.py).
"""
from sqlalchemy import case
from sqlalchemy.orm import Session

from . import models


def apply_score_delta(db: Session, model, row_id: int, delta: int, floor_zero: bool = False):
    """Applique un delta à `model.score` (Team, PlayerRound2Stats,
    PlayerRound3Stats — tout modèle avec une colonne `id` et une colonne
    `score`) de façon atomique et retourne la ligne rafraîchie. Ne commite
    pas — laisse l'appelant gérer la transaction (plusieurs de ces mises à
    jour peuvent participer à un même commit).
    """
    # flush() d'abord : sans ça, d'autres attributs déjà modifiés en mémoire
    # sur ce même objet (ex. Team.bonus_active consommé juste avant par
    # award_points_with_bonus) ne seraient pas encore écrits en base, et le
    # db.refresh() plus bas les effacerait silencieusement en rechargeant
    # une version obsolète depuis la base (repéré : test_bonus_token.py
    # échouait avec bonus_active resté True après ce fix).
    db.flush()
    new_score_expr = model.score + delta
    if floor_zero:
        new_score_expr = case((model.score + delta < 0, 0), else_=model.score + delta)
    db.query(model).filter(model.id == row_id).update(
        {"score": new_score_expr}, synchronize_session=False,
    )
    row = db.query(model).filter(model.id == row_id).first()
    db.refresh(row)
    return row


def apply_team_score_delta(db: Session, team_id: int, delta: int, floor_zero: bool = False) -> models.Team:
    return apply_score_delta(db, models.Team, team_id, delta, floor_zero=floor_zero)