# Quizkw

Jeu de quiz multijoueur en équipe, jouable en LAN/soirée : trois manches
successives (quiz collectif, tournoi individuel 16→8→4, grille mémoire
finale à 4 joueurs) avec un backend FastAPI et un frontend React. Un module
**blind test** (deviner, à l'écoute d'un morceau, dans quelle playlist —
donc de quel joueur — il se trouve) tourne en parallèle sur la même
application.

Déployé en production sur **quizclimb.fr**.

## Stack technique

- **Backend** : FastAPI, SQLAlchemy, Alembic, SQLite (dev/prod actuelle),
  PostgreSQL prévu. Voir [`backend/README.md`](backend/README.md).
- **Frontend** : React 18, TypeScript, Vite, TailwindCSS, React Router.
- **Tests** : pytest (backend), Playwright (E2E frontend).

### Module blind test

Router séparé (`backend/main_blindtest.py`), monté sur la même app FastAPI
mais avec sa **propre base de données isolée** (`app/blindtest/`, AD-7) —
aucune jointure avec les tables du quiz principal. Import de playlists
(Deezer/YouTube), matching automatique vers YouTube, lobby et
rounds en temps réel via WebSocket (`frontend/src/lib/blindtestSocket.ts`).
Front : `frontend/src/pages/BlindTestLobby.tsx`, route `/blindtest/:code`.

⚠️ Limité à **1 seul worker gunicorn** en prod — état de partie en mémoire
par process, pas encore de coordination multi-worker (Redis prévu).

⚠️ Le provider Spotify a été retiré (2026-09-14) : l'API Spotify bloque
désormais l'accès Client Credentials (app-only) aux morceaux des playlists
d'autres utilisateurs, même publiques (Extended Quota Mode requis) — ça ne
dépendait pas de la playlist ciblée, ni d'un abonnement Premium côté
utilisateur. Deezer (sans authentification) et YouTube sont les deux
sources d'import disponibles.

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
| Blind test | Jouable, intégré à la home | Rejoindre/créer depuis la home, titre/artiste et score visibles en permanence, layout/palette dédiés, résilience host/déconnexion — voir `_bmad-output/specs/spec-blindtest-integration-ui/` |

Le suivi détaillé du backlog (epics, stories, statut) est géré via BMad Method
dans `_bmad-output/` (non versionné — généré localement).

## Déploiement

Voir [`DEPLOY.md`](DEPLOY.md).

## Structure du dépôt

```
Quizkw/
├── backend/
│   ├── main.py             # App FastAPI principale, monte tous les routers (dont blindtest)
│   ├── main_blindtest.py   # Router blind test (lobby, rounds, WebSocket)
│   └── app/blindtest/      # DB isolée + modèles du module blind test (AD-7)
├── frontend/
│   └── src/pages/BlindTestLobby.tsx  # Écran blind test (/blindtest/:code)
├── docs/archive/    # Notes de session et TODO historiques (périmés, conservés pour référence)
├── DEPLOY.md        # Guide de déploiement production
└── README.md        # Ce fichier
```
