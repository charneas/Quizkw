"""Authentification admin (AD-17) : cookie de session signé, stateless — pas
de table de session, la signature est la seule source de vérité. Guard
partagé, appliqué à toutes les routes `/admin/*` (y compris celles
préexistantes de `main_admin.py`, non authentifiées avant cette story)."""
import os

import bcrypt
from fastapi import Cookie, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

try:
    SESSION_SECRET_KEY = os.environ["SESSION_SECRET_KEY"]
except KeyError:
    raise RuntimeError(
        "SESSION_SECRET_KEY est requise (AD-17, signature du cookie de session admin) "
        "— définir cette variable d'environnement avant de démarrer l'application."
    ) from None
COOKIE_NAME = "admin_session"
# AD-17 : cookie envoyé uniquement sur HTTPS. Défaut activé — confirmé par le
# Product Owner (2026-07-29) que le certificat HTTPS est réellement en place en
# prod, malgré la note de statut de DEPLOY.md §7 qui semble périmée sur ce
# point (à corriger séparément). Désactivable pour du développement local en
# HTTP simple via SESSION_COOKIE_SECURE=false.
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"

# Revue de sécurité M2 (2026-08-15) : le cookie n'expirait jamais (signature
# stateless sans horodatage) — volé une fois (XSS, poste partagé), il restait
# valide indéfiniment. URLSafeTimedSerializer embarque un timestamp signé,
# vérifié via max_age à la lecture (SignatureExpired). 7 jours par défaut,
# ajustable sans redéployer le code.
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600)))

_serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY, salt="admin-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def sign_session(admin_id: int) -> str:
    return _serializer.dumps({"admin_id": admin_id})


def require_admin_session(admin_session: str | None = Cookie(default=None)) -> int:
    """Dépendance FastAPI partagée : lève 401 si le cookie est absent, invalide
    ou expiré (SESSION_MAX_AGE_SECONDS, voir M2 ci-dessus), sinon retourne
    l'id de l'admin authentifié. Pas de recherche en base : le cookie signé
    reste la seule source de vérité, seule sa fraîcheur est désormais bornée."""
    if admin_session is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    try:
        payload = _serializer.loads(admin_session, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Authentification requise")
    return payload["admin_id"]
