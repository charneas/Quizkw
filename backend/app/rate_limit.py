"""Rate limiting partagé entre main.py et les routers (revue de sécurité, 2026-08-15).

Un seul Limiter par process, importé par chaque router qui veut une limite
plus stricte que le défaut global (voir main.py) sur un endpoint particulier
— typiquement les actions qui changent le score ou l'état de la partie
(roue, réponses, jetons), pour empêcher le spam même par un client déjà
authentifié (X-Team-Token/X-Player-Token).
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# RATE_LIMIT_ENABLED=false en tests (tests/conftest.py) : la suite envoie des
# centaines de requêtes par cas de test, toutes vues comme la même IP par
# TestClient — le vrai limiteur les rejetterait en 429 sans rapport avec ce
# que chaque test vérifie.
_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"], enabled=_enabled)
