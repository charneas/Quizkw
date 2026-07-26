"""
Test de fumée de migration Alembic contre PostgreSQL (H-009).

La suite de tests principale (conftest.py) tourne exclusivement sur SQLite
en mémoire. Un bug de migration réel (type enum `themecategory` redéclaré)
ne s'est manifesté que sous PostgreSQL — voir epic-f-retro-2026-07-26.md.
Ce test comble cet angle mort sans dépendre d'une infrastructure PostgreSQL
locale : il se marque `skipped` si aucune base n'est disponible via
POSTGRES_TEST_URL, plutôt que d'échouer ou de fausser un "passed".

ATTENTION : ce test exécute `alembic downgrade base` (destructeur, vide le
schéma) avant `upgrade head`. Ne jamais pointer POSTGRES_TEST_URL vers une
base contenant de vraies données — utiliser une base jetable dédiée.
"""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

# BACKEND_DIR : ce fichier vit dans backend/tests/, donc deux dirname()
# remontent à backend/. Si ce test est déplacé (ex: backend/tests/migrations/),
# ce calcul doit être ajusté en conséquence.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUBPROCESS_TIMEOUT_SECONDS = 300


def _postgres_test_url():
    return os.getenv("POSTGRES_TEST_URL")


def _normalize_url(url):
    """Alembic/SQLAlchemy récent n'accepte plus le schéma `postgres://`."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _looks_disposable(url):
    """Garde-fou : exige "test" dans l'hôte ou le nom de base avant tout
    downgrade destructeur — décision actée avec l'utilisateur (2026-07-26)
    après revue de code, pour empêcher un POSTGRES_TEST_URL mal renseigné de
    vider une vraie base."""
    try:
        parsed = make_url(url)
    except Exception:
        return False
    host = (parsed.host or "").lower()
    database = (parsed.database or "").lower()
    return "test" in host or "test" in database


def _connection_error(url):
    """Retourne un message d'erreur si la connexion échoue, sinon None.

    Capture large et volontaire (pas seulement OperationalError) : une URL
    malformée ou un driver manquant peuvent lever ArgumentError,
    NoSuchModuleError, ModuleNotFoundError, etc. — tous doivent aboutir à un
    skip propre (AC #2), pas à une erreur de fixture non catchée.
    """
    try:
        engine = create_engine(url)
        try:
            with engine.connect():
                pass
        finally:
            engine.dispose()
        return None
    except Exception as exc:
        return str(exc)


@pytest.fixture(scope="module")
def postgres_test_url():
    url = _postgres_test_url()
    if not url:
        pytest.skip(
            "POSTGRES_TEST_URL non positionnée — test de fumée PostgreSQL sauté "
            "(voir backend/README.md#Test de fumée PostgreSQL pour le configurer)"
        )
    url = _normalize_url(url)
    if not _looks_disposable(url):
        pytest.skip(
            f"POSTGRES_TEST_URL ne contient pas 'test' dans l'hôte ou le nom de "
            f"base ({url!r}) — refus par sécurité d'exécuter un downgrade "
            f"destructeur contre une base qui pourrait être réelle. Utiliser une "
            f"base jetable explicitement nommée (ex: 'quizkw_test')."
        )
    error = _connection_error(url)
    if error:
        pytest.skip(f"Connexion PostgreSQL impossible ({url}) : {error}")
    return url


def test_alembic_upgrade_head_against_postgres(postgres_test_url):
    """`alembic upgrade head` doit réussir contre une base PostgreSQL.

    Connu : peut échouer avec NoSuchTableError faute de révision baseline
    couvrant le schéma préexistant — violation déjà documentée par AD-14
    (ARCHITECTURE-SPINE.md), pas un défaut introduit par ce test. Si cet
    échec se produit, il confirme le risque qu'AD-14 documente déjà.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = postgres_test_url

    # Repartir de zéro si un run précédent a laissé une base déjà versionnée,
    # pour retester la migration complète depuis le vide à chaque exécution.
    # Échec traité comme fatal (pas silencieux) : un downgrade cassé laisse
    # la base dans un état inconnu, ce qui invaliderait le upgrade suivant.
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    assert downgrade.returncode == 0, (
        f"`alembic downgrade base` (nettoyage préalable) a échoué :\n"
        f"--- stdout ---\n{downgrade.stdout}\n--- stderr ---\n{downgrade.stderr}"
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        f"`alembic upgrade head` a échoué contre PostgreSQL "
        f"(voir AD-14 pour un risque connu lié à l'absence de baseline) :\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
