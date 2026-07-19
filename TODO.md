# TODO - Points à corriger

## 🔴 Priorités Hautes

### 1. ✅ Synchronisation des questions - COMPLÉTÉ
**Statut:** ✅ TERMINÉ ET TESTÉ
**Description:** Toutes les équipes répondent à la même question en même temps
**Résultat:** 
- Écran d'attente avec barre de progression
- Système de polling automatique (2s)
- Transition automatique quand tous ont répondu
- 52/52 tests backend passent
- Documentation: `SYNCHRONISATION_QUESTIONS.md`

---

### 2. ✅ Questions Ping-Pong tous les 5 tours - COMPLÉTÉ
**Statut:** ✅ TERMINÉ ET FONCTIONNEL
**Description:** Tous les 5 tours, DUEL 1v1 entre 2 équipes (tour par tour, première sans bonne réponse = perd)

**État actuel:**
- ✅ Modèles DB créés (`PingPongDuel`, `PingPongTurn`, `PingPongTheme`)
- ✅ Schémas Pydantic pour les duels
- ✅ Composants React de base créés
- ⚠️ Manager et endpoints à implémenter
- ⚠️ Composants à adapter pour format duel

**Plan complet:** Voir `PING_PONG_TODO.md` (6-8h de travail estimées)

**17 Thèmes à ajouter:**
1. Pays ayant le Français en langue officielle
2. Présidents de la 5ème République
3. Artistes français à l'Eurovision
4. Pays ayant organisé les JO d'été
5. Auteurs classiques français
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

---

### 3. Jetons (Tokens) - Non disponibles
**Problème:** Les jetons ne sont pas disponibles dans le jeu
**Localisation:** Round 1 - Gameplay
**Action requise:**
- Vérifier l'implémentation du TokenPanel
- S'assurer que les jetons sont créés en base lors du setup
- Vérifier que le composant TokenPanel est bien affiché
- Tester l'utilisation des jetons (SWAP, PENALTY, BONUS)

**Fichiers concernés:**
- `frontend/src/components/TokenPanel.tsx`
- `backend/app/models.py` (Token model)
- `frontend/src/pages/Game.tsx`

---

### 4. ✅ Bouton d'aide pour les tests - COMPLÉTÉ
**Statut:** ✅ MASQUÉ EN PRODUCTION
**Solution:** Ajout de `import.meta.env.DEV` autour de `<DevHelper>` dans `Game.tsx` et `Lobby.tsx`, ainsi que le texte de référence dans Lobby.
**Fichiers modifiés:**
- `frontend/src/pages/Game.tsx`
- `frontend/src/pages/Lobby.tsx`

---

## 📊 État Actuel du Projet  

✅ **Complété:**
- ✅ 52/52 tests backend passent (100%)
- ✅ Synchronisation des questions COMPLÈTE
- ✅ Ping-Pong duels COMPLET (17 thèmes, modèles, UI, résultats)
- ✅ 232 questions en base + 85 questions Round 3
- ✅ **Manche 3 — Grille Mémoire COMPLÈTE** (backend + frontend)
  - Backend: `create_memory_grid`, `reveal_cell`, `answer_cell`, `get_grid_state`
  - Frontend: `MemoryGrid.tsx` avec grille 7×5, couleurs par équipe, popup question, scoring
  - Format API aligné: `{memory_grid: {...}, cells: [...]}`
  - Navigation: HostGame → Manche 3, Round2 → Manche 3

⚠️ **En cours / À tester:**
- ⚠️ Manche 3: test end-to-end en conditions réelles (lancer serveur + navigateur)

❌ **À corriger:**
- ❌ Jetons non disponibles dans le jeu (Manche 1)

---

## 🎯 Prochaines Étapes Recommandées

### Étape 1: Test E2E Manche 3 (30min)
1. Lancer backend + frontend
2. Créer partie, avancer en Manche 3
3. Tester grille: cliquer cellule → voir question → répondre → score
4. Tester complétion

### Étape 2: Polissage Manche 3 (1-2h)
1. Timer par question (30s)
2. Son/animation de révélation
3. Meilleure indication de la cellule sélectionnée
4. Page de résultats finaux

### Étape 3: Corriger les Jetons Manche 1 (1-2h)
1. Débugger TokenPanel
2. Vérifier création en base lors du setup
3. Tester utilisation

---

## 📝 Notes

**Architecture Manche 3:**
- Backend: `backend/app/memory_grid.py` (MemoryGridManager)
- Frontend: `frontend/src/pages/MemoryGrid.tsx`
- Grille 7×5 = 35 cellules, 5 par équipe (couleur) + 15 neutres
- Points: 2 base + 1 bonus cellule propre OU +1 bonus vol

---

Date de création: 2026-05-25
Dernière mise à jour: 2026-07-19
