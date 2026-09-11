"""File d'attente publique (spec-rooms-publiques, story 1).

Un joueur anonyme peut rejoindre une partie complète sans code partagé :
POST /games/public/join trouve ou crée une `GameSession(is_public=True)`
en équipes-de-1 (players_per_team=1, total_players=4), crée team+player
atomiquement, et déclenche le démarrage automatique côté serveur (sans
host_token, voir `_start_game_core`) dès le 4e arrivant.

Aucune tâche planifiée : une file trop ancienne (> PUBLIC_QUEUE_TTL_MINUTES)
ou déjà démarrée est simplement ignorée par le filtre de recherche
ci-dessous, et un nouveau joueur en crée une fraîche à la place — c'est ce
même filtre qui gère aussi bien l'expiration (CAP-6) que le routage d'un 5e
joueur arrivé après assemblage vers une nouvelle vague (CAP-4).

Pas de verrou distribué contre la course "deux 1ers joueurs créent chacun
une file simultanément" (voir Never de la story) : limitation acceptée vu le
trafic attendu faible.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.game_helpers import generate_session_code
from app.pseudo_filter import contains_forbidden_word
from app.rate_limit import limiter
from main_games import _start_game_core

router = APIRouter()

# Choix de durée non critique (aucun humain ne le remarque directement) —
# valeur raisonnable, facilement ajustable ici plutôt que répétée en dur.
PUBLIC_QUEUE_TTL_MINUTES = 10

PUBLIC_QUEUE_PLAYERS_PER_TEAM = 1
PUBLIC_QUEUE_TOTAL_PLAYERS = 4


def _find_open_public_queue(db: Session) -> models.GameSession | None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PUBLIC_QUEUE_TTL_MINUTES)
    return (
        db.query(models.GameSession)
        .filter(
            models.GameSession.is_public == True,  # noqa: E712
            models.GameSession.started == False,  # noqa: E712
            models.GameSession.created_at > cutoff,
        )
        .order_by(models.GameSession.created_at.asc())
        .first()
    )


def _create_public_queue(db: Session) -> models.GameSession:
    code = generate_session_code()
    while db.query(models.GameSession).filter(models.GameSession.code == code).first():
        code = generate_session_code()

    game = models.GameSession(
        code=code,
        total_players=PUBLIC_QUEUE_TOTAL_PLAYERS,
        players_per_team=PUBLIC_QUEUE_PLAYERS_PER_TEAM,
        current_round=models.RoundType.MANCHE_1,
        is_active=True,
        started=False,
        is_public=True,
    )
    db.add(game)
    db.flush()
    return game


@router.post("/games/public/join", response_model=schemas.PublicQueueJoinResponse)
@limiter.limit("10/minute")
def join_public_queue(request: Request, body: schemas.PublicQueueJoinRequest, db: Session = Depends(get_db)):
    """Rejoint la file publique ouverte (ou en crée une nouvelle), crée une
    équipe-de-1 + son joueur en un seul appel atomique, et déclenche le
    démarrage automatique si ce joueur est le 4e.
    """
    if contains_forbidden_word(body.name):
        raise HTTPException(status_code=400, detail="Ce pseudo n'est pas autorisé")

    game = _find_open_public_queue(db)
    if game is not None:
        # Même garde de capacité que create_team : si la file trouvée est déjà
        # pleine (course entre deux joins quasi simultanés), on l'ignore et on
        # en crée une fraîche plutôt que d'insérer une 5e équipe dedans.
        max_teams = game.total_players // game.players_per_team
        current_teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).count()
        if current_teams >= max_teams:
            game = None
    if game is None:
        game = _create_public_queue(db)

    # Même garde d'unicité de nom que create_team (une équipe = un pseudo ici).
    existing_names = db.query(models.Team.name).filter(models.Team.game_session_id == game.id).all()
    if body.name.strip().lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce pseudo est déjà pris dans cette file")

    team = models.Team(name=body.name, game_session_id=game.id, score=0)
    db.add(team)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ce pseudo est déjà pris dans cette file")

    # Les 3 jetons standards (SWAP/PENALTY/BONUS), comme create_team.
    for token_type in (models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS):
        db.add(models.Token(team_id=team.id, token_type=token_type, is_used=False))

    player = models.Player(name=body.name, team_id=team.id)
    db.add(player)
    db.flush()

    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    if len(teams) >= game.total_players // game.players_per_team:
        # 4e arrivant : démarrage serveur, équivalent de start_game mais sans
        # host_token (personne n'en détient pour une partie assemblée auto).
        _start_game_core(db, game, teams)

    db.commit()
    db.refresh(game)
    db.refresh(team)
    db.refresh(player)

    return schemas.PublicQueueJoinResponse(
        code=game.code,
        game=game,
        team_id=team.id,
        team_token=team.team_token,
        player_id=player.id,
        player_token=player.player_token,
    )
