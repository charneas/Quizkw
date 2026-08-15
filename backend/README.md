# Quizkw Backend

Backend FastAPI pour le jeu de quiz Quizkw : trois manches (quiz collectif,
tournoi individuel, grille mémoire), duels ping-pong, roue de bonus/malus,
interface admin (thèmes, questions, génération de contenu, propositions
publiques).

## Structure du projet

```
backend/
├── app/
│   ├── database.py          # Configuration de la base de données
│   ├── models.py             # Modèles SQLAlchemy
│   ├── schemas.py            # Schémas Pydantic
│   ├── round2_manager.py     # Logique métier Manche 2
│   └── memory_grid.py        # Logique métier Manche 3 (grille mémoire)
├── alembic/                  # Migrations de base de données
├── tests/                    # Tests pytest
├── main.py                   # Point d'entrée FastAPI, assemble les routers ci-dessous
├── main_games.py             # Endpoints sessions de jeu
├── main_teams.py             # Endpoints équipes / joueurs
├── main_manche1.py           # Endpoints Manche 1 (quiz collectif, jetons, roue)
├── main_round2.py            # Endpoints Manche 2 (tournoi individuel)
├── main_ping_pong.py         # Endpoints duels ping-pong
├── main_memory_grid_legacy.py # Endpoints Manche 3 (grille mémoire)
├── main_admin.py             # Auth + CRUD admin (thèmes, questions)
├── main_content_gen.py       # Génération semi-automatique de contenu (LLM)
├── main_propositions.py      # Propositions publiques de questions
├── main_extended.py          # Endpoints complémentaires / compatibilité
├── seed.py / seed_admin.py   # Scripts de peuplement de la base
├── requirements.txt          # Dépendances Python (prod)
├── requirements-dev.txt      # Dépendances de développement (tests, coverage)
└── README.md                 # Ce fichier
```

## Installation

1. **Créer un environnement virtuel :**
```bash
python -m venv venv
source venv/bin/activate  # Sur Linux/Mac
# ou
venv\Scripts\activate     # Sur Windows
```

2. **Installer les dépendances :**
```bash
pip install -r requirements.txt
```

3. **Configurer la base de données :**
```bash
# Créer un fichier .env (optionnel, SQLite par défaut)
echo "DATABASE_URL=sqlite:///./quizkw.db" > .env
```

4. **Appliquer les migrations :**
```bash
alembic upgrade head
```

## Utilisation

### Lancer l'API

```bash
# Développement avec auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

L'API sera disponible sur : http://localhost:8000

### Documentation automatique

- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

### Peupler la base de données

```bash
python seed.py         # Questions, thèmes, session de démo
python seed_admin.py   # Compte admin
```

## API — routers principaux

Chaque fichier `main_*.py` est un `APIRouter` FastAPI monté dans `main.py`.
Voir `/docs` pour la liste exhaustive et à jour des endpoints.

- **Sessions / équipes** (`main_games.py`, `main_teams.py`) : création de
  partie, jointure, équipes, joueurs.
- **Manche 1** (`main_manche1.py`) : quiz collectif par équipes, jetons
  (SWAP/pénalité/bonus), roue de bonus/malus tous les 5 tours.
- **Manche 2** (`main_round2.py`, `app/round2_manager.py`) : tournoi
  individuel 16→8→4.
- **Ping-pong** (`main_ping_pong.py`) : duels 1v1 déclenchés en cours de
  Manche 1.
- **Manche 3** (`main_memory_grid_legacy.py`, `app/memory_grid.py`) : grille
  mémoire 7×5 finale à 4 joueurs.
- **Admin** (`main_admin.py`) : authentification par cookie de session
  (`SESSION_SECRET_KEY`), CRUD thèmes/questions.
- **Génération de contenu** (`main_content_gen.py`) : génération
  semi-automatique de questions via LLM, signalement de contenu.
- **Propositions publiques** (`main_propositions.py`) : soumission externe de
  questions, workflow de validation admin.

## Règles implémentées

Les trois manches (quiz collectif, tournoi individuel, grille mémoire finale)
ainsi que les duels ping-pong et la roue de bonus/malus sont jouables de bout
en bout. Voir le tableau « État du jeu » dans [`../README.md`](../README.md)
pour le détail par manche, et `_bmad-output/` (non versionné) pour le
backlog détaillé.

## Configuration

### Variables d'environnement

- `DATABASE_URL` : URL de connexion à la base de données
  - Développement : `sqlite:///./quizkw.db`
  - Production : `postgresql://user:pass@host/dbname` (voir `../DEPLOY.md`)
- `SESSION_SECRET_KEY` : secret de signature du cookie de session admin
  (`/admin/*`). Obligatoire en production, générer une valeur aléatoire par
  déploiement (ex. `openssl rand -hex 32`).
- `SESSION_COOKIE_SECURE` : `true` par défaut (cookie envoyé uniquement en
  HTTPS) ; ne le passer à `false` qu'en dev local HTTP.

### Base de données

- SQLite par défaut (dev et prod actuelle).
- PostgreSQL supporté, pas encore utilisé en prod — voir `../DEPLOY.md`
  section 8 et `README.md` (racine) pour l'avertissement sur la
  désynchronisation `requirements.txt` / venv installé.
- Migrations gérées avec Alembic (`alembic/versions/`).

## Tests

```bash
python -m pip install -r requirements-dev.txt
pytest                              # suite complète (SQLite en mémoire)
pytest --cov=app --cov-report=term-missing
```

Un test de fumée dédié (`tests/test_migration_smoke_postgres.py`) valide les
migrations Alembic sous PostgreSQL (angle mort de la suite principale, qui
tourne exclusivement sur SQLite). Voir les commentaires en tête de ce fichier
de test pour la procédure — il exécute `alembic downgrade base` (destructeur)
et refuse de s'exécuter si `POSTGRES_TEST_URL` ne pointe pas vers une base de
test.

## Déploiement

Voir [`../DEPLOY.md`](../DEPLOY.md) pour le guide de déploiement production
complet (Gunicorn + Nginx + Let's Encrypt).
