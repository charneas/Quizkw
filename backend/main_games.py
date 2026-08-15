"""
Router du domaine session/host lifecycle (Epic H, story H.014).
"""
import secrets

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app import manche1_orchestration
from app import team_state_service
from app.game_helpers import generate_session_code, require_host, require_team_token
from app.rate_limit import limiter

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API Quizkw !", "version": "1.0.0"}

@router.get("/health")
def health_check():
    return {"status": "healthy"}

@router.post("/games/", response_model=schemas.GameSessionResponse)
@limiter.limit("10/minute")
def create_game(request: Request, game_create: schemas.GameSessionCreate, db: Session = Depends(get_db)):
    """
    Créer une nouvelle session de jeu
    """
    # Générer un code unique
    code = generate_session_code()
    while db.query(models.GameSession).filter(models.GameSession.code == code).first():
        code = generate_session_code()

    # Créer la session
    game = models.GameSession(
        code=code,
        total_players=game_create.total_players,
        players_per_team=game_create.players_per_team,
        manche1_question_count=game_create.manche1_question_count,
        wheel_frequency=game_create.wheel_frequency,
        current_round=models.RoundType.MANCHE_1,
        is_active=True,
        started=False,
        host_token=secrets.token_urlsafe(24)
    )

    db.add(game)
    db.commit()
    db.refresh(game)

    return {
        "game": game,
        "message": f"Session de jeu créée avec le code: {code}",
        "host_token": game.host_token
    }

@router.get("/games/{code}", response_model=schemas.GameSession)
def get_game(code: str, db: Session = Depends(get_db)):
    """
    Récupérer une session de jeu par son code
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    return game

@router.post("/games/{code}/start")
def start_game(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Démarrer une session de jeu. Échoue si une équipe n'a pas encore son
    nombre complet de joueurs (BUG-201).
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Vérifier qu'il y a au moins 2 équipes
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Au moins 2 équipes sont nécessaires pour démarrer")

    # BUG-201 : l'auto-remplissage silencieux de joueurs factices
    # ("Player {team.name} {i+1}") a été retiré — le bouton "Démarrer" du
    # lobby ne bloquait pas sur les équipes incomplètes, donc ces noms
    # génériques remontaient jusqu'en Manche 2 pour de vrais joueurs qui
    # n'avaient simplement pas encore rejoint. La validation ci-dessous
    # (déjà présente, mais rendue inopérante par l'auto-fill qui la
    # satisfaisait toujours) rejette maintenant réellement ce cas.

    # Vérifier que chaque équipe a le bon nombre de joueurs
    for team in teams:
        players = db.query(models.Player).filter(models.Player.team_id == team.id).count()
        if players != game.players_per_team:
            raise HTTPException(
                status_code=400,
                detail=f"L'équipe {team.name} doit avoir {game.players_per_team} joueurs"
            )

    game.is_active = True
    game.started = True
    db.commit()

    return {"message": "Jeu démarré avec succès", "teams": len(teams)}

@router.get("/game/{code}/team/{team_id}/state")
def get_team_specific_state(
    code: str,
    team_id: int,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
):
    # Revue de sécurité H3 (2026-08-15) : cet état contient des données
    # privées à l'équipe (réponse en cours de saisie non encore verrouillée)
    # — n'importe quel spectateur connaissant team_id pouvait sinon la lire.
    require_team_token(db, team_id, x_team_token)
    return team_state_service.get_team_specific_state(db, code, team_id)

@router.post("/games/{code}/register-host")
def register_host(code: str, db: Session = Depends(get_db)):
    """
    Enregistre qu'un hôte est connecté à cette session.
    Quand un hôte est présent, la validation des réponses est manuelle (par l'hôte).
    Sans hôte, les réponses sont auto-validées quand toutes les équipes ont répondu.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    game.has_host = True
    db.commit()

    return {"message": "Hôte enregistré", "has_host": True}

@router.post("/games/{code}/next-question")
def next_question(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Passer à la question suivante (utilisable sans hôte).
    Choisit une question aléatoire et la définit comme question courante —
    sauf tous les `game.wheel_frequency` tours (roue de fortune), ou au-delà de
    `game.manche1_question_count` où la Manche 1 se termine à la place.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if game.current_round == models.RoundType.MANCHE_1 and manche1_orchestration._pending_tiebreak_duel(db, game):
        # Un duel de départage de fin de Manche 1 est en cours : on ne
        # touche à rien tant qu'il n'est pas résolu (voir submit_ping_pong_duel_answer).
        return {
            "message": "Un duel de départage est en cours, patientez.",
            "question_id": None,
        }

    game.questions_played = (game.questions_played or 0) + 1
    db.commit()

    if game.current_round == models.RoundType.MANCHE_1 and game.questions_played >= game.manche1_question_count:
        outcome = manche1_orchestration.resolve_manche1_end(db, game)
        return {
            "message": "Manche 1 terminée !",
            "question_id": None,
            "manche1_end": outcome,
        }

    if game.questions_played % game.wheel_frequency == 0:
        # Un tirage indépendant par équipe (pas une seule équipe par rotation) —
        # voir Dev Notes de trigger_wheel_effect.
        wheel_events = manche1_orchestration.trigger_wheel_effect(db, game)
        game.current_question_id = None
        db.commit()
        return {
            "message": "C'est l'heure de la roue de fortune !",
            "question_id": None,
            "wheel_events": wheel_events,
        }

    # Choisir une question aléatoire
    question = db.query(models.Question).order_by(func.random()).first()
    if not question:
        raise HTTPException(status_code=404, detail="Aucune question disponible")

    # Définir comme question courante
    game.current_question_id = question.id
    db.commit()

    return {
        "message": "Nouvelle question définie",
        "question_id": question.id,
        "question_text": question.text,
    }