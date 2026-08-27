"""Connexion Discord facultative (Epic O, Story O.1.1, AD-19/AD-22).

Flux authorization-code standard : `GET /auth/discord/login` redirige vers
l'écran de consentement Discord, `GET /auth/discord/callback` échange le code,
résout-ou-crée l'Account via `account_manager.py`, pose un cookie de session
Discord signé (secret dédié, distinct du cookie admin AD-17) puis redirige
vers l'accueil. Aucune garde d'authentification sur ces deux routes elles-mêmes
— on ne peut pas exiger le cookie qu'on cherche justement à obtenir (même
traitement que `POST /admin/login`, F-ext-2.1).

Revue de code (2026-08-27) : validation des variables d'environnement Discord
différée (lazy) — l'absence de configuration Discord ne doit jamais empêcher
le reste de l'API (mode invité) de démarrer, contrairement au pattern
fail-fast-au-démarrage de SESSION_SECRET_KEY (AD-17), qui suppose l'admin
toujours configuré. Décision utilisateur explicite, cf. Review Findings de
cette story."""
import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import URLSafeSerializer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.account_manager import DISCORD_COOKIE_NAME, resolve_account_from_request, resolve_or_create_account
from app.database import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

# Story O.2.1 : nom de cookie promu dans account_manager.py (partagé avec
# main_teams.py) — réutilisé ici tel quel plutôt que redéfini une deuxième fois.
COOKIE_NAME = DISCORD_COOKIE_NAME
STATE_COOKIE_NAME = "discord_oauth_state"
# AD-22 : cookie envoyé uniquement sur HTTPS, même logique que SESSION_COOKIE_SECURE (AD-17).
DISCORD_SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"
DISCORD_SCOPE = "identify"  # strict minimum — jamais `email` (AC #7/FR7)

# Pas d'expiration de signature (URLSafeSerializer, pas URLSafeTimedSerializer) :
# AD-22 ne l'exige pas ("stateless, no session table") et FR3 va dans le sens
# inverse ("la session ne doit idéalement jamais expirer en cours de partie").
# max_age du cookie lui-même volontairement long (voir DISCORD_SESSION_COOKIE_MAX_AGE_SECONDS
# ci-dessous) pour que le cookie survive une fermeture de navigateur — sans
# max_age, ce serait un cookie de session navigateur, plus éphémère que le
# cookie admin qu'il devait pourtant surpasser en durée de vie (trouvé en
# revue de code). Point réversible, pas gravé dans AD-22.
DISCORD_SESSION_COOKIE_MAX_AGE_SECONDS = int(
    os.getenv("DISCORD_SESSION_COOKIE_MAX_AGE_SECONDS", str(365 * 24 * 3600))
)
# Cookie d'état CSRF (RFC 6749 §10.12) : courte durée de vie, juste le temps
# de l'aller-retour vers l'écran de consentement Discord.
STATE_COOKIE_MAX_AGE_SECONDS = 600

router = APIRouter(prefix="/auth/discord", tags=["Auth Discord"])


def _require_discord_config() -> dict[str, str]:
    """Valide les 4 variables d'environnement Discord à l'appel, pas à l'import
    du module (revue de code 2026-08-27) : un déploiement sans Discord configuré
    reste un mode invité pleinement fonctionnel — seules ces routes échouent."""
    missing = [
        name
        for name in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_REDIRECT_URI", "DISCORD_SESSION_SECRET_KEY")
        if not os.getenv(name)
    ]
    if missing:
        logger.error("Connexion Discord indisponible — variables manquantes: %s", ", ".join(missing))
        raise HTTPException(status_code=503, detail="Connexion Discord indisponible (configuration manquante).")
    return {
        "client_id": os.environ["DISCORD_CLIENT_ID"],
        "client_secret": os.environ["DISCORD_CLIENT_SECRET"],
        "redirect_uri": os.environ["DISCORD_REDIRECT_URI"],
        "session_secret_key": os.environ["DISCORD_SESSION_SECRET_KEY"],
    }


def _serializer(session_secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(session_secret_key, salt="discord-session")


def sign_discord_session(discord_id: str, session_secret_key: str) -> str:
    return _serializer(session_secret_key).dumps({"discord_id": discord_id})


def _avatar_url(discord_id: str, avatar_hash: str | None) -> str:
    """Construit l'URL CDN Discord affichable par `profil-button-connected`
    (DESIGN.md) — `Account.avatar` ne stocke qu'un hash, jamais une URL
    complète. Sans avatar personnalisé, Discord retombe sur un avatar par
    défaut indexé par l'identifiant (formule officielle Discord)."""
    if avatar_hash:
        return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
    default_index = (int(discord_id) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"


def _current_account(request: Request, db: Session) -> models.Account | None:
    """Résout l'Account courant à partir du cookie de session Discord, sans
    jamais en créer un nouveau (contrairement au callback OAuth) : une lecture
    seule (Task 1, Story O.1.2). Délègue entièrement à
    `account_manager.resolve_account_from_request` (Story O.2.1/O.2.2, revue
    de code) — une seule requête DB, partagée avec `join_team`/`create_player`
    (qui n'ont besoin que de l'id) plutôt que deux requêtes séparées relisant
    la même ligne. Signature invalide, cookie absent, secret non configuré, ou
    Account supprimé entre-temps (AD-21) sont tous traités uniformément comme
    "non connecté" (401), jamais comme une erreur serveur — contrairement à
    l'ancien `_require_discord_config()` qui levait une 503."""
    return resolve_account_from_request(request, db)


@router.get("/login")
@limiter.limit("20/minute")
def discord_login(request: Request):
    config = _require_discord_config()
    # RFC 6749 §10.12 : `state` aléatoire, posé dans un cookie CSRF de courte
    # durée et renvoyé par Discord tel quel — comparé au retour (AC de sécurité
    # trouvée en revue de code, absente de la version initiale).
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": DISCORD_SCOPE,
        "state": state,
    }
    redirect = RedirectResponse(f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}")
    redirect.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        # Lax, pas Strict : ce cookie doit être renvoyé par le navigateur sur la
        # navigation top-level cross-site initiée par la redirection Discord
        # vers /callback — un cookie Strict ne le serait pas.
        samesite="lax",
        secure=DISCORD_SESSION_COOKIE_SECURE,
        max_age=STATE_COOKIE_MAX_AGE_SECONDS,
    )
    return redirect


@router.get("/callback")
@limiter.limit("20/minute")
def discord_callback(request: Request, db: Session = Depends(get_db)):
    config = _require_discord_config()

    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    code = request.query_params.get("code")
    query_state = request.query_params.get("state")
    error = request.query_params.get("error")

    def _guest_redirect(reason: str) -> RedirectResponse:
        logger.warning("Échec de connexion Discord (%s)", reason)
        redirect = RedirectResponse("/")
        redirect.delete_cookie(key=STATE_COOKIE_NAME)
        return redirect

    if error:
        # Refus de l'utilisateur sur l'écran de consentement Discord, ou erreur
        # Discord explicite (AC #5) — retour silencieux à l'accueil en invité.
        return _guest_redirect(f"discord error={error}")

    if not code:
        return _guest_redirect("code manquant")

    if not cookie_state or not query_state or not secrets.compare_digest(cookie_state, query_state):
        return _guest_redirect("state CSRF invalide ou absent")

    try:
        with httpx.Client(timeout=10.0) as client:
            token_resp = client.post(
                DISCORD_TOKEN_URL,
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config["redirect_uri"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            user_resp = client.get(
                DISCORD_USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            user_data = user_resp.json()

            discord_id = str(user_data["id"])
            pseudo = user_data["username"]
            avatar = user_data.get("avatar")

            resolve_or_create_account(db, discord_id=discord_id, pseudo=pseudo, avatar=avatar)
    except (httpx.HTTPError, KeyError, ValueError, SQLAlchemyError) as exc:
        # Erreur réseau/timeout, réponse Discord inattendue, ou échec de
        # résolution-ou-création (AC #5) : aucun Account créé (ou laissé tel
        # quel), aucun cookie posé, retour silencieux à l'accueil. La
        # résolution-ou-création est volontairement dans ce même try : une
        # erreur DB à cette étape doit avoir exactement le même traitement
        # qu'une erreur Discord (trouvé en revue de code — l'appel était hors
        # du try dans la version initiale).
        return _guest_redirect(f"{type(exc).__name__}: {exc}")

    redirect = RedirectResponse("/?discord=connected")
    redirect.delete_cookie(key=STATE_COOKIE_NAME)
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=sign_discord_session(discord_id, config["session_secret_key"]),
        httponly=True,
        samesite="strict",
        secure=DISCORD_SESSION_COOKIE_SECURE,
        max_age=DISCORD_SESSION_COOKIE_MAX_AGE_SECONDS,
    )
    return redirect


@router.get("/me")
@limiter.limit("60/minute")
def discord_me(request: Request, db: Session = Depends(get_db)):
    """Lecture d'identité pour l'affichage global du bouton connecté (Story
    O.1.2, AC #7) : re-résout l'Account depuis le cookie à chaque appel (AD-22,
    jamais un account_id mis en cache), sans jamais en créer un — une lecture
    seule, contrairement au callback OAuth."""
    account = _current_account(request, db)
    if account is None:
        raise HTTPException(status_code=401, detail="Non connecté.")
    return {
        "pseudo": account.pseudo,
        "avatar": _avatar_url(account.discord_id, account.avatar),
    }


@router.post("/logout")
@limiter.limit("60/minute")
def discord_logout(request: Request):
    """Efface le cookie de session Discord (AC #3/#4, Story O.1.2). Stateless
    (AD-22) : aucune session serveur à invalider, un appel sans cookie reste un
    no-op réussi — même traitement que POST /admin/logout
    (backend/main_admin.py:59-64)."""
    response = JSONResponse({"message": "Déconnexion réussie."})
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=DISCORD_SESSION_COOKIE_SECURE,
    )
    return response
