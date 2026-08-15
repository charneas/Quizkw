"""
Router du domaine équipes/joueurs/tokens (Epic H, story H.015).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import or_, case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.game_helpers import require_team_token
from app.rate_limit import limiter

router = APIRouter()

PENALTY_POINTS = 2


@router.post("/games/{code}/teams/", response_model=schemas.TeamWithToken)
def create_team(code: str, team_create: schemas.TeamCreate, db: Session = Depends(get_db)):
    """
    Créer une équipe dans une session de jeu
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Vérifier le nombre maximum d'équipes
    max_teams = game.total_players // game.players_per_team
    current_teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).count()

    if current_teams >= max_teams:
        raise HTTPException(status_code=400, detail="Nombre maximum d'équipes atteint")

    existing_names = db.query(models.Team.name).filter(models.Team.game_session_id == game.id).all()
    if team_create.name.strip().lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce nom d'équipe est déjà pris dans cette partie")

    team = models.Team(
        name=team_create.name,
        game_session_id=game.id,
        score=0,
        icon=team_create.icon,
    )

    db.add(team)
    db.commit()
    db.refresh(team)

    # Donner 3 jetons à l'équipe
    token_types = [models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS]
    for token_type in token_types:
        token = models.Token(
            team_id=team.id,
            token_type=token_type,
            is_used=False
        )
        db.add(token)

    db.commit()

    return team

@router.patch("/games/{code}/teams/{team_id}", response_model=schemas.Team)
def rename_team(
    code: str,
    team_id: int,
    team_update: schemas.TeamCreate,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
):
    """Renommage d'équipe par ses propres membres (X-Team-Token), même garde
    d'unicité de nom que create_team."""
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    team = require_team_token(db, team_id, x_team_token)
    if team.game_session_id != game.id:
        raise HTTPException(status_code=404, detail="Équipe introuvable dans cette partie")

    new_name = team_update.name
    existing_names = db.query(models.Team.name).filter(
        models.Team.game_session_id == game.id,
        models.Team.id != team.id,
    ).all()
    if new_name.lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce nom d'équipe est déjà pris dans cette partie")

    team.name = new_name
    team.icon = team_update.icon
    db.commit()
    db.refresh(team)
    return team

@router.post("/games/{code}/teams/{team_id}/players/", response_model=schemas.PlayerWithTeamToken)
def join_team(code: str, team_id: int, player_create: schemas.PlayerCreate, db: Session = Depends(get_db)):
    """
    Rejoindre une équipe existante en tant que joueur, avec son pseudo.

    C'est le vrai point d'entrée du pseudo en Manche 1 (auparavant, les
    joueurs n'étaient jamais nommés réellement : `start_game` les générait
    automatiquement en "Player <équipe> <n>" — bug utilisateur). Les joueurs
    ainsi créés sont ensuite ceux qualifiés pour la Manche 2 par
    qualify_players_from_round1, qui lit team.players.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if game.started:
        raise HTTPException(status_code=400, detail="La partie a déjà démarré")

    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.game_session_id == game.id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe non trouvée dans cette partie")

    current_count = db.query(models.Player).filter(models.Player.team_id == team.id).count()
    if current_count >= game.players_per_team:
        raise HTTPException(status_code=400, detail="Cette équipe est déjà complète")

    existing_names = db.query(models.Player.name).filter(models.Player.team_id == team.id).all()
    if player_create.name.strip().lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce pseudo est déjà pris dans cette équipe")

    player = models.Player(name=player_create.name, team_id=team.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    # team_token n'est pas une colonne de Player : construit explicitement
    # plutôt que sérialisé depuis l'objet ORM (BUG-101d).
    return schemas.PlayerWithTeamToken(
        id=player.id,
        name=player.name,
        team_id=player.team_id,
        team_token=team.team_token,
        player_token=player.player_token,
    )

@router.post("/games/{code}/players/", response_model=schemas.Player)
def create_player(code: str, player_create: schemas.PlayerCreate, db: Session = Depends(get_db)):
    """
    Create a player in a game session (for Round 2 individual play)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    # For Round 2, players can be created without team (will be assigned later or stay individual)
    player = models.Player(
        name=player_create.name,
        team_id=None  # Allow null for Round 2 individual play
    )

    db.add(player)
    db.commit()
    db.refresh(player)

    return player

@router.get("/teams/{team_id}/tokens")
def get_team_tokens(team_id: int, db: Session = Depends(get_db), x_team_token: Optional[str] = Header(default=None)):
    """
    Récupérer les jetons disponibles pour une équipe

    Revue de sécurité H4 (2026-08-15) : exposait les jetons de n'importe
    quelle équipe (info utile pour anticiper un SWAP/PENALTY adverse).
    """
    require_team_token(db, team_id, x_team_token)
    tokens = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False
    ).all()

    # CORRECTION : Renvoyer directement le tableau (la liste) attendu par le frontend
    return [
        {
            "id": token.id,
            "token_type": token.token_type.value,
            "is_used": token.is_used
        } for token in tokens
    ]

@router.post("/tokens/use")
@limiter.limit("20/minute")
def use_token(request: Request, data: dict, db: Session = Depends(get_db), x_team_token: Optional[str] = Header(default=None)):
    team_id = data.get("team_id")
    target_team_id = data.get("target_team_id")
    token_type = data.get("token_type", "").upper()  # Ex: "SWAP", "PENALTY", "BONUS"

    # BUG-101d : sans ça, n'importe quel client connaissant un team_id pouvait
    # consommer les jetons d'une équipe qui n'est pas la sienne.
    caller_team = require_team_token(db, team_id, x_team_token)

    # Le jeton PENALTY cible une équipe adverse précise : on valide la cible
    # avant de consommer le jeton, pour ne pas le perdre sur une requête invalide.
    target_team = None
    if token_type == "PENALTY":
        if not target_team_id:
            raise HTTPException(status_code=400, detail="Une équipe cible est requise pour utiliser un jeton PENALTY")
        if target_team_id == team_id:
            raise HTTPException(status_code=400, detail="Impossible de cibler sa propre équipe")
        target_team = db.query(models.Team).filter(
            models.Team.id == target_team_id,
            models.Team.game_session_id == caller_team.game_session_id,
        ).first()
        if not target_team:
            raise HTTPException(status_code=404, detail="Équipe cible non trouvée dans cette partie")

    # Consomme le jeton via un UPDATE conditionnel (WHERE id=... AND
    # is_used=False), et vérifie le nombre de lignes modifiées, plutôt qu'un
    # SELECT suivi d'une écriture séparée sur l'objet en mémoire. Portable
    # SQLite/PostgreSQL — contrairement à SELECT ... FOR UPDATE, qui est un
    # no-op silencieux sur SQLite (le moteur utilisé en production ici) et ne
    # protégeait donc pas réellement contre la course entre deux requêtes
    # concurrentes sur le même jeton (ex. deux coéquipiers cliquant SWAP au
    # même moment), cause de BUG-101 : "swaps infinis". L'UPDATE lui-même
    # sérialise les écritures concurrentes ; seule l'une d'elles peut modifier
    # une ligne encore à is_used=False, l'autre affecte 0 ligne.
    candidate_token = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.token_type == token_type,
        models.Token.is_used == False
    ).first()

    chosen_token = None
    if candidate_token:
        rows_updated = db.query(models.Token).filter(
            models.Token.id == candidate_token.id,
            models.Token.is_used == False
        ).update({"is_used": True}, synchronize_session=False)
        if rows_updated:
            candidate_token.is_used = True
            chosen_token = candidate_token

    # Si le jeton de ce type existe et était disponible, on applique son effet
    if chosen_token:
        penalized_teams = []

        if token_type == "PENALTY" and target_team:
            # Mise à jour atomique du score (UPDATE ... SET score = CASE ...,
            # même logique portable que plus haut) plutôt qu'un
            # read-modify-write sur l'objet Python : deux PENALTY concurrentes
            # visant la même équipe perdraient sinon l'une des deux
            # pénalités (BUG-101b).
            db.query(models.Team).filter(models.Team.id == target_team.id).update(
                {
                    "score": case(
                        (models.Team.score - PENALTY_POINTS < 0, 0),
                        else_=models.Team.score - PENALTY_POINTS,
                    )
                },
                synchronize_session=False,
            )
            db.refresh(target_team)
            penalized_teams.append({"team_id": target_team.id, "new_score": target_team.score})
        elif token_type == "BONUS":
            # Consommé à la prochaine validation de réponse de cette équipe (voir validate_answers).
            caller_team.bonus_active = True
        elif token_type == "SWAP":
            # En duel ping-pong : change le thème du duel (le jeton ne
            # touchait jusqu'ici que la question de Manche 1, jamais le
            # thème d'un duel en cours — bug utilisateur). Sinon : change la
            # question courante de la partie.
            # order_by en défense en profondeur : PingPongManager.start_duel
            # empêche désormais qu'une équipe se retrouve dans 2 duels actifs
            # (BUG-101c), mais si ce garde-fou était contourné, on cible le
            # duel le plus récent plutôt qu'un résultat arbitraire.
            active_duel = db.query(models.PingPongDuel).filter(
                models.PingPongDuel.is_completed == False,
                or_(
                    models.PingPongDuel.team1_id == team_id,
                    models.PingPongDuel.team2_id == team_id,
                ),
            ).order_by(models.PingPongDuel.id.desc()).first()
            if active_duel:
                new_theme = db.query(models.PingPongTheme).filter(
                    models.PingPongTheme.id != active_duel.theme_id
                ).order_by(func.random()).first()
                if new_theme:
                    active_duel.theme_id = new_theme.id
                    active_duel.answers_used = []
            else:
                game = db.query(models.GameSession).filter(
                    models.GameSession.id == caller_team.game_session_id
                ).first()
                if game and game.current_question_id:
                    new_question = db.query(models.Question).filter(
                        models.Question.id != game.current_question_id
                    ).order_by(func.random()).first()
                    if new_question:
                        game.current_question_id = new_question.id

# --- AJOUT : Enregistrer l'événement du jeton pour la synchronisation React ---
        if caller_team:
            # Pour une PÉNALITÉ, la cible est l'équipe victime (target_team_id).
            # Pour un SWAP ou BONUS, la cible enregistrée doit être l'équipe qui joue (team_id).
            actual_target = target_team_id if (token_type == "PENALTY" and target_team_id) else team_id

            # Pour PENALTY, on encode l'équipe émettrice dans `value` (colonne
            # sinon inutilisée pour ce type d'effet) : c'est ce qui permet à
            # team_state_service de retrouver l'auteur réel de la pénalité au
            # lieu de deviner "une équipe qui n'est pas la cible" (faux dès
            # qu'il y a 3+ équipes).
            token_event = models.WheelEffect(
                game_session_id=caller_team.game_session_id,
                effect_type=f"TOKEN_{token_type}",
                value=team_id if token_type == "PENALTY" else None,
                target_team_id=actual_target,
                is_applied=True
            )
            db.add(token_event)

        db.commit()
        return {
            "status": "success",
            "message": f"Jeton {token_type} consommé avec succès.",
            "token_type": token_type,
            "penalized_teams": penalized_teams,
        }

    # S'il n'existe pas ou a déjà été utilisé
    raise HTTPException(
        status_code=400,
        detail=f"Jeton {token_type} non disponible ou déjà utilisé !"
    )