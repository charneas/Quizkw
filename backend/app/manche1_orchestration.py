import logging
import random
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.score_utils import apply_team_score_delta

logger = logging.getLogger(__name__)


def _roll_wheel_effect(has_opponent: bool):
    """Tire un effet de roue selon les probabilités du jeu de plateau
    (1-5 malus, 6-10 +1 auto-résolu, 11-18 ping-pong ou +2 si pas
    d'adversaire, 19-20 +3). Fonction pure (aucune mutation, aucun accès
    DB) : source de vérité UNIQUE des probabilités, partagée par
    spin_wheel (roue host) et trigger_wheel_effect (roue hostless,
    rotation déterministe) — voir revue de code de la story J.004 :
    ces deux règles étaient dupliquées et avaient déjà commencé à
    diverger. Retourne (spin_result, effect_type, value).
    """
    spin_result = random.randint(1, 20)
    if spin_result <= 5:
        return spin_result, "malus", -3
    if spin_result <= 10:
        return spin_result, "bonus", 1
    if spin_result <= 18:
        if has_opponent:
            return spin_result, "ping_pong", None
        return spin_result, "bonus", 2
    return spin_result, "bonus", 3


def trigger_wheel_effect(db: Session, game: models.GameSession) -> Optional[dict]:
    """Fait tourner la roue automatiquement pour l'équipe dont c'est le tour
    (rotation déterministe sur `questions_played // game.wheel_frequency`),
    applique l'effet en base et le journalise dans WheelEffect. Reprend les
    probabilités du jeu de plateau (1-5 malus, 6-10 +1, 11-18 ping-pong, 19-20 +3).
    """
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).order_by(models.Team.id).all()
    if not teams:
        return None

    wheel_round = game.questions_played // game.wheel_frequency
    spinning_team = teams[(wheel_round - 1) % len(teams)]

    # Probabilités partagées avec spin_wheel (roue host) via _roll_wheel_effect
    # — voir revue de code de la story J.004 (duplication déjà divergente).
    has_opponent = any(t.id != spinning_team.id for t in teams)
    _spin_result, effect_type, value = _roll_wheel_effect(has_opponent)

    if effect_type == "malus":
        spinning_team = apply_team_score_delta(db, spinning_team.id, value, floor_zero=True)
        message = f"💀 Malus : {spinning_team.name} perd 3 points"
    elif effect_type == "bonus" and value == 1:
        spinning_team = apply_team_score_delta(db, spinning_team.id, value)
        message = f"🎉 {spinning_team.name} gagne 1 point"
    elif effect_type == "ping_pong":
        # L'équipe qui tombe sur le ping-pong choisit elle-même son adversaire
        # (voir TeamScreen.tsx) — pas de duel démarré ici, juste l'annonce.
        message = f"🏓 {spinning_team.name}, choisissez votre adversaire !"
    elif effect_type == "bonus" and value == 2:
        # Une seule équipe en jeu : pas d'adversaire possible pour le duel.
        spinning_team = apply_team_score_delta(db, spinning_team.id, value)
        message = f"Pas d'adversaire disponible pour le ping-pong : {spinning_team.name} reçoit +2 points à la place."
    else:  # bonus +3 (19-20)
        spinning_team = apply_team_score_delta(db, spinning_team.id, value)
        message = f"🎉 Bonus : {spinning_team.name} gagne 3 points !"

    wheel_effect = models.WheelEffect(
        game_session_id=game.id,
        effect_type=effect_type,
        value=value,
        target_team_id=spinning_team.id,
        is_applied=True,
    )
    db.add(wheel_effect)
    db.commit()
    db.refresh(wheel_effect)

    return {
        "id": wheel_effect.id,
        "effect_type": wheel_effect.effect_type,
        "value": wheel_effect.value,
        "target_team_id": spinning_team.id,
        "target_team_name": spinning_team.name,
        "duel_id": None,
        "message": message,
    }


def _pending_tiebreak_duel(db: Session, game: models.GameSession) -> Optional[models.PingPongDuel]:
    return db.query(models.PingPongDuel).filter(
        models.PingPongDuel.game_session_id == game.id,
        models.PingPongDuel.is_tiebreak == True,
        models.PingPongDuel.is_completed == False,
    ).first()


def resolve_manche1_end(db: Session, game: models.GameSession) -> dict:
    """Manche 1 vient d'atteindre son maximum de questions (ou un duel de
    départage vient de se terminer). Si le classement laisse une égalité
    gênante sur la dernière place qualificative pour la Manche 2, déclenche
    un duel ping-pong de départage entre les deux équipes concernées avant
    de qualifier. Sinon, qualifie directement pour la Manche 2.
    """
    from app.round2_manager import Round2Manager
    from app.ping_pong_manager import PingPongManager

    pending = _pending_tiebreak_duel(db, game)
    if pending:
        return {"status": "tiebreak_pending", "duel_id": pending.id}

    manager = Round2Manager(db)
    slots = manager.ROUND2_SLOTS

    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    teams_sorted = sorted(teams, key=lambda t: -t.score)

    remaining = slots
    boundary_team = None
    for t in teams_sorted:
        if remaining <= 0:
            break
        remaining -= len(t.players)
        boundary_team = t

    if boundary_team is not None:
        boundary_score = boundary_team.score
        tied_teams = [t for t in teams_sorted if t.score == boundary_score]
        higher_players = sum(len(t.players) for t in teams_sorted if t.score > boundary_score)
        tied_players_all = sum(len(t.players) for t in tied_teams)

        # Ambiguë seulement si ni "toutes les équipes à égalité qualifient"
        # ni "aucune ne qualifie" n'est possible sans dépasser la tolérance —
        # sinon le tri normal par score suffit déjà à trancher.
        if len(tied_teams) > 1 and higher_players < slots and higher_players + tied_players_all > slots + 1:
            team_a, team_b = tied_teams[0], tied_teams[1]
            pp_manager = PingPongManager(db)
            theme = pp_manager.get_random_theme()
            if theme:
                try:
                    duel = pp_manager.start_duel(
                        game_session_id=game.id,
                        theme_id=theme.id,
                        team1_id=team_a.id,
                        team2_id=team_b.id,
                    )
                except ValueError as e:
                    # BUG-101c : start_duel refuse désormais de créer un duel
                    # si une des deux équipes a déjà un duel actif (ex. duel
                    # abandonné jamais complété). Ne doit pas bloquer la fin
                    # de la Manche 1 pour autant — on qualifie sans trancher
                    # par duel de départage plutôt que de planter la requête
                    # (voir la branche de fallback "qualify" plus bas).
                    logger.warning(
                        "Fin de Manche 1 : duel de départage impossible pour %s : %s",
                        game.code, e,
                    )
                    duel = None
                if duel:
                    duel.is_tiebreak = True
                    db.add(models.WheelEffect(
                        game_session_id=game.id,
                        effect_type="tiebreak",
                        value=None,
                        target_team_id=team_a.id,
                        is_applied=True,
                    ))
                    db.commit()
                    return {
                        "status": "tiebreak_started",
                        "duel_id": duel.id,
                        "team1_id": team_a.id,
                        "team2_id": team_b.id,
                    }

    try:
        result = manager.qualify_players_from_round1(game.id)
        db.commit()
    except (LookupError, ValueError) as e:
        db.rollback()
        logger.warning("Fin de Manche 1 : qualification impossible pour %s : %s", game.code, e)
        return {"status": "qualification_failed", "detail": str(e)}

    return {"status": "qualified", **result}