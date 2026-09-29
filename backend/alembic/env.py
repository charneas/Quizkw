from logging.config import fileConfig
import sys
import os

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

load_dotenv()

# Add the app directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Base from your models
from app.database import Base, DATABASE_URL
# Import EVERY module that defines ORM models, so Base.metadata is complete.
# Missing one makes autogenerate silently propose dropping its tables.
from app import models  # noqa: F401 — core entities
from app import memory_grid  # noqa: F401 — Manche 3 grid models
from app import memory_grid_enhanced  # noqa: F401 — grid colour/result models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Connexion fournie par app/migrations.py (upgrade_main_db, au démarrage de
# l'app) ; None en CLI.
injected_connection = config.attributes.get("connection")

# Interpret the config file for Python logging.
# En CLI seulement : au démarrage de l'app, fileConfig reconfigurerait (et
# désactiverait) les loggers déjà en place du process FastAPI.
if injected_connection is None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate support
target_metadata = Base.metadata

# Surcharger sqlalchemy.url avec DATABASE_URL, comme app/database.py (H-008).
# alembic.ini garde une valeur statique en fallback inerte quand cette
# surcharge s'applique (via les entrypoints standards run_migrations_*) :
# sans elle, une migration peut s'exécuter contre la mauvaise base — c'est
# exactement ce qui est arrivé le 2026-07-26
# (voir _bmad-output/epic-f-retro-2026-07-26.md).
# Réutilise app.database.DATABASE_URL (même valeur, même fallback) plutôt
# que de re-dériver la logique ici. `%%` échappe les `%` littéraux
# (ex: mot de passe encodé en URL) car ConfigParser interprète `%` sans
# échappement automatique côté Alembic.
config.set_main_option(
    "sqlalchemy.url", (DATABASE_URL or "sqlite:///./quizkw.db").replace("%", "%%")
)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    if injected_connection is not None:
        context.configure(connection=injected_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
