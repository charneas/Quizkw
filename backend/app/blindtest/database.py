"""Moteur/session/Base dédiés au module blindtest (AD-7, Epic 1).

Mirroir de `app/database.py` mais avec un fichier SQLite/engine DISTINCT —
`BLINDTEST_DATABASE_URL` plutôt que `DATABASE_URL` — pour éviter toute
contention d'écriture avec la DB Quizkw principale (cf. BUG-101f) et parce
que ce module n'a aucun besoin de JOIN cross-DB avec le reste de l'app.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("BLINDTEST_DATABASE_URL", "sqlite:///./blindtest.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# BUG-101f : même rationale que app/database.py — sans busy_timeout, une
# écriture concurrente lève immédiatement "database is locked" plutôt que de
# réessayer pendant le délai imparti.
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_busy_timeout(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
