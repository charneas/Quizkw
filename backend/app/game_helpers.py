import secrets
from typing import Optional
import random
import string
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app import models


def award_points_with_bonus(team: models.Team, base_points: int) -> int:
    """Double les points si l'équipe a un jeton BONUS actif, puis le consomme.

    Le bonus s'applique à la question en cours d'être validée, correcte ou
    non — il est consommé dans les deux cas car il visait "cette question".
    """
    points = base_points * 2 if team.bonus_active else base_points
    team.bonus_active = False
    return points


def wheel_effect_message(effect_type: str, target_name: str, value: int | None) -> str:
    """Message d'affichage d'un effet de roue classique (hors jetons
    TOKEN_*, déjà messagés séparément). Partagé entre get_team_specific_state
    (dernier effet) et /games/{code}/wheel-history (#8) pour ne pas dupliquer
    ce formatage à deux endroits.
    """
    if effect_type == "malus":
        return f"💀 Malus : {target_name} perd {abs(value or 0)} points"
    if effect_type == "bonus":
        return f"🎉 Bonus : {target_name} gagne {value or 0} points"
    if effect_type == "ping_pong":
        return f"🏓 Duel Ping-Pong déclenché pour {target_name} !"
    if effect_type == "tiebreak":
        return f"⚖️ Égalité en fin de Manche 1 : duel de départage pour {target_name} !"
    return "Effet de roue appliqué"


# Generate a random session code
def generate_session_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def require_host(code: str, x_host_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> models.GameSession:
    """
    Dépendance FastAPI protégeant les endpoints de contrôle de partie (BUG-103).
    Le host_token est généré à la création de la partie (POST /games/) et
    connu du seul créateur : c'est la seule preuve d'identité host, il n'y a
    pas de notion de compte/session par ailleurs.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    if not x_host_token or not secrets.compare_digest(x_host_token, game.host_token):
        raise HTTPException(status_code=403, detail="Action réservée à l'hôte de la partie")
    return game


def require_host_by_game_code(game_code: str, x_host_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> models.GameSession:
    """Variante de require_host pour les routes utilisant `game_code` (Manche 2)."""
    return require_host(game_code, x_host_token, db)


def require_team_token(db: Session, team_id, x_team_token: Optional[str]) -> models.Team:
    """Analogue de require_host, à l'échelle d'une équipe (BUG-101d).
    team_token est généré à la création de l'équipe (create_team) et connu
    de tous ses membres (renvoyé aussi par join_team, qui reste public — les
    autres endpoints acceptant team_id sans vérification, plus nombreux,
    restent hors périmètre, voir #55). Prend team_id/x_team_token en
    paramètres explicites plutôt qu'en Depends() FastAPI : les endpoints
    concernés lisent team_id depuis un corps `dict` brut, pas un chemin,
    donc l'injection automatique ne s'applique pas directement ici.
    """
    if not isinstance(team_id, int):
        raise HTTPException(status_code=400, detail="team_id requis")
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    # Même 403 que l'équipe existe ou non : un 404 distinct laisserait un
    # appelant non authentifié énumérer les team_id valides — exactement ce
    # que ce token doit empêcher de deviner.
    if not team or not x_team_token or not secrets.compare_digest(x_team_token, team.team_token):
        raise HTTPException(status_code=403, detail="Action réservée aux membres de cette équipe")
    return team


def require_player_token(db: Session, player_id, x_player_token: Optional[str]) -> models.Player:
    """Analogue de require_team_token, à l'échelle d'un joueur individuel
    (Manche 2/3). player_token est reçu par le joueur à son adhésion
    (join_team) et connu de lui seul — contrairement à team_token, qui est
    partagé entre coéquipiers.
    """
    if not isinstance(player_id, int):
        raise HTTPException(status_code=400, detail="player_id requis")
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player or not x_player_token or not secrets.compare_digest(x_player_token, player.player_token):
        raise HTTPException(status_code=403, detail="Action réservée à ce joueur")
    return player


def require_team_token_or_host(
    db: Session,
    team_id,
    x_team_token: Optional[str],
    x_host_token: Optional[str],
) -> models.Team:
    """Comme require_team_token, mais accepte aussi le host_token de la partie.

    Certaines actions (tour de roue, lancement de duel ping-pong) sont
    déclenchées soit par l'équipe elle-même (mode hostless, un seul
    appareil), soit par l'hôte pour le compte d'une équipe (HostGame.tsx,
    appareil séparé qui ne connaît jamais le team_token des équipes) — les
    deux flux sont légitimes, contrairement aux endpoints purement
    self-service comme /answers/ ou /tokens/use.
    """
    if not isinstance(team_id, int):
        raise HTTPException(status_code=400, detail="team_id requis")
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=403, detail="Action réservée à l'hôte ou aux membres de cette équipe")

    if x_team_token and secrets.compare_digest(x_team_token, team.team_token):
        return team

    game = db.query(models.GameSession).filter(models.GameSession.id == team.game_session_id).first()
    if game and x_host_token and secrets.compare_digest(x_host_token, game.host_token):
        return team

    raise HTTPException(status_code=403, detail="Action réservée à l'hôte ou aux membres de cette équipe")