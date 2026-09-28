"""Environnement Alembic dédié à la DB blindtest (AD-7 : fichier SQLite distinct).

Utilisé de deux façons :
- au démarrage du backend, via `app.blindtest.migrations.upgrade_blindtest_db`,
  qui fournit sa propre connexion dans `config.attributes["connection"]` ;
- en CLI, via `alembic -n blindtest ...` (section `[blindtest]` d'alembic.ini),
  auquel cas l'URL vient de `app.blindtest.database.DATABASE_URL`
  (`BLINDTEST_DATABASE_URL`) — jamais de `DATABASE_URL` (DB quiz).

`render_as_batch=True` : SQLite ne sait pas faire la plupart des `ALTER`,
le mode batch recrée la table quand c'est nécessaire.
"""
from logging.config import fileConfig
import os
import sys

from sqlalchemy import create_engine, pool

from alembic import context

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blindtest.database import Base, DATABASE_URL  # noqa: E402
# Importer les modèles pour que Base.metadata soit complet (sinon
# l'autogenerate proposerait de supprimer les tables).
from app.blindtest import models  # noqa: E402,F401

config = context.config

connection = config.attributes.get("connection")

# En CLI seulement : au démarrage de l'app, fileConfig reconfigurerait (et
# désactiverait) les loggers déjà en place du process FastAPI.
if connection is None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(conn) -> None:
    context.configure(
        connection=conn,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if connection is not None:
        _run_with_connection(connection)
        return

    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as conn:
        _run_with_connection(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
