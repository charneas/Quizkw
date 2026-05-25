# Implémentation des Questions Ping-Pong - Plan Détaillé

## 📋 Format Ping-Pong

**Type**: DUEL 1v1 entre 2 équipes  
**Règle**: Tour par tour, première équipe sans bonne réponse = perd  
**Points**: +2 par réponse correcte donnée par le gagnant

## ✅ Infrastructure Créée

### Backend
- ✅ Modèles `PingPongTheme`, `PingPongDuel`, `PingPongTurn`  
- ✅ Schémas Pydantic pour les duels
- ⚠️ Anciens endpoints à remplacer

### Frontend
- ✅ Composants `PingPongQuestion.tsx`, `PingPongResults.tsx`
- ⚠️ À adapter pour le format duel

## 🔧 À Implémenter

### 1. Backend - Manager Ping-Pong

Créer `backend/app/ping_pong_manager.py`:

```python
class PingPongManager:
    def __init__(self, db: Session):
        self.db = db
    
    def start_duel(self, game_id: int, theme_id: int, team1_id: int, team2_id: int):
        """Créer un nouveau duel ping-pong"""
        # Créer le PingPongDuel
        # Définir team1 comme first turn
        # Retourner l'état du duel
        
    def submit_answer(self, duel_id: int, team_id: int, answer: str):
        """Soumettre une réponse pour un duel"""
        # Vérifier que c'est le tour de l'équipe
        # Normaliser la réponse (lower, strip)
        # Vérifier si la réponse est dans correct_answers
        # Vérifier qu'elle n'a pas déjà été donnée
        
        if is_correct:
            # Créer PingPongTurn
            # Ajouter à answers_used
            # Changer current_turn_team_id
            # Retourner {continues: True, next_team: ...}
        else:
            # Marquer le duel comme terminé
            # L'autre équipe gagne
            # Calculer les points (+2 par réponse correcte)
            # Retourner {continues: False, winner: ...}
    
    def get_duel_state(self, duel_id: int):
        """Récupérer l'état actuel d'un duel"""
```

### 2. Backend - Nouveaux Endpoints

Remplacer les endpoints ping-pong existants dans `main.py`:

```python
@app.post("/ping-pong/duel/start")
def start_ping_pong_duel(request: schemas.StartPingPongDuelRequest, db: Session = Depends(get_db)):
    """
    Démarrer un duel ping-pong entre 2 équipes
    """
    # Utiliser PingPongManager.start_duel()
    pass

@app.post("/ping-pong/duel/answer")
def submit_ping_pong_answer(request: schemas.SubmitPingPongAnswerRequest, db: Session = Depends(get_db)):
    """
    Soumettre une réponse dans un duel
    """
    # Utiliser PingPongManager.submit_answer()
    pass

@app.get("/ping-pong/duel/{duel_id}")
def get_ping_pong_duel(duel_id: int, db: Session = Depends(get_db)):
    """
    Récupérer l'état d'un duel
    """
    # Utiliser PingPongManager.get_duel_state()
    pass

@app.get("/ping-pong/duel/{duel_id}/results")
def get_ping_pong_results(duel_id: int, db: Session = Depends(get_db)):
    """
    Récupérer les résultats finaux d'un duel
    """
    pass
```

### 3. Frontend - Sélection des Équipes

Créer `frontend/src/components/PingPongTeamSelector.tsx`:

```typescript
// Composant pour sélectionner les 2 équipes qui vont s'affronter
// Options:
// 1. Équipe courante vs équipe suivante
// 2. Équipe courante vs choix manuel
// 3. Choix manuel des 2 équipes (mode animateur)
```

### 4. Frontend - Adapter PingPongQuestion

Modifications à faire:
- Afficher les 2 équipes qui s'affrontent
- Afficher quelle équipe doit jouer
- Afficher les réponses déjà données
- Désactiver le timer auto-submit (c'est un duel)
- Ajouter bouton "Passer" si l'équipe abandonne
- Une seule réponse à la fois (pas une liste)

### 5. Frontend - Flux du Jeu

Dans `Game.tsx`:

```typescript
// Tour 5, 10, 15, etc.
if (turnCount % 5 === 0) {
  // 1. Obtenir un thème aléatoire
  const theme = await getRandomPingPongTheme()
  
  // 2. Sélectionner les 2 équipes
  //    Option simple: équipe courante vs équipe suivante
  const team1 = game.teams[currentTeamIndex]
  const team2 = game.teams[(currentTeamIndex + 1) % game.teams.length]
  
  // 3. Démarrer le duel
  const duel = await startPingPongDuel({
    game_session_id: game.id,
    theme_id: theme.id,
    team1_id: team1.id,
    team2_id: team2.id
  })
  
  // 4. Afficher le composant duel
  setShowPingPong(true)
  setPingPongDuel(duel)
}
```

## 📝 Ordre d'Implémentation Recommandé

1. **Backend Manager** (1-2h)
   - Créer `ping_pong_manager.py`
   - Implémenter la logique de duel
   - Tests unitaires

2. **Backend Endpoints** (30min)
   - Remplacer les endpoints existants
   - Utiliser le manager

3. **Frontend API** (15min)
   - Mettre à jour `api.ts` avec les nouveaux endpoints

4. **Frontend Composants** (2-3h)
   - Adapter `PingPongQuestion` pour le format duel
   - Créer `PingPongTeamSelector` si nécessaire
   - Adapter `PingPongResults` pour afficher le duel

5. **Intégration** (1h)
   - Intégrer dans `Game.tsx`
   - Gérer le flux complet

6. **Seed Database** (30min)
   - Script pour ajouter les 17 thèmes du TODO.md

7. **Tests** (1h)
   - Tester avec plusieurs équipes
   - Tester les cas limites

## 🎯 Thèmes Ping-Pong à Ajouter

1. Pays ayant le Français en langue officielle
2. Présidents de la 5ème République
3. Artistes français à l'Eurovision  
4. Pays ayant organisé les JO d'été
5. Auteurs classiques français (19e et avant)
6. Films du MCU
7. Marques de voiture en activité
8. Agents Valorant
9. Plats de la cuisine française
10. Ustensiles de cuisine
11. Capitales de l'UE
12. Pays bordant la Méditerranée
13. Pays commençant par M
14. Personnages de Sonic
15. Consoles de salon
16. Franchises NBA
17. Fast Food en France

## ⚠️ Notes Importantes

- Le format duel est TRÈS différent du format "toutes les équipes répondent"
- Nécessite une gestion d'état complexe (tour par tour)
- Attention aux doublons de réponses (case-insensitive)
- Bien gérer l'attribution des points au gagnant
- UX importante: bien montrer qui joue et qui attend

## 📚 Ressources

- Modèles DB: `backend/app/models.py` (PingPongDuel, PingPongTurn)
- Schémas: `backend/app/schemas.py` (section Ping-Pong)
- Composants existants: `frontend/src/components/PingPong*.tsx`

---

**Date**: 25 mai 2026  
**Statut**: Infrastructure créée, implémentation à compléter  
**Temps estimé**: 6-8 heures de développement
