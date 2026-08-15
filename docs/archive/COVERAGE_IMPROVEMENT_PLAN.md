# Plan d'Amélioration de la Couverture de Code

## État Actuel de la Couverture (82% globale)

### Modules et leur Couverture Actuelle

1. **app/memory_grid.py** : 33% (151 lignes, 101 manquées) ⚠️ **CRITIQUE**
2. **app/database.py** : 73% (15 lignes, 4 manquées)
3. **app/round2_manager.py** : 91% (148 lignes, 13 manquées)
4. **app/models.py** : 100% (121 lignes, 0 manquées) ✅
5. **app/schemas.py** : 96% (272 lignes, 12 manquées)

## Analyse des Zones Non Couvertes

### 1. MemoryGridManager (Le Plus Critique)

**Lignes non couvertes** : 57, 61-151, 155-162, 166-180, 198-235, 246-274, 287-302

**Fonctionnalités non testées** :
- Création de grille de mémoire (7x5)
- Assignation des cellules aux équipes
- Révélation/réponse aux cellules
- Logique de tour par tour
- Calcul des scores
- Gestion des équipes gagnantes

### 2. Database (Mineur)

**Lignes non couvertes** : 23-27 (gestion des connexions et rollback)

### 3. Round2Manager (Bon mais peut être amélioré)

**Lignes non couvertes** : 26, 62, 69, 108, 112, 135, 173-174, 225, 261-264, 313
- Principalement des cas d'erreur et des vérifications de sécurité

### 4. Schemas (Très bon)

**Lignes non couvertes** : 43-57 (quelques champs optionnels)

## Plan d'Action par Priorité

### Phase 1 : MemoryGridManager (Haute Priorité)
**Objectif** : Porter la couverture de 33% à >80%

#### Tâches :
1. **Créer `tests/test_memory_grid.py`** avec :
   - Fixtures pour MemoryGrid, GridCell, MemoryGridRound
   - Tests de création de grille (7x5)
   - Tests d'assignation d'équipes (5 cellules par équipe)
   - Tests de révélations de cellules
   - Tests de soumission de réponses
   - Tests de calcul de scores
   - Tests de gestion des tours

2. **Cas de test critiques** :
   - Grille avec nombre insuffisant de questions
   - Équipes multiples (2-4 équipes)
   - Cellules sans assignation d'équipe
   - Conditions de victoire
   - Gestion des erreurs (cellules déjà révélées, etc.)

### Phase 2 : Round2Manager (Amélioration)
**Objectif** : Porter la couverture de 91% à >95%

#### Tâches :
1. **Ajouter des tests pour les cas d'erreur** :
   - `select_theme` avec thème inexistant
   - `submit_answer` avec question non valide
   - Vérifications de sécurité des IDs de joueur

2. **Tests de performance et concurrence** :
   - Création simultanée de statistiques
   - Mise à jour de classement avec plusieurs joueurs

### Phase 3 : Database et Schemas (Faible Priorité)
**Objectif** : Porter la couverture globale à >85%

#### Tâches :
1. **Tester les rollbacks de transaction**
2. **Tester les schémas avec données limites**

## Plan d'Exécution Détaillé

### Jour 1 : Configuration des Tests MemoryGrid
```bash
# Créer le fichier de test
touch tests/test_memory_grid.py

# Ajouter les fixtures nécessaires dans conftest.py
# Créer des fixtures pour :
# - sample_memory_grid
# - sample_grid_cell
# - sample_memory_grid_round
# - memory_grid_manager
```

### Jour 2 : Tests de Création de Grille
- `test_create_memory_grid_success`
- `test_create_memory_grid_insufficient_questions`
- `test_create_memory_grid_no_teams`

### Jour 3 : Tests de Logique de Jeu
- `test_reveal_cell_success`
- `test_reveal_already_revealed_cell`
- `test_answer_cell_correct`
- `test_answer_cell_incorrect`

### Jour 4 : Tests de Scores et Victoire
- `test_calculate_scores`
- `test_determine_winner`
- `test_handle_tie`

### Jour 5 : Tests d'Intégration
- `test_complete_memory_grid_flow`
- `test_multiple_teams_competition`

## Métriques de Suivi

### Objectifs de Couverture :
- **MemoryGridManager** : >80%
- **Round2Manager** : >95%
- **Global** : >85%

### Points de Contrôle :
- Après Phase 1 : Couverture globale >75%
- Après Phase 2 : Couverture globale >82%
- Après Phase 3 : Couverture globale >85%

## Outils de Surveillance

### Exécution Régulière :
```bash
# Tous les tests avec couverture
python -m pytest tests/ --cov=app --cov-report=term-missing

# Tests spécifiques à MemoryGrid
python -m pytest tests/test_memory_grid.py -v

# Générer rapport HTML
python -m pytest tests/ --cov=app --cov-report=html
```

### Intégration Continue :
```yaml
# Dans GitHub Actions
- name: Run tests with coverage
  run: |
    cd backend
    python -m pytest tests/ --cov=app --cov-report=xml --cov-fail-under=85
```

## Risques et Atténuation

### Risque 1 : Complexité de MemoryGrid
**Atténuation** : Commencer par des tests simples de création, puis ajouter progressivement la logique complexe.

### Risque 2 : Dépendances aux Fixtures
**Atténuation** : Créer des fixtures modulaires et réutilisables.

### Risque 3 : Performance des Tests
**Atténuation** : Utiliser SQLite en mémoire, limiter le nombre de données de test.

## Critères de Succès

1. **Couverture** :
   - MemoryGridManager >80%
   - Global >85%

2. **Qualité des Tests** :
   - Tests isolés et reproductibles
   - Bonnes pratiques de nommage
   - Assertions claires

3. **Documentation** :
   - Commentaires dans les tests complexes
   - README mis à jour
   - Exemples d'exécution

## Références

- [Documentation Pytest](https://docs.pytest.org/)
- [SQLAlchemy Testing Guide](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

## Prochaines Étapes

1. Examiner les lignes exactes manquantes dans memory_grid.py
2. Créer les fixtures nécessaires dans conftest.py
3. Implémenter les tests phase par phase
4. Valider l'amélioration de la couverture après chaque phase