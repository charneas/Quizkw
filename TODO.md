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

### 2. Questions Ping-Pong tous les 5 tours
**Problème:** Infrastructure créée, implémentation à compléter
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

### 4. Bouton d'aide pour les tests
**Problème:** Un bouton de dev/test est encore visible en production
**Localisation:** Probablement dans `DevHelper.tsx` ou pages de jeu
**Action requise:**
- Identifier le bouton concerné
- Le masquer en production (utiliser `import.meta.env.DEV`)
- Ou le supprimer complètement

**Fichiers concernés:**
- `frontend/src/components/DevHelper.tsx`
- Pages contenant des boutons de debug

**Code suggéré:**
```tsx
{import.meta.env.DEV && (
  <button>Debug Button</button>
)}
```

---

## 📊 État Actuel du Projet  

✅ **Complété:**
- ✅ 52/52 tests backend passent (100%)
- ✅ Synchronisation des questions COMPLÈTE
- ✅ Infrastructure ping-pong créée
- ✅ 232 questions en base
- ✅ 85 questions Round 3 importées
- ✅ Documentation complète

⚠️ **En cours:**
- ⚠️ Ping-pong: modèles créés, implémentation à terminer

❌ **À corriger:**
- ❌ Jetons non disponibles
- ❌ Bouton de test visible

---

## 🎯 Prochaines Étapes Recommandées

### Étape 1: Terminer Ping-Pong (6-8h) 
Voir `PING_PONG_TODO.md` pour le plan détaillé
1. Créer PingPongManager
2. Implémenter endpoints de duel
3. Adapter composants React
4. Intégration complète
5. Seed des 17 thèmes

### Étape 2: Corriger les Jetons (1-2h)
1. Débugger TokenPanel
2. Vérifier création en base
3. Tester utilisation

### Étape 3: Nettoyer DevHelper (15min)
1. Masquer en production
2. Tester build production

---

## 📝 Notes

**Priorité:** 
1. Terminer Ping-Pong (infrastructure déjà créée)
2. Corriger les jetons
3. Nettoyer le code de dev

**Questions Ping-Pong:** Nécessite une conception plus approfondie (format de réponse, scoring, UI).

**Tests:** Ajouter des tests E2E pour ces nouvelles fonctionnalités une fois implémentées.

---

Date de création: 2026-05-25
Dernière mise à jour: 2026-05-25
