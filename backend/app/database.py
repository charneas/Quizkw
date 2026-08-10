from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Utiliser SQLite pour le développement, PostgreSQL pour la production
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quizkw.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# BUG-101f : sans busy_timeout, le driver sqlite3 lève immédiatement
# "database is locked" (OperationalError -> 500 côté client) dès qu'une
# deuxième transaction tente d'écrire pendant qu'une première tient le
# verrou fichier — y compris pour des actions de jeu légitimes sans rapport
# avec les courses applicatives déjà corrigées par #3/#53. Avec un
# busy_timeout, SQLite réessaie en interne pendant ce délai avant d'échouer.
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_busy_timeout(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

Base = declarative_base()

# Dependency pour les routes FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()