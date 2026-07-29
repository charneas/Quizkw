#!/usr/bin/env python3
"""Seed du compte admin unique (Epic F-ext-2, story F-ext-2.1, AD-17).

Distinct de `seed.py` (données de jeu de test) : ce script ne crée qu'un
compte, lit le mot de passe depuis la variable d'environnement
`ADMIN_SEED_PASSWORD` (jamais en clair dans le dépôt), et est idempotent
(ne recrée pas le compte si l'email existe déjà).
"""
import os
import sys

# app.database charge le .env (load_dotenv) — doit être importé avant app.auth,
# qui lit SESSION_SECRET_KEY depuis l'environnement dès son import (AD-17).
from app.database import Base, SessionLocal, engine
from app.auth import hash_password
from app.models import Admin

ADMIN_EMAIL = "charneas@gmail.com"


def seed_admin() -> None:
    password = os.getenv("ADMIN_SEED_PASSWORD")
    if not password:
        print("ERREUR : la variable d'environnement ADMIN_SEED_PASSWORD est requise.", file=sys.stderr)
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(Admin).filter(Admin.email == ADMIN_EMAIL).first()
        if existing:
            print(f"Le compte admin '{ADMIN_EMAIL}' existe déjà, rien à faire.")
            return
        admin = Admin(email=ADMIN_EMAIL, hashed_password=hash_password(password))
        db.add(admin)
        db.commit()
        print(f"Compte admin '{ADMIN_EMAIL}' créé.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
