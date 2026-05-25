# Synchronisation des Questions - Documentation

## 📋 Vue d'ensemble

La synchronisation des questions garantit que toutes les équipes répondent à la même question en même temps, avec un système d'attente pour les équipes ayant déjà répondu.

## 🎯 Fonctionnalités implémentées

### 1. **Backend - Endpoints de synchronisation**

#### `POST /games/{code}/set-current-question`
- Définit la question courante pour toutes les équipes
- Prend `question_id` dans le body JSON
- Stocke l'ID dans `GameSession.current_question_id`

#### `GET /games/{code}/current-question`
- Récupère la question courante synchronisée
- Retourne la question avec options mélangées

#### `GET /games/{code}/answers-status`
- Vérifie le statut des réponses pour la question courante
- Retourne:
  - `question_id`: ID de la question courante
  - `total_teams`: Nombre total d'équipes
  - `answered_teams`: Liste des IDs d'équipes ayant répondu
  - `remaining_teams`: Liste des IDs d'équipes n'ayant pas répondu
  - `all_answered`: Boolean indiquant si toutes les équipes ont répondu

#### Logique dans `POST /answers/`
- Après qu'une équipe répond, vérifie si toutes les équipes ont répondu
- Si oui, réinitialise `current_question_id` à `null`

### 2. **Frontend - Composant WaitingForTeams**

**Fichier**: `frontend/src/components/WaitingForTeams.tsx`

**Fonctionnalités**:
- ⏳ Animation de points d'attente
- 📊 Barre de progression visuelle
- 🎯 Affichage des équipes ayant répondu (checkmarks)
- 🔔 Détection automatique quand toutes les équipes ont répondu
- ✨ Design moderne et responsive

### 3. **Frontend - Logique de synchronisation dans Game.tsx**

#### États ajoutés:
```typescript
const [waitingForTeams, setWaitingForTeams] = useState(false)
const [answersStatus, setAnswersStatus] = useState<AnswersStatus | null>(null)
const pollingIntervalRef = useRef<number | null>(null)
```

#### Flux de synchronisation:

1. **Chargement de question** (`loadQuestion()`):
   - Récupère le statut des réponses
   - Si toutes les équipes ont répondu → charge nouvelle question
   - Si question courante existe → vérifie si l'équipe a déjà répondu
   - Si déjà répondu → affiche écran d'attente + démarre polling

2. **Système de polling** (`startPolling()`):
   - Vérifie le statut toutes les 2 secondes
   - Arrêt automatique quand toutes les équipes ont répondu
   - Cleanup automatique au démontage du composant

3. **Après réponse** (`handleAnswer()`):
   - Soumet la réponse
   - Met à jour le statut local
   - Récupère le nouveau statut des réponses

4. **Transition automatique** (`handleAllAnswered()`):
   - Arrête le polling
   - Cache l'écran d'attente
   - Passe automatiquement au tour suivant

## 🔄 Flux utilisateur

### Scénario type (3 équipes):

1. **Équipe A arrive en premier sur une question**
   - Voit la question
   - Répond
   - Voit son résultat (correct/incorrect)
   - Clique sur "Tour suivant"
   - → **Entre en mode attente** ⏳

2. **Équipe A en attente**
   - Voit un écran: "Attente des autres équipes..."
   - Barre de progression: 1/3 équipes ont répondu
   - Polling automatique toutes les 2s

3. **Équipe B répond**
   - Même processus
   - La barre de progression d'Équipe A se met à jour: 2/3 ✅

4. **Équipe C répond (dernière équipe)**
   - Équipe C voit son résultat
   - Équipes A et B détectent automatiquement que tous ont répondu
   - **Toutes les équipes passent automatiquement à la question suivante** 🚀

5. **Nouvelle question**
   - Toutes les équipes voient la même nouvelle question
   - Le cycle recommence

## 🛡️ Gestion des cas limites

### Équipe se reconnecte
- Si l'équipe a déjà répondu à la question courante → Mode attente
- Sinon → Peut répondre normalement

### Toutes les équipes ont répondu mais une équipe arrive
- Le backend a déjà réinitialisé `current_question_id` à `null`
- Nouvelle question sera définie automatiquement

### Rafraîchissement de page
- L'état de la question courante est persisté en base
- Le statut des réponses est récupéré via l'API
- Le système se resynchronise automatiquement

## 📊 Architecture technique

```
┌─────────────┐
│   Équipe A  │──┐
└─────────────┘  │
                 │    ┌──────────────────────────┐
┌─────────────┐  │    │   GameSession DB         │
│   Équipe B  │──┼───▶│  - current_question_id   │
└─────────────┘  │    │  - code                  │
                 │    └──────────────────────────┘
┌─────────────┐  │              │
│   Équipe C  │──┘              │
└─────────────┘                 ▼
                    ┌──────────────────────────┐
                    │   Answers Table          │
                    │  - team_id               │
                    │  - question_id           │
                    │  - answered_at           │
                    └──────────────────────────┘
```

### Synchronisation:
1. Question stockée dans `GameSession.current_question_id`
2. Réponses trackées dans table `Answer`
3. Frontend poll `/answers-status` pour détecter quand tous ont répondu
4. Backend réinitialise `current_question_id` quand tous ont répondu

## 🧪 Tests

### Backend
✅ Tous les 52 tests passent
- Tests des endpoints de synchronisation existants
- Aucune régression introduite

### À tester manuellement
- [ ] Créer un jeu avec 2-4 équipes
- [ ] Répondre à une question avec une équipe
- [ ] Vérifier que l'équipe entre en mode attente
- [ ] Répondre avec les autres équipes
- [ ] Vérifier que toutes les équipes passent automatiquement à la question suivante
- [ ] Tester la reconnexion d'une équipe
- [ ] Tester le rafraîchissement de page

## 🚀 Déploiement

### Fichiers modifiés:
1. `frontend/src/components/WaitingForTeams.tsx` *(nouveau)*
2. `frontend/src/pages/Game.tsx` *(modifié)*
3. `backend/main.py` *(modifié)*
4. `backend/app/schemas.py` *(modifié)*

### Pas de migration DB nécessaire
- Utilise les colonnes existantes (`current_question_id`)
- Pas de nouveaux modèles

## 💡 Améliorations futures possibles

1. **WebSocket au lieu de polling**
   - Notification instantanée en temps réel
   - Réduit la charge serveur

2. **Timeout automatique**
   - Si une équipe ne répond pas après X secondes
   - Passer automatiquement à la question suivante

3. **Indicateur de qui attend**
   - Afficher les noms des équipes ayant déjà répondu
   - "En attente de: Équipe Rouge, Équipe Bleue..."

4. **Mode host**
   - Permettre à un animateur de forcer le passage
   - Voir toutes les réponses en temps réel

5. **Statistiques**
   - Temps moyen de réponse par équipe
   - Progression de la partie

## 📝 Notes

- Le polling est configuré à 2 secondes (configurable dans `Game.tsx`)
- Le cleanup du polling est automatique au démontage du composant
- Compatible avec le système de tours existant (roue tous les 5 tours)
- N'interfère pas avec Round 2 et Round 3

---

**Date de création**: 25 mai 2026  
**Version**: 1.0.0  
**Auteur**: Cline AI Assistant
