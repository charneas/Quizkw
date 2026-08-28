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
        # Story O.2.1 : SQLite n'applique pas les contraintes FK par défaut —
        # sans ce pragma, `ondelete="SET NULL"` (Player.account_id ->
        # accounts.id, AD-21) n'est qu'une déclaration de schéma inerte.
        # Activé une première fois en O.2.1, retiré en revue de O.2.2 (révélait
        # un bug préexistant, memory_grid.py::select_player_themes acceptant
        # des theme_ids sans les valider), remis après correction de ce bug
        # racine (validation ajoutée dans select_player_themes) — voir Change
        # Log de o-2-1-attribution-des-reponses-au-compte.md pour l'historique.
        cursor.execute("PRAGMA foreign_keys = ON")
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