"""
Router du domaine questions/roue/validation de Manche 1 (Epic H, story H.016).
"""
import random

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app import manche1_orchestration
from app.game_helpers import require_host, require_team_token, require_team_token_or_host, award_points_with_bonus, wheel_effect_message
from app.rate_limit import limiter
from app.score_utils import apply_team_score_delta

router = APIRouter()


@router.get("/questions/random", response_model=schemas.QuestionResponse)
def get_random_question(category: str = None, difficulty: schemas.DifficultyEnum = None, db: Session = Depends(get_db)):
    """
    Obtenir une question aléatoire
    """
    query = db.query(models.Question)

    if category:
        query = query.filter(models.Question.category == category)
    if difficulty:
        query = query.filter(models.Question.difficulty == difficulty)

    question = query.order_by(func.random()).first()

    if not question:
        raise HTTPException(status_code=404, detail="Aucune question trouvée")

    # Mélanger les réponses de façon déterministe (basé sur le question_id)
    # pour que l'ordre soit stable entre les appels de polling
    import json, hashlib
    wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
    options = wrong_answers + [question.correct_answer]
    # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
    seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    rng.shuffle(options)

    return {
        "question": question,
        "options": options
    }

@router.post("/games/{code}/set-current-question")
def set_current_question(code: str, request: schemas.SetCurrentQuestionRequest, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Définir la question courante pour toutes les équipes (synchronisation)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    question = db.query(models.Question).filter(models.Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")

    # BUG-105 (story J.003) : bloque tout lancement de question tant qu'un
    # duel ping-pong est actif pour la partie, quelles que soient les
    # équipes impliquées (contrairement au garde de start_duel, filtré par
    # équipe) — le duel occupe l'écran host partagé, une question qui se
    # lance en parallèle cause de la confusion.
    active_duel = db.query(models.PingPongDuel).filter(
        models.PingPongDuel.game_session_id == game.id,
        models.PingPongDuel.is_completed == False,
    ).first()
    if active_duel:
        raise HTTPException(
            status_code=400,
            detail="Impossible de lancer une question : un duel ping-pong est en cours",
        )

    game.current_question_id = request.question_id
    db.commit()

    return {
        "message": "Question courante définie",
        "question": question.text,
        "question_id": question.id
    }

@router.get("/games/{code}/current-question")
def get_current_question(code: str, db: Session = Depends(get_db)):
    """
    Obtenir la question courante synchronisée pour toutes les équipes
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if not game.current_question_id:
        return {"message": "Pas de question courante définie", "question_id": None}

    question = db.query(models.Question).filter(models.Question.id == game.current_question_id).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")

    # Mélanger les réponses de façon déterministe (basé sur le question_id)
    # pour que l'ordre soit stable entre les appels de polling
    import json, hashlib
    wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
    options = wrong_answers + [question.correct_answer]
    # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
    seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    rng.shuffle(options)

    return {
        "question": question,
        "options": options,
        "question_id": question.id
    }

@router.get("/games/{code}/wheel-history")
def get_wheel_history(code: str, db: Session = Depends(get_db)):
    """
    BUG-106 (#8) : vue consolidée des tours de roue déjà joués pour cette
    partie, dans l'ordre chronologique — pour l'host et/ou les équipes.
    Exclut les jetons (TOKEN_*), qui sont des actions joueur et non des
    tours de roue, et n'ont pas de sens dans ce suivi.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    effects = (
        db.query(models.WheelEffect)
        .filter(
            models.WheelEffect.game_session_id == game.id,
            ~models.WheelEffect.effect_type.startswith("TOKEN_"),
        )
        .order_by(models.WheelEffect.id.asc())
        .all()
    )

    teams_by_id = {
        t.id: t
        for t in db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    }

    history = []
    for effect in effects:
        target = teams_by_id.get(effect.target_team_id)
        target_name = target.name if target else "?"
        history.append({
            "id": effect.id,
            "effect_type": effect.effect_type,
            "value": effect.value,
            "target_team_id": effect.target_team_id,
            "target_team_name": target_name,
            "message": wheel_effect_message(effect.effect_type, target_name, effect.value),
        })

    return {"history": history}

@router.get("/games/{code}/last-token-used")
def get_last_token_used(code: str, db: Session = Depends(get_db)):
    """
    Dernier jeton (SWAP/PENALTY/BONUS) utilisé par une équipe, pour informer
    l'hôte des changements globaux qu'il ne verrait sinon jamais (ex: SWAP,
    qui change la question courante de TOUTE la partie sans notification
    côté écran hôte jusqu'ici).
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    latest_token_effect = db.query(models.WheelEffect).filter(
        models.WheelEffect.game_session_id == game.id,
        models.WheelEffect.effect_type.startswith("TOKEN_"),
    ).order_by(models.WheelEffect.id.desc()).first()

    if not latest_token_effect:
        return {"last_token_used": None}

    token_type_name = latest_token_effect.effect_type.replace("TOKEN_", "")
    target_team = db.query(models.Team).filter(models.Team.id == latest_token_effect.target_team_id).first()

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

    return {
        "last_token_used": {
            "id": latest_token_effect.id,
            "user_team_id": user_team.id if user_team else None,
            "user_team_name": user_team.name if user_team else "Une équipe",
            "token_type": token_type_name,
            "target_team_id": latest_token_effect.target_team_id,
            "target_team_name": target_team.name if target_team else None,
        }
    }

@router.get("/games/{code}/answers-status")
def get_answers_status(code: str, question_id: int = None, db: Session = Depends(get_db)):
    """
    Obtenir le statut des réponses pour la question courante
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Si question_id n'est pas fourni, utiliser la question courante
    if not question_id:
        question_id = game.current_question_id
        if not question_id:
            return {"message": "Pas de question courante définie", "answered": []}

    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    team_ids = [team.id for team in teams]

    # Obtenir les réponses déjà données pour cette question
    answered_teams = db.query(models.Answer).filter(
        models.Answer.question_id == question_id,
        models.Answer.team_id.in_(team_ids)
    ).all()

    # Dédupliquer: si une équipe a soumis plusieurs réponses, compter une seule fois
    answered_ids = list(set([answer.team_id for answer in answered_teams]))
    all_ids = [team.id for team in teams]
    remaining_ids = [id for id in all_ids if id not in answered_ids]

    return {
        "question_id": question_id,
        "total_teams": len(all_ids),
        "answered_teams": answered_ids,
        "remaining_teams": remaining_ids,
        "all_answered": len(answered_ids) == len(all_ids)
    }

@router.post("/answers/", response_model=schemas.AnswerResponse)
@limiter.limit("30/minute")
def submit_answer(
    request: Request,
    answer_create: schemas.AnswerCreate,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
):
    """
    Soumettre une réponse à une question
    """
    question = db.query(models.Question).filter(models.Question.id == answer_create.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")

    team = require_team_token(db, answer_create.team_id, x_team_token)

    is_correct = answer_create.player_answer.strip().lower() == question.correct_answer.strip().lower()

    # BUG-110 : upsert atomique sur la contrainte unique (question_id, team_id).
    # Chaque coéquipier peut soumettre/corriger la réponse d'équipe tant que
    # l'host n'a pas validé ; la clause WHERE rend le verrouillage post-validation
    # atomique lui aussi (pas de fenêtre de course entre lecture et écriture).
    stmt = sqlite_insert(models.Answer).values(
        question_id=answer_create.question_id,
        team_id=answer_create.team_id,
        player_answer=answer_create.player_answer,
        is_correct=is_correct,
        points_earned=0,
    ).on_conflict_do_update(
        index_elements=[models.Answer.question_id, models.Answer.team_id],
        set_={
            "player_answer": answer_create.player_answer,
            "is_correct": is_correct,
        },
        where=models.Answer.validated_at.is_(None),
    )
    db.execute(stmt)
    db.commit()

    existing = db.query(models.Answer).filter(
        models.Answer.question_id == answer_create.question_id,
        models.Answer.team_id == answer_create.team_id,
    ).first()
    locked = existing.validated_at is not None

    # Ne révéler is_correct/correct_answer qu'une fois la réponse verrouillée
    # (validée par l'host) — sinon la soumission étant rejouable à volonté,
    # ce serait un oracle permettant de deviner la bonne réponse.
    return {
        "is_correct": existing.is_correct if locked else None,
        "correct_answer": question.correct_answer if locked else None,
        "points_earned": existing.points_earned,
        "team_score": team.score,
        "pending_validation": not locked,
    }

@router.post("/games/{code}/validate-answers")
def validate_answers(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    L'host valide les réponses de toutes les équipes pour la question courante.
    Attribue les points aux équipes qui ont répondu correctement.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if not game.current_question_id:
        raise HTTPException(status_code=400, detail="Pas de question courante à valider")

    question = db.query(models.Question).filter(models.Question.id == game.current_question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")

    # FIX: Only get answers from teams in THIS game session (not previous games)
    teams_in_game = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    team_ids_in_game = [t.id for t in teams_in_game]

    answers = db.query(models.Answer).filter(
        models.Answer.question_id == game.current_question_id,
        models.Answer.team_id.in_(team_ids_in_game)
    ).all()

    # Attribuer les points pour chaque réponse correcte (idempotent — safe to call multiple times)
    teams_updated = []
    teams_processed = set()
    for answer in answers:
        if answer.team_id in teams_processed:
            continue
        teams_processed.add(answer.team_id)
        # Récupérer l'état le plus frais possible juste avant de calculer les
        # points : une soumission concurrente a pu modifier is_correct entre
        # le SELECT initial de cette fonction et ce point de la boucle.
        db.refresh(answer)
        answer.validated_at = func.now()
        team = db.query(models.Team).filter(models.Team.id == answer.team_id).first()
        if team and answer.is_correct and answer.points_earned == 0:
            points = award_points_with_bonus(team, question.points)
            team = apply_team_score_delta(db, team.id, points)
            answer.points_earned = points
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": True,
                "points_earned": points,
                "new_score": team.score,
                "player_answer": answer.player_answer,
            })
        elif team and answer.is_correct:
            # Already validated — return existing data without double-counting
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": True,
                "points_earned": answer.points_earned,
                "new_score": team.score,
                "player_answer": answer.player_answer,
            })
        elif team:
            # Réponse fausse : pas de points, mais le bonus visait cette
            # question — il est tout de même consommé.
            team.bonus_active = False
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": False,
                "points_earned": 0,
                "new_score": team.score,
                "player_answer": answer.player_answer,
            })

    db.commit()

    # Effacer la question courante (toutes les équipes ont été validées)
    game.current_question_id = None
    db.commit()

    return {
        "message": "Réponses validées avec succès",
        "teams_updated": teams_updated,
        "question_text": question.text,
        "correct_answer": question.correct_answer,
    }

@router.post("/wheel/spin", response_model=schemas.WheelSpinResponse)
@limiter.limit("20/minute")
def spin_wheel(
    request: Request,
    wheel_spin: schemas.WheelSpinRequest,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
):
    """
    Tourner la roue de bonus/malus (tous les 5 tours selon les règles).

    Story J.004 (BUG-111) : persiste réellement l'effet (WheelEffect + score),
    comme le fait déjà trigger_wheel_effect pour le flux hostless. Ici
    l'équipe est celle choisie par le host (wheel_spin.team_id), pas une
    rotation déterministe — les deux logiques de SÉLECTION D'ÉQUIPE restent
    volontairement séparées (voir Dev Notes de la story), mais les
    PROBABILITÉS sont partagées via _roll_wheel_effect (revue de code).
    La diffusion aux écrans équipe se fait via last_wheel_event
    (get_team_specific_state), déjà fonctionnel, sans changement
    supplémentaire.
    """
    # BUG-101e : with_for_update() ne protège rien en pratique sur SQLite (le
    # moteur utilisé ici), qui l'ignore silencieusement (déjà constaté sur
    # BUG-101 pour les jetons) — la vraie protection contre une perte de mise
    # à jour vient de apply_team_score_delta() plus bas (UPDATE atomique),
    # pas d'un verrou de ligne qui n'existe pas réellement.
    team = require_team_token_or_host(db, wheel_spin.team_id, x_team_token, x_host_token)

    has_opponent = db.query(models.Team.id).filter(
        models.Team.game_session_id == team.game_session_id,
        models.Team.id != team.id,
    ).first() is not None

    spin_result, effect_type, value = manche1_orchestration._roll_wheel_effect(has_opponent)

    if effect_type == "malus":
        team = apply_team_score_delta(db, team.id, value, floor_zero=True)
        message = f"Résultat {spin_result}: Malus de 3 points"
    elif effect_type == "bonus" and value == 1:
        message = f"Résultat {spin_result}: +1 point"
        team = apply_team_score_delta(db, team.id, value)
    elif effect_type == "ping_pong":
        message = f"Résultat {spin_result}: Mode Ping Pong! Choisissez un adversaire"
    elif effect_type == "bonus" and value == 2:
        message = f"Résultat {spin_result}: pas d'adversaire disponible, +2 points à la place"
        team = apply_team_score_delta(db, team.id, value)
    else:  # bonus +3 (19-20)
        message = f"Résultat {spin_result}: Bonus de 3 points!"
        team = apply_team_score_delta(db, team.id, value)

    wheel_effect = models.WheelEffect(
        game_session_id=team.game_session_id,
        effect_type=effect_type,
        value=value,
        target_team_id=team.id,
        is_applied=True,
    )
    db.add(wheel_effect)
    db.commit()

    return {
        "effect_type": effect_type,
        "value": value,
        "message": message,
    }