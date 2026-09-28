"""Migrations de schéma de la DB blindtest, appliquées au démarrage.

Remplace l'ancien `Base.metadata.create_all` de `main.py`, qui n'altérait
jamais une table existante (d'où les `OperationalError: no such column` en
prod, corrigés trois fois à la main). Environnement Alembic :
`backend/alembic_blindtest/`, section `[blindtest]` d'`alembic.ini`.

Mise à niveau automatique (et non étape de déploiement manuelle comme la DB
quiz) : c'est justement l'étape manuelle oubliée qui cassait la prod. Sûr
car le blindtest tourne sur un seul worker gunicorn (pas de migrateur
concurrent).
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_INI_PATH = _BACKEND_DIR / "alembic.ini"
_SCRIPT_LOCATION = _BACKEND_DIR / "alembic_blindtest"

BASELINE_REVISION = "b7e1a2c9d4f0"

# Colonnes du schéma baseline, figées ici volontairement (et non dérivées des
# modèles, qui évolueront) : une DB legacy n'est tamponnée à la baseline que
# si elle les possède toutes.
BASELINE_COLUMNS = {
    "playlists": ["id", "source_url", "provider", "created_at", "game_id", "owner_pseudo"],
    "tracks": [
        "id", "playlist_id", "title", "artist", "isrc", "youtube_video_id",
        "source_url", "duration_seconds", "created_at",
    ],
    "match_cache": ["id", "isrc", "normalized_key", "youtube_video_id", "duration_seconds", "created_at"],
    "games": ["id", "code", "phase", "host_pseudo", "current_track_id", "created_at"],
}


def _alembic_config(connection) -> Config:
    # Chemins absolus : indépendant du répertoire de travail du process.
    cfg = Config(str(_INI_PATH), ini_section="blindtest")
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.attributes["connection"] = connection
    return cfg


def _missing_baseline_columns(connection, present_tables) -> list:
    inspector = inspect(connection)
    missing = []
    for table, columns in BASELINE_COLUMNS.items():
        existing = (
            {c["name"] for c in inspector.get_columns(table)} if table in present_tables else set()
        )
        missing.extend(f"{table}.{col}" for col in columns if col not in existing)
    return missing


def upgrade_blindtest_db(engine: Engine) -> None:
    """Met la DB blindtest au schéma `head`.

    - DB vide : la baseline crée les tables.
    - DB legacy (tables présentes, pas d'`alembic_version`) : vérifiée contre
      la baseline, tamponnée, puis mise à niveau. Aucune donnée touchée.
    - DB déjà gérée : `upgrade head` (no-op si déjà à jour).
    - DB legacy incomplète : `RuntimeError` listant les colonnes manquantes.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        # Le mode batch recrée des tables sous SQLite ; avec foreign_keys=ON
        # (posé par app/blindtest/database.py), le DROP d'une table référencée
        # échouerait. Le PRAGMA est sans effet dans une transaction, d'où le
        # commit immédiat, et il est rétabli avant de rendre la connexion au pool.
        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
        try:
            with connection.begin():
                tables = set(inspect(connection).get_table_names())
                cfg = _alembic_config(connection)
                if "alembic_version" not in tables:
                    legacy_tables = tables & set(BASELINE_COLUMNS)
                    if legacy_tables:
                        missing = _missing_baseline_columns(connection, legacy_tables)
                        if missing:
                            raise RuntimeError(
                                "La DB blindtest existante n'a pas d'historique Alembic et "
                                "diffère du schéma baseline : colonnes manquantes "
                                f"{', '.join(missing)}. Refus de la tamponner. Restaurer une "
                                "sauvegarde conforme ou recréer la DB (supprimer le fichier) "
                                "avant de relancer."
                            )
                        logger.info(
                            "DB blindtest legacy sans alembic_version : tamponnée à la baseline %s",
                            BASELINE_REVISION,
                        )
                        command.stamp(cfg, BASELINE_REVISION)
                command.upgrade(cfg, "head")
        finally:
            if is_sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                connection.commit()
