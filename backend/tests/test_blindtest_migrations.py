"""Migrations Alembic de la DB blindtest (spec-blindtest-schema-migrations).

Chaque test travaille sur un fichier SQLite temporaire avec un engine monté
comme `app/blindtest/database.py` (busy_timeout + foreign_keys=ON), pour
couvrir chaque ligne de la matrice I/O de la spec.
"""
import shutil
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text

from app.blindtest import migrations
from app.blindtest.database import Base
from app.blindtest import models  # noqa: F401 — complète Base.metadata
from app.blindtest.migrations import BASELINE_REVISION, upgrade_blindtest_db

TABLES = ["playlists", "tracks", "match_cache", "games"]


def _make_engine(path: Path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


@pytest.fixture
def engine(tmp_path):
    eng = _make_engine(tmp_path / "blindtest.db")
    yield eng
    eng.dispose()


def _head_revision(script_location=None):
    cfg = migrations._alembic_config(None)
    if script_location is not None:
        cfg.set_main_option("script_location", str(script_location))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _version(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _schema(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT type, name, sql FROM sqlite_master WHERE tbl_name != 'alembic_version' ORDER BY name")
        ).all()
    return [tuple(r) for r in rows]


def _counts(engine):
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in TABLES}


def _seed(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO games (id, code, phase, host_pseudo) VALUES (1, 'ABCD', 'lobby', 'bob')"))
        conn.execute(text(
            "INSERT INTO playlists (id, source_url, provider, game_id, owner_pseudo) "
            "VALUES (1, 'https://x', 'youtube', 1, 'bob')"
        ))
        conn.execute(text(
            "INSERT INTO tracks (id, playlist_id, title, artist, youtube_video_id, duration_seconds) "
            "VALUES (1, 1, 'T', 'A', 'vid', 200)"
        ))
        conn.execute(text("UPDATE games SET current_track_id = 1 WHERE id = 1"))
        conn.execute(text(
            "INSERT INTO match_cache (id, isrc, youtube_video_id) VALUES (1, 'ISRC1', 'vid')"
        ))


def test_fresh_install_creates_tables_and_version(engine):
    upgrade_blindtest_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert set(TABLES) <= tables
    assert _version(engine) == _head_revision()


def test_head_schema_matches_models(engine):
    upgrade_blindtest_db(engine)

    # Le cycle de FK playlists/games/tracks provoque un SAWarning de tri
    # attendu (tri des tables pour l'affichage), sans incidence sur le résultat.
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_baseline_matches_create_all_schema(tmp_path, engine):
    """La baseline reproduit exactement le schéma produit jusqu'ici par
    `create_all` (tables, colonnes, FK, contraintes uniques, index)."""
    upgrade_blindtest_db(engine)

    legacy = _make_engine(tmp_path / "legacy.db")
    Base.metadata.create_all(bind=legacy)
    try:
        assert _schema(engine) == _schema(legacy)
    finally:
        legacy.dispose()


def test_legacy_db_is_stamped_without_touching_data(engine):
    Base.metadata.create_all(bind=engine)
    _seed(engine)
    schema_before = _schema(engine)
    counts_before = _counts(engine)

    upgrade_blindtest_db(engine)

    assert _version(engine) == _head_revision()
    assert _counts(engine) == counts_before
    assert _schema(engine) == schema_before


def test_already_managed_db_second_run_is_noop(engine):
    upgrade_blindtest_db(engine)
    _seed(engine)
    schema_before = _schema(engine)
    counts_before = _counts(engine)
    version_before = _version(engine)

    upgrade_blindtest_db(engine)

    assert _version(engine) == version_before
    assert _schema(engine) == schema_before
    assert _counts(engine) == counts_before


def test_stale_legacy_db_fails_loudly_and_is_not_stamped(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_games_code"))
        conn.execute(text("DROP INDEX ix_games_id"))
        conn.execute(text("DROP TABLE games"))
        conn.execute(text(
            "CREATE TABLE games (id INTEGER NOT NULL PRIMARY KEY, code VARCHAR NOT NULL, "
            "phase VARCHAR NOT NULL, current_track_id INTEGER, created_at DATETIME)"
        ))

    with pytest.raises(RuntimeError) as excinfo:
        upgrade_blindtest_db(engine)

    message = str(excinfo.value)
    assert "games.host_pseudo" in message
    assert "Restaurer" in message and "recréer" in message
    assert "alembic_version" not in inspect(engine).get_table_names()


def test_partial_legacy_db_names_missing_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE match_cache (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError) as excinfo:
        upgrade_blindtest_db(engine)

    assert "games.host_pseudo" in str(excinfo.value)
    assert "match_cache.youtube_video_id" in str(excinfo.value)


def test_foreign_keys_pragma_restored_after_upgrade(engine):
    upgrade_blindtest_db(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_future_revision_is_applied_on_restart(tmp_path, engine, monkeypatch):
    """Critère d'acceptation : une révision ajoutée plus tard est appliquée
    au redémarrage sur une DB existante, sans étape manuelle — y compris une
    opération batch qui recrée une table référencée par des FK."""
    Base.metadata.create_all(bind=engine)  # DB legacy, comme la prod
    _seed(engine)
    upgrade_blindtest_db(engine)

    script_dir = tmp_path / "alembic_blindtest"
    shutil.copytree(migrations._SCRIPT_LOCATION, script_dir, ignore=shutil.ignore_patterns("__pycache__"))
    (script_dir / "versions" / "c0ffee000001_add_playlists_title.py").write_text(
        f'''
from alembic import op
import sqlalchemy as sa

revision = "c0ffee000001"
down_revision = "{BASELINE_REVISION}"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("playlists", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("playlists") as batch_op:
        batch_op.drop_column("title")
''',
        encoding="utf-8",
    )
    monkeypatch.setattr(migrations, "_SCRIPT_LOCATION", script_dir)
    counts_before = _counts(engine)

    upgrade_blindtest_db(engine)

    assert _version(engine) == "c0ffee000001"
    columns = {c["name"] for c in inspect(engine).get_columns("playlists")}
    assert "title" in columns
    assert _counts(engine) == counts_before
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
