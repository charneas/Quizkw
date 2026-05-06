# Tests Unitaires Reproducibles - Quizkw Backend

Ce document décrit comment exécuter les tests unitaires de manière reproducible pour le projet Quizkw.

## Environnement de Test

Le projet utilise un environnement virtuel Python pour isoler les dépendances.

### Configuration Initiale

1. **Créer l'environnement virtuel** (déjà fait) :
   ```bash
   cd backend
   python -m venv venv
   ```

2. **Activer l'environnement virtuel** :
   - Windows (PowerShell) :
     ```powershell
     .\venv\Scripts\activate
     ```
   - Linux/Mac :
     ```bash
     source venv/bin/activate
     ```

3. **Installer les dépendances de développement** :
   ```bash
   python -m pip install -r requirements-dev.txt
   ```

## Exécution des Tests

### Tous les tests
```bash
python -m pytest tests/ -v
```

### Tests spécifiques
```bash
python -m pytest tests/test_round2_manager.py -v
python -m pytest tests/test_round2_manager.py::TestRound2Manager::test_get_available_themes -v
```

### Avec couverture de code
```bash
python -m pytest tests/ --cov=app --cov-report=html --cov-report=term
```

### Lancer les tests en parallèle (accélération)
```bash
python -m pytest tests/ -n auto
```

## Fixtures de Test

Les tests utilisent des fixtures définies dans `tests/conftest.py` :

- `db_session` : Session de base de données SQLite en mémoire
- `sample_game_session` : Session de jeu de test
- `sample_theme` : Thème de test
- `sample_player` : Joueur de test
- `sample_question` : Question de test
- `sample_player_stats` : Statistiques Round 2 de test
- `round2_manager` : Instance de Round2Manager pour les tests

## Caractéristiques de Reproductibilité

### Isolation des Tests
- Chaque test s'exécute dans une transaction séparée qui est rollbackée à la fin
- Base de données SQLite en mémoire, redémarrée pour chaque test
- Pas de dépendance aux données de production

### Fixtures Reproductibles
- Les fixtures créent des données de test déterministes
- Les objets ont des IDs prévisibles et des valeurs constantes

### Environnement Contrôlé
- Toutes les dépendances sont verrouillées dans `requirements-dev.txt`
- Environnement virtuel isolé du système
- Version spécifique de Python (3.12.6)

## Structure des Tests

### Round2Manager (Composant Critique)
Les tests couvrent les scénarios suivants :
- Sélection de thème (succès, échecs)
- Récupération de questions
- Soumission de réponses
- Calcul de scores
- Classements intermédiaires
- Progression du tournoi

### Tests d'Intégration
- Interaction avec la base de données
- Validation des schémas Pydantic
- Gestion des erreurs métier

## Résolution de Problèmes

### Problèmes Courants

#### "Module not found"
```bash
# Vérifier que l'environnement virtuel est activé
# Réinstaller les dépendances
python -m pip install -r requirements-dev.txt --force-reinstall
```

#### Tests qui échouent après des modifications
```bash
# Nettoyer le cache pytest
python -m pytest --cache-clear
# Supprimer le répertoire __pycache__
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```

#### Problèmes de base de données
Les tests utilisent SQLite en mémoire. Si des problèmes persistent :
- Vérifier que les migrations sont à jour
- Réinitialiser la base de données de test

## Intégration Continue (CI)

Pour intégrer ces tests dans un pipeline CI :

```yaml
# Exemple GitHub Actions
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: |
          cd backend
          python -m pip install -r requirements-dev.txt
          python -m pytest tests/ --cov=app --cov-report=xml
```

## Maintenance

### Mettre à jour les dépendances
```bash
# Générer un nouveau fichier requirements
python -m pip freeze > requirements-dev.txt
# Vérifier les mises à jour de sécurité
python -m pip list --outdated
```

### Ajouter de nouveaux tests
1. Créer un fichier `tests/test_*.py`
2. Utiliser les fixtures existantes
3. S'assurer de l'isolation des tests
4. Ajouter des assertions claires

### Suivi de la Couverture
La couverture de code est surveillée via `pytest-cov`. Objectif : maintenir >80% de couverture.

## Références

- [Documentation Pytest](https://docs.pytest.org/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)