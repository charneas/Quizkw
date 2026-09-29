"""Schéma de la DB principale (quiz), appliqué au démarrage.

Remplace l'ancien `Base.metadata.create_all` de `main.py`, qui créait des
tables hors Alembic (un `alembic upgrade head` échouait ensuite sur une DB de
dev : "table accounts already exists") et pouvait masquer en prod une
migration oubliée. Même principe que la DB blindtest
(`app/blindtest/migrations.py`) : la migration n'est plus une étape manuelle
de déploiement. Sûr car l'app tourne sur un seul worker gunicorn (pas de
migrateur concurrent).

La chaîne Alembic ne sait pas construire une DB vide (les premières
migrations supposent des tables historiquement créées par `create_all` :
arrêt sur `grid_cells` en 151a691eefd6), d'où l'amorçage "create_all puis
stamp head" pour une DB vide — le motif standard d'Alembic.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database import Base

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_INI_PATH = _BACKEND_DIR / "alembic.ini"
_SCRIPT_LOCATION = _BACKEND_DIR / "alembic"


def _alembic_config(connection) -> Config:
    # Chemins absolus : indépendant du répertoire de travail du process.
    cfg = Config(str(_INI_PATH))
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.attributes["connection"] = connection
    return cfg


def _backup_sqlite(connection, engine: Engine, current_rev: str) -> str | None:
    """Copie la DB SQLite (API de sauvegarde SQLite, cohérente) avant une
    migration effective. Sous SQLite le DDL n'est pas transactionnel pour
    Alembic (pysqlite n'émet pas de BEGIN avant un CREATE/ALTER) : un échec
    au milieu d'une chaîne de migrations laisserait un schéma partiel, d'où
    cette copie de retour arrière. None pour une DB en mémoire."""
    db_path = engine.url.database
    if not db_path or db_path == ":memory:":
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = f"{db_path}.bak.pre-migration-{current_rev}-{stamp}"
    dest = sqlite3.connect(backup_path)
    try:
        connection.connection.driver_connection.backup(dest)
    finally:
        dest.close()
    logger.info("DB principale sauvegardée avant migration : %s", backup_path)
    return backup_path


def upgrade_main_db(engine: Engine) -> None:
    """Met la DB principale au schéma `head`.

    - DB vide : tables créées depuis les modèles, puis tamponnée à `head`.
    - DB gérée (table `alembic_version`) : rien si déjà à `head` ; sinon
      copie de sauvegarde (SQLite) puis `upgrade head`.
    - DB avec tables mais sans `alembic_version` (DB de dev créée par
      l'ancien `create_all`) : `RuntimeError` explicite, rien n'est touché.
    """
    # Enregistre tous les modèles dans Base.metadata avant un create_all
    # (mêmes imports que alembic/env.py).
    from app import models, memory_grid, memory_grid_enhanced  # noqa: F401

    is_sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        # Le mode batch recrée des tables sous SQLite ; avec foreign_keys=ON
        # (posé par app/database.py), le DROP d'une table référencée
        # échouerait. Le PRAGMA est sans effet dans une transaction, d'où le
        # commit immédiat, et il est rétabli avant de rendre la connexion.
        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
        try:
            with connection.begin():
                tables = set(inspect(connection).get_table_names())
                cfg = _alembic_config(connection)
                if not tables:
                    logger.info("DB principale vide : création depuis les modèles puis stamp head")
                    Base.metadata.create_all(bind=connection)
                    command.stamp(cfg, "head")
                elif "alembic_version" not in tables:
                    raise RuntimeError(
                        "La DB principale contient des tables mais aucun historique Alembic "
                        "(table alembic_version absente) : elle a été créée hors migrations "
                        "(ancien create_all). Refus de démarrer dessus. En dev : supprimer le "
                        "fichier de la DB pour qu'il soit recréé. Sinon : vérifier que son "
                        "schéma est à jour puis `alembic stamp head`."
                    )
                else:
                    current = MigrationContext.configure(connection).get_current_revision()
                    head = ScriptDirectory.from_config(cfg).get_current_head()
                    if current == head:
                        return
                    backup = _backup_sqlite(connection, engine, current or "base") if is_sqlite else None
                    try:
                        command.upgrade(cfg, "head")
                    except Exception as exc:
                        first_line = (str(exc).splitlines() or [""])[0]
                        hint = (
                            " Cas typique en dev : DB créée en partie hors Alembic par "
                            "l'ancien create_all — supprimer le fichier de la DB pour "
                            "qu'il soit recréé."
                            if "already exists" in first_line else ""
                        )
                        where = f" Sauvegarde d'avant migration : {backup}." if backup else ""
                        raise RuntimeError(
                            f"Échec de la migration de la DB principale de {current} vers "
                            f"{head} ({type(exc).__name__}: {first_line}). Le schéma peut "
                            f"être partiellement migré (DDL non transactionnel sous SQLite)."
                            f"{where}{hint}"
                        ) from exc
        finally:
            if is_sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                connection.commit()
