# Quizkw

Jeu de quiz multijoueur en équipe, jouable en LAN/soirée : trois manches
successives (quiz collectif, tournoi individuel 16→8→4, grille mémoire
finale à 4 joueurs) avec un backend FastAPI et un frontend React.

## Stack technique

- **Backend** : FastAPI, SQLAlchemy, Alembic, SQLite (dev/prod actuelle),
  PostgreSQL prévu. Voir [`backend/README.md`](backend/README.md).
- **Frontend** : React 18, TypeScript, Vite, TailwindCSS, React Router.
- **Tests** : pytest (backend), Playwright (E2E frontend).

## Installation

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

L'API est alors disponible sur `http://localhost:8000`, avec documentation
interactive sur `/docs` (Swagger) et `/redoc`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Le frontend est servi sur `http://localhost:3000` (Vite) et proxifie les
appels `/api/*` vers le backend sur `:8000` (voir `frontend/vite.config.ts`).
**Le backend doit tourner en parallèle** pour que l'application fonctionne.

## Lancer les tests

```bash
# Backend
cd backend
venv\Scripts\pytest

# Frontend (E2E, nécessite backend + frontend démarrés)
cd frontend
npx playwright test
```

## État du jeu

| Manche | Statut | Notes |
|---|---|---|
| 1 — Quiz collectif par équipes | Jouable | Jetons (swap/pénalité/bonus), roue de bonus/malus tous les 5 tours, duels ping-pong |
| 2 — Tournoi individuel 16→8→4 | Jouable, retours playtest corrigés | Tour par rôle avec spectateurs, qualification Manche 1→2 fiabilisée (H-007), tests E2E (`frontend/tests/round2.spec.ts`) |
| 3 — Grille mémoire (finale, 4 joueurs) | Jouable, testée en E2E réel | Grille 7×5, individuelle depuis la réécriture AD-0 (2026-07-25) |

Le suivi détaillé du backlog (epics, stories, statut) est géré via BMad Method
dans `_bmad-output/` (non versionné — généré localement).

## Déploiement

Voir [`DEPLOY.md`](DEPLOY.md).

## Structure du dépôt

```
Quizkw/
├── backend/         # API FastAPI (voir backend/README.md)
├── frontend/        # Application React
├── docs/archive/    # Notes de session et TODO historiques (périmés, conservés pour référence)
├── DEPLOY.md        # Guide de déploiement production
└── README.md        # Ce fichier
```
