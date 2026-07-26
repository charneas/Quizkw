# Quizkw Backend

Backend FastAPI pour le jeu de quiz Quizkw avec règles complexes.

## Structure du projet

```
backend/
├── app/
│   ├── database.py          # Configuration de la base de données
│   ├── models.py            # Modèles SQLAlchemy
│   ├── schemas.py           # Schémas Pydantic
│   └── api/                 # Endpoints API (à venir)
├── alembic/                 # Migrations de base de données (à venir)
├── requirements.txt         # Dépendances Python
├── seed.py                 # Script de peuplement de la base de données
├── main.py                 # Application FastAPI principale
└── README.md               # Ce fichier
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

## Utilisation

### Lancer l'API

```bash
# Développement avec auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Ou exécuter directement
python main.py
```

L'API sera disponible sur : http://localhost:8000

### Documentation automatique

- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

### Peupler la base de données

```bash
python seed.py
```

Ce script créera :
- 7 questions de test avec différentes difficultés
- Une session de jeu avec 3 équipes de 2 joueurs
- 3 jetons par équipe (SWAP, pénalité, bonus)

## API Endpoints

### Gestion des jeux
- `POST /games/` - Créer une nouvelle session
- `GET /games/{code}` - Récupérer une session
- `POST /games/{code}/teams/` - Créer une équipe
- `POST /games/{code}/start` - Démarrer le jeu
- `POST /games/{code}/advance-to-phase3` - Passer à la phase 3 (manche finale)

### Questions et réponses
- `GET /questions/random` - Obtenir une question aléatoire
- `POST /answers/` - Soumettre une réponse

### Fonctionnalités avancées
- `POST /tokens/use` - Utiliser un jeton
- `POST /wheel/spin` - Tourner la roue de bonus/malus

### Phase 3 - Grille Mémoire (Manche Finale)
- `POST /games/{code}/memory-grid/create` - Créer une grille mémoire 7x5
- `POST /games/{code}/memory-grid/start` - Démarrer un tour de grille mémoire
- `GET /memory-grid/{memory_grid_id}/state` - Obtenir l'état de la grille
- `POST /memory-grid/reveal-cell` - Révéler une cellule dans la grille
- `POST /memory-grid/answer-cell` - Répondre à une cellule révélée

## Règles implémentées

### Manche 1
- ✅ Groupes de 2 ou 3 joueurs selon nombre total
- ✅ 3 jetons par équipe (SWAP, pénalité, bonus)
- ✅ Système de points (2/4/6 selon difficulté)
- ✅ Roue de bonus/malus (tous les 5 tours)

### À venir
- Manche 2 (individuelle avec choix de thème)
- Manche 3 (finale avec grille mémoire)

## Configuration

### Variables d'environnement
- `DATABASE_URL` : URL de connexion à la base de données
  - Développement : `sqlite:///./quizkw.db`
  - Production : `postgresql://user:pass@host/dbname`

### Base de données
- SQLite pour le développement
- PostgreSQL recommandé pour la production
- Migrations avec Alembic (à implémenter)

### Test de fumée PostgreSQL

La suite de tests principale (`pytest tests/`) tourne exclusivement sur
SQLite en mémoire. Un bug de migration réel (type enum redéclaré) ne s'est
manifesté que sous PostgreSQL — un test dédié comble cet angle mort.

**⚠️ Ce test exécute `alembic downgrade base` (destructeur, vide le schéma)
avant `upgrade head`. Ne jamais pointer `POSTGRES_TEST_URL` vers une base
contenant de vraies données.** Par sécurité, le test refuse de s'exécuter
(skip explicite) si l'hôte ou le nom de la base ne contient pas `test`.

1. Démarrer un PostgreSQL jetable, par exemple avec Docker :
   ```bash
   docker run --rm -e POSTGRES_PASSWORD=test -e POSTGRES_DB=quizkw_test -p 5432:5432 postgres
   ```
2. Positionner `POSTGRES_TEST_URL` (nom de base contenant `test`) et lancer le test :
   ```bash
   export POSTGRES_TEST_URL="postgresql://postgres:test@localhost:5432/quizkw_test"
   pytest tests/test_migration_smoke_postgres.py -v
   ```
3. Si `POSTGRES_TEST_URL` n'est pas positionnée, si la connexion échoue, ou
   si l'URL ne contient pas `test` dans l'hôte/la base, le test se marque
   `skipped` (pas d'échec, pas de faux positif) — c'est le comportement
   attendu sur une machine sans PostgreSQL jetable disponible.

À exécuter avant de committer toute migration Alembic modifiant le schéma.

## Développement

### Structure des données
Les modèles reflètent fidèlement les règles du jeu :
- **GameSession** : Session de jeu avec code unique
- **Team** : Équipes avec score et joueurs
- **Player** : Joueurs individuels
- **Question** : Questions avec difficulté et catégorie
- **Token** : Jetons utilisables par les équipes
- **Answer** : Réponses enregistrées

### Tests
Le script `seed.py` permet de tester rapidement l'API avec des données réalistes.

## Déploiement

### Production
```bash
# Avec Gunicorn (recommandé)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app

# Avec Docker (à créer)
docker build -t quizkw-backend .
docker run -p 8000:8000 quizkw-backend
```

### Sécurité
- CORS configuré pour le développement (`*`)
- À restreindre en production
- Validation des données avec Pydantic
- Gestion d'erreurs avec HTTPException

## Prochaines étapes

1. Implémenter les manches 2 et 3
2. Ajouter WebSockets pour le temps réel
3. Créer l'interface React
4. Ajouter l'authentification
5. Déployer en production

## Support

Pour toute question, consulter la documentation automatique ou ouvrir une issue.