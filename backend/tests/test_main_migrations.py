"""spec-main-db-migrations-at-startup : `upgrade_main_db` remplace le
`create_all` de démarrage de la DB principale. DB vide -> create_all + stamp
head ; DB gérée -> upgrade head ; DB avec tables sans alembic_version ->
refus explicite, sans rien toucher."""
import glob
import os
import tempfile

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.migrations import _INI_PATH, _SCRIPT_LOCATION, upgrade_main_db


def _engine():
    path = os.path.join(tempfile.mkdtemp(prefix="quizkw-mig-"), "quizkw.db").replace("\\", "/")
    return create_engine(f"sqlite:///{path}")


def _head() -> str:
    cfg = Config(str(_INI_PATH))
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _version(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_empty_db_is_created_from_models_and_stamped_head():
    engine = _engine()
    upgrade_main_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert _version(engine) == _head()


def test_managed_db_at_head_is_left_as_is_on_restart():
    engine = _engine()
    upgrade_main_db(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO themes (name, category, difficulty_level) VALUES ('Kept', 'SERIOUS', 1)"))

    upgrade_main_db(engine)

    assert _version(engine) == _head()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM themes WHERE name = 'Kept'")).scalar() == 1


def test_legacy_db_without_alembic_history_is_refused_untouched():
    engine = _engine()
    Base.metadata.create_all(bind=engine)  # ancien comportement de démarrage

    with pytest.raises(RuntimeError, match="alembic_version"):
        upgrade_main_db(engine)

    assert "alembic_version" not in set(inspect(engine).get_table_names())


def test_failed_upgrade_is_explained_and_backed_up_first():
    """Scénario réel de la DB de dev (2026-09-30) : historique Alembic à une
    révision ancienne, mais tables plus récentes déjà créées par l'ancien
    create_all -> "table accounts already exists". Message explicite qui
    cite la copie de sauvegarde faite juste avant la migration."""
    from alembic import command
    from app.migrations import _alembic_config

    engine = _engine()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        command.stamp(_alembic_config(conn), "d9e0f1a2b3c4")

    with pytest.raises(RuntimeError, match="supprimer le fichier") as exc_info:
        upgrade_main_db(engine)

    # DDL non transactionnel sous SQLite : pas de promesse de rollback, mais
    # une copie de sauvegarde d'avant migration, citée dans le message.
    db_path = engine.url.database
    backups = glob.glob(f"{db_path}.bak.pre-migration-d9e0f1a2b3c4-*")
    assert len(backups) == 1
    assert os.path.basename(backups[0]) in str(exc_info.value)
    backup_engine = create_engine(f"sqlite:///{backups[0]}")
    assert _version(backup_engine) == "d9e0f1a2b3c4"


def test_db_already_at_head_is_not_backed_up():
    engine = _engine()
    upgrade_main_db(engine)
    upgrade_main_db(engine)
    assert glob.glob(f"{engine.url.database}.bak.*") == []
