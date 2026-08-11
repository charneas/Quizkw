import hashlib
import json
import random

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.game_helpers import wheel_effect_message
from app.ping_pong_manager import PingPongManager


def get_team_specific_state(db: Session, code: str, team_id: int) -> dict:
    """
    Retourne l'état spécifique à UNE équipe pour le jeu multi-écrans.

    Chaque équipe peut avoir son propre appareil et voir :
    - Si c'est son tour de répondre
    - La question courante (si elle n'a pas déjà répondu)
    - Les duels ping-pong en cours (si elle est impliquée)
    - Ses jetons disponibles
    - Son score actuel
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Récupérer l'équipe
    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.game_session_id == game.id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe non trouvée dans cette session")

    # --- Statut de la question courante ---
    current_question_data = None
    has_answered = False
    answer_locked = False
    current_team_answer = None
    is_my_turn = True  # par défaut

    if game.current_question_id:
        question = db.query(models.Question).filter(
            models.Question.id == game.current_question_id
        ).first()

        if question:
            # Vérifier si cette équipe a déjà répondu à cette question.
            # BUG-110 : has_answered ne verrouille plus le formulaire tant que
            # l'host n'a pas validé — n'importe quel coéquipier peut corriger
            # la réponse jusque-là (answer_locked = réponse validée par l'host).
            existing_answer = db.query(models.Answer).filter(
                models.Answer.question_id == question.id,
                models.Answer.team_id == team_id,
            ).first()

            has_answered = existing_answer is not None
            answer_locked = existing_answer is not None and existing_answer.validated_at is not None
            current_team_answer = existing_answer.player_answer if existing_answer else None

            # Mélanger les réponses de façon déterministe (basé sur le question_id)
            # pour que l'ordre soit stable entre les appels de polling
            wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
            options = wrong_answers + [question.correct_answer]
            # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
            seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            rng.shuffle(options)

            current_question_data = {
                "id": question.id,
                "text": question.text,
                "category": question.category,
                "difficulty": question.difficulty.value,
                "points": question.points,
                "correct_answer": question.correct_answer if answer_locked else None,  # Ne révéler qu'après validation host
                "options": options,
                "answer_locked": answer_locked,
                "current_team_answer": current_team_answer,
                "image_url": question.image_url,
            }

    # Vérifier le statut des réponses pour déterminer si c'est le tour
    if game.current_question_id:
        teams_in_game = db.query(models.Team).filter(
            models.Team.game_session_id == game.id
        ).all()
        team_ids_in_game = [t.id for t in teams_in_game]

        answered_teams = db.query(models.Answer).filter(
            models.Answer.question_id == game.current_question_id,
            models.Answer.team_id.in_(team_ids_in_game),
        ).all()
        # Dédupliquer: une équipe peut avoir soumis plusieurs réponses
        answered_ids = list(set([a.team_id for a in answered_teams]))

        # Si toutes les équipes ont répondu, personne n'a "le tour"
        if len(answered_ids) == len(team_ids_in_game):
            is_my_turn = False

    # --- Duel Ping-Pong en cours ---
    ping_pong_manager = PingPongManager(db)
    active_duel_for_team = None

    # Chercher un duel actif où cette équipe est impliquée. Une seule requête
    # avec OR, triée par le plus récent (BUG-101c) — l'ancien schéma en deux
    # requêtes séparées (team1 d'abord, puis team2 en repli) pouvait désigner
    # un duel différent de celui utilisé par le jeton SWAP dans /tokens/use
    # si l'équipe se retrouvait dans plusieurs duels actifs.
    active_duel = db.query(models.PingPongDuel).filter(
        models.PingPongDuel.game_session_id == game.id,
        models.PingPongDuel.is_completed == False,
        or_(
            models.PingPongDuel.team1_id == team_id,
            models.PingPongDuel.team2_id == team_id,
        ),
    ).order_by(models.PingPongDuel.id.desc()).first()

    if active_duel:
        try:
            duel_state = ping_pong_manager.get_duel_state(active_duel.id)
            active_duel_for_team = {
                "duel_id": active_duel.id,
                "theme": duel_state["theme"],
                "team1": duel_state["team1"],
                "team2": duel_state["team2"],
                "current_turn_team_id": duel_state["current_turn_team_id"],
                "current_turn_team_name": duel_state["current_turn_team_name"],
                "turn_number": duel_state["turn_number"],
                "answers_used": duel_state["answers_used"],
                "is_completed": duel_state["is_completed"],
                "winner_team_id": duel_state["winner_team_id"],
                "is_cancelled": duel_state["is_cancelled"],
                "is_my_turn_in_duel": active_duel.current_turn_team_id == team_id,
            }
        except Exception:
            pass  # Duel not found or error — leave as None

    # --- Duel Ping-Pong à titre spectateur (BUG-104 / Story J.001) ---
    # Une équipe n'ayant pas de duel actif (active_duel est None) peut malgré
    # tout vouloir suivre le duel d'une autre équipe en lecture seule. On
    # prend le duel le plus récent de la partie auquel cette équipe ne
    # participe PAS (avant ou après complétion — pas de filtre is_completed,
    # même convention que last_wheel_event/last_token_event : "dernier
    # événement", pas "événement encore actif"), pour que le spectateur voie
    # aussi le résultat une fois le duel terminé.
    spectator_duel = None
    if not active_duel_for_team:
        latest_other_duel = db.query(models.PingPongDuel).filter(
            models.PingPongDuel.game_session_id == game.id,
            models.PingPongDuel.team1_id != team_id,
            models.PingPongDuel.team2_id != team_id,
        ).order_by(models.PingPongDuel.id.desc()).first()
        if latest_other_duel:
            try:
                duel_state = ping_pong_manager.get_duel_state(latest_other_duel.id)
                spectator_duel = {
                    "duel_id": latest_other_duel.id,
                    "theme": duel_state["theme"],
                    "team1": duel_state["team1"],
                    "team2": duel_state["team2"],
                    "current_turn_team_id": duel_state["current_turn_team_id"],
                    "current_turn_team_name": duel_state["current_turn_team_name"],
                    "turn_number": duel_state["turn_number"],
                    "answers_used": duel_state["answers_used"],
                    "is_completed": duel_state["is_completed"],
                    "winner_team_id": duel_state["winner_team_id"],
                    "is_cancelled": duel_state["is_cancelled"],
                    "is_my_turn_in_duel": False,
                }
            except Exception:
                pass

    # --- Jetons ---
    tokens = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False,
    ).all()

    tokens_data = [
        {"id": t.id, "token_type": t.token_type.value, "is_used": t.is_used}
        for t in tokens
    ]

    # --- Statut des autres équipes ---
    # Calculé indépendamment de la question courante : nécessaire pour cibler
    # une PENALTY ou choisir un adversaire de ping-pong même entre deux questions.
    teams_in_game = db.query(models.Team).filter(
        models.Team.game_session_id == game.id
    ).all()
    other_teams_status = []
    for t in teams_in_game:
        if t.id == team_id:
            continue
        other_teams_status.append({
            "team_id": t.id,
            "team_name": t.name,
            "team_score": t.score,
            "has_answered": t.id in answered_ids if game.current_question_id else False,
        })

    # Un host est désormais toujours présent (BUG-103) : la validation des
    # réponses est systématiquement manuelle, via /validate-answers.
    all_teams_answered = False
    validation_result_data = None

    if game.current_question_id:
        all_teams_answered = (
            len(answered_ids) == len(team_ids_in_game) and len(team_ids_in_game) > 0
        )
    else:
        # BUG (#50) : validate_answers remet current_question_id à None juste
        # après validation, donc côté équipe on ne peut plus s'appuyer sur
        # current_question pour afficher le résultat. On retrouve ici la
        # dernière question que CETTE équipe a vu validée, puis on reconstruit
        # le même résumé toutes-équipes que /validate-answers renvoyait à
        # l'host (shape attendue par TeamScreen.tsx : correct_answer + teams[]).
        # Dès qu'une nouvelle question démarre, current_question_id est
        # repeuplé, on retombe dans la branche ci-dessus et validation_result
        # disparaît naturellement.
        last_validated_answer = (
            db.query(models.Answer)
            .filter(
                models.Answer.team_id == team_id,
                models.Answer.validated_at.isnot(None),
            )
            .order_by(models.Answer.validated_at.desc())
            .first()
        )
        if last_validated_answer:
            validated_question = db.query(models.Question).filter(
                models.Question.id == last_validated_answer.question_id
            ).first()
            if validated_question:
                teams_in_game_for_result = db.query(models.Team).filter(
                    models.Team.game_session_id == game.id
                ).all()
                team_ids_for_result = [t.id for t in teams_in_game_for_result]
                validated_answers = db.query(models.Answer).filter(
                    models.Answer.question_id == validated_question.id,
                    models.Answer.team_id.in_(team_ids_for_result),
                    models.Answer.validated_at.isnot(None),
                ).all()
                answers_by_team = {a.team_id: a for a in validated_answers}
                validation_result_data = {
                    "correct_answer": validated_question.correct_answer,
                    "teams": [
                        {
                            "team_name": t.name,
                            "is_correct": answers_by_team[t.id].is_correct,
                            "points_earned": answers_by_team[t.id].points_earned,
                            "player_answer": answers_by_team[t.id].player_answer,
                        }
                        for t in teams_in_game_for_result
                        if t.id in answers_by_team
                    ],
                }

    # --- Dernier effet de roue (pour afficher un modal sur tous les écrans,
    # y compris ceux qui n'ont pas cliqué sur "Tour suivant") ---
    last_wheel_event = None
    last_token_used = None

    # Requêtes séparées par catégorie (jeton vs effet de roue classique) :
    # avec une seule requête "dernier effet toutes catégories confondues",
    # une pénalité pouvait être masquée par un effet de roue survenu juste
    # après elle (avant le prochain poll de l'équipe visée), et la
    # notification de pénalité n'apparaissait jamais côté équipe.
    latest_token_effect = db.query(models.WheelEffect).filter(
        models.WheelEffect.game_session_id == game.id,
        models.WheelEffect.effect_type.startswith("TOKEN_"),
    ).order_by(models.WheelEffect.id.desc()).first()

    latest_wheel_effect = db.query(models.WheelEffect).filter(
        models.WheelEffect.game_session_id == game.id,
        ~models.WheelEffect.effect_type.startswith("TOKEN_"),
    ).order_by(models.WheelEffect.id.desc()).first()

    if latest_token_effect:
        token_type_name = latest_token_effect.effect_type.replace("TOKEN_", "")
        target_team = db.query(models.Team).filter(models.Team.id == latest_token_effect.target_team_id).first()

        # Pour SWAP / BONUS, l'émetteur est la cible (l'équipe qui a cliqué).
        # Pour PENALTY, l'émetteur est encodée dans `value` depuis #main_teams
        # (l'équipe qui n'est pas la cible ne suffit plus dès 3+ équipes).
        if token_type_name == "PENALTY":
            user_team = None
            if latest_token_effect.value:
                user_team = db.query(models.Team).filter(models.Team.id == latest_token_effect.value).first()
            if not user_team:
                user_team = db.query(models.Team).filter(
                    models.Team.game_session_id == game.id,
                    models.Team.id != latest_token_effect.target_team_id
                ).first()
        else:
            user_team = target_team

        last_token_used = {
            "id": latest_token_effect.id,
            "user_team_id": user_team.id if user_team else team_id,
            "user_team_name": user_team.name if user_team else "Une équipe",
            "token_type": token_type_name,
            "target_team_id": latest_token_effect.target_team_id,
            "target_team_name": target_team.name if target_team else None
        }

    if latest_wheel_effect:
        target = db.query(models.Team).filter(models.Team.id == latest_wheel_effect.target_team_id).first()
        target_name = target.name if target else "?"
        message = wheel_effect_message(latest_wheel_effect.effect_type, target_name, latest_wheel_effect.value)

        last_wheel_event = {
            "id": latest_wheel_effect.id,
            "effect_type": latest_wheel_effect.effect_type,
            "value": latest_wheel_effect.value,
            "target_team_id": latest_wheel_effect.target_team_id,
            "target_team_name": target_name,
            "message": message,
        }

    return {
        "team_id": team_id,
        "team_name": team.name,
        "team_score": team.score,
        "game_session_id": game.id,
        "game_started": game.started,
        "game_phase": game.current_round.value,
        "is_my_turn": is_my_turn,
        "has_answered": has_answered,
        "answer_locked": answer_locked,
        "current_question": current_question_data,
        "active_duel": active_duel_for_team,
        "spectator_duel": spectator_duel,
        "tokens": tokens_data,
        "other_teams": other_teams_status,
        "all_answered": all_teams_answered,
        "validation_result": validation_result_data,
        "last_wheel_event": last_wheel_event,
         "last_token_used": last_token_used  # <-- CHAMP AJOUTÉ POUR SYNCHRO REACT
    }