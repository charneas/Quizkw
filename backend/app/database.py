from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Utiliser SQLite pour le développement, PostgreSQL pour la production
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quizkw.db")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency pour les routes FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()