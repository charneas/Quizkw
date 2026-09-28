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
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.game_helpers import generate_session_code, require_team_token
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


@router.delete("/games/public/{code}/teams/{team_id}", status_code=204)
@limiter.limit("10/minute")
def leave_public_queue(
    request: Request,
    code: str,
    team_id: int,
    x_team_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Quitte une file publique pas encore démarrée (spec-public-queue-leave).

    Supprime la place du joueur (jetons, joueur(s), équipe) en un seul commit,
    pour que les autres joueurs voient le compteur baisser à leur prochain
    poll et que le prochain arrivant reprenne cette place. Une partie non
    démarrée n'a encore aucune ligne Answer/duel/manche liée à l'équipe.
    """
    # Authentification d'abord : 403 identique pour équipe inconnue ou jeton
    # invalide (pas d'énumération des team_id, voir require_team_token).
    team = require_team_token(db, team_id, x_team_token)

    # Le code du chemin doit être celui de la partie de l'équipe : un jeton
    # valide pour une autre file ne peut pas supprimer à travers les files.
    # Même 403 qu'un mauvais jeton, pour ne pas révéler l'existence du code.
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if game is None or game.id != team.game_session_id:
        raise HTTPException(status_code=403, detail="Action réservée aux membres de cette équipe")

    if not game.is_public or game.started:
        raise HTTPException(status_code=409, detail="Impossible de quitter cette partie")

    # Course : un 4e join peut démarrer la partie entre le contrôle ci-dessus
    # et nos suppressions. Cet UPDATE no-op gardé par started=False pose un
    # verrou d'écriture sur la ligne de partie dans cette transaction (le
    # join concurrent attend) et revérifie started : 0 ligne = déjà démarrée.
    locked = (
        db.query(models.GameSession)
        .filter(models.GameSession.id == game.id, models.GameSession.started == False)  # noqa: E712
        .update({models.GameSession.started: False}, synchronize_session=False)
    )
    if locked == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Impossible de quitter cette partie")

    try:
        db.query(models.Token).filter(models.Token.team_id == team.id).delete(synchronize_session=False)
        db.query(models.Player).filter(models.Player.team_id == team.id).delete(synchronize_session=False)
        db.query(models.Team).filter(models.Team.id == team.id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Response(status_code=204)
