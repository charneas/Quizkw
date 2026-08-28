import os

from fastapi import Request
from itsdangerous import BadPayload, BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models

# Story O.1.1/AD-22 : nom de cookie partagé par main_auth_discord.py (qui
# l'importe depuis ici, plutôt que l'inverse, pour éviter un import circulaire
# — ce module ne dépend jamais des routeurs qui l'appellent).
DISCORD_COOKIE_NAME = "discord_session"


def resolve_or_create_account(db: Session, discord_id: str, pseudo: str, avatar: str | None) -> models.Account:
    """Résolution-ou-création d'un Account par discord_id (AD-19). Pseudo/avatar
    sont écrasés par les valeurs reçues à chaque appel, réutilisation comprise.

    La contrainte unique DB sur discord_id est la sentinelle d'idempotence face
    à deux logins concurrents pour le même compte Discord — jamais un
    check-then-insert nu : sur IntegrityError après un insert perdant la course,
    on relit la ligne posée par l'autre transaction plutôt que de propager
    l'erreur."""
    account = db.query(models.Account).filter(models.Account.discord_id == discord_id).first()
    if account is not None:
        account.pseudo = pseudo
        account.avatar = avatar
        db.commit()
        db.refresh(account)
        return account

    account = models.Account(discord_id=discord_id, pseudo=pseudo, avatar=avatar)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        account = db.query(models.Account).filter(models.Account.discord_id == discord_id).first()
        if account is None:
            # L'IntegrityError ne venait pas de la course discord_id documentée
            # ci-dessus (autre contrainte, ou ligne concurrente elle-même
            # annulée depuis) — propager plutôt que de planter sur un accès
            # None (trouvé en revue de code).
            raise
        account.pseudo = pseudo
        account.avatar = avatar
        db.commit()
        db.refresh(account)
        return account

    db.refresh(account)
    return account


def resolve_account_from_discord_id(db: Session, discord_id: str) -> models.Account | None:
    """Lecture seule par discord_id — jamais resolve_or_create_account : un
    appelant qui n'a que le discord_id du cookie (pas de pseudo/avatar frais,
    ceux-ci ne viennent que du callback OAuth) écraserait silencieusement les
    données réelles du compte s'il appelait l'upsert avec des valeurs vides
    (piège identique à celui déjà rencontré et évité pour GET /auth/discord/me,
    Story O.1.2). Un cookie signé valide implique structurellement qu'un
    Account existe déjà pour ce discord_id (AD-22 : le cookie n'est posé
    qu'après un resolve_or_create_account réussi au login) — sauf suppression
    RGPD entre-temps (AD-21), auquel cas ce lookup renvoie None sans jamais
    recréer de compte à la volée."""
    return db.query(models.Account).filter(models.Account.discord_id == discord_id).first()


def resolve_account_from_request(request: Request, db: Session) -> models.Account | None:
    """Décode le cookie discord_session et résout l'Account correspondant, en
    une seule lecture — fonction de bas niveau partagée par
    `resolve_account_id_from_request` (main_teams.py) et `_current_account`
    (main_auth_discord.py, GET /auth/discord/me), qui appelaient auparavant
    chacun une variante de ce décodage, l'une d'elles refaisant une deuxième
    requête pour relire la ligne déjà chargée ici (trouvé en revue de code).
    Ne lève jamais : cookie absent, signature invalide, secret non configuré
    ou compte introuvable sont tous traités comme "non connecté"."""
    cookie_value = request.cookies.get(DISCORD_COOKIE_NAME)
    if not cookie_value:
        return None
    session_secret_key = os.getenv("DISCORD_SESSION_SECRET_KEY")
    if not session_secret_key:
        return None
    try:
        payload = URLSafeSerializer(session_secret_key, salt="discord-session").loads(cookie_value)
    except (BadSignature, BadPayload):
        # BadPayload (revue de code) : signature valide mais désérialisation
        # du payload impossible — même traitement "non connecté" que
        # BadSignature, jamais une 500 sur join_team/create_player.
        return None
    discord_id = payload.get("discord_id")
    if not discord_id:
        return None
    return resolve_account_from_discord_id(db, discord_id)


def resolve_account_id_from_request(request: Request, db: Session) -> int | None:
    """Résout l'account_id à écrire sur un nouveau Player (AD-19). Ne lève
    jamais — contrairement à _require_discord_config() des routes
    /auth/discord/*, un endpoint de jeu (join_team/create_player) ne doit
    jamais échouer parce que Discord n'est pas configuré sur ce déploiement
    (FR1, additif uniquement)."""
    account = resolve_account_from_request(request, db)
    return account.id if account is not None else None
