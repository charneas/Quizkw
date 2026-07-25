import { test, expect, type APIRequestContext } from '@playwright/test';

/**
 * E2E Manche 3 (grille mémoire) en conditions réelles — story H-002.
 *
 * Périmètre (décision produit du 2026-07-25, voir
 * _bmad-output/h-002-test-e2e-manche-3-en-conditions-reelles.md) :
 * - Manche 1 : par l'UI réelle (création de partie, équipes, démarrage, quelques questions).
 * - Manche 2 et entrée en Manche 3 (qualification + finalistes) : par appels API directs.
 *   L'UI de la Manche 2 a des trous structurels indépendants (sélection de joueur non liée
 *   aux joueurs qualifiés, déclenchement de phase circulaire) hors périmètre de cette story —
 *   voir h-007-qualification-manche-1-vers-manche-2-inatteignable.md.
 * - Manche 3 (grille mémoire) : entièrement par l'UI réelle — c'est la cible de ce test.
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api par le serveur
 * de dev Vite, voir frontend/vite.config.ts) — playwright.config.ts ne démarre que le frontend.
 */

const TOTAL_PLAYERS = 8;
const PLAYERS_PER_TEAM = 2;
const TEAM_COUNT = TOTAL_PLAYERS / PLAYERS_PER_TEAM;
const GRID_CELLS = 35;

async function qualifyAndReachFinalists(request: APIRequestContext, code: string) {
  // Manche 1 -> Manche 2 : peuple PlayerRound2Stats et passe current_round à MANCHE_2.
  const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`);
  expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();
  const qualifyBody = await qualifyRes.json();
  const qualifiedPlayerIds: number[] = qualifyBody.qualified_player_ids;
  expect(qualifiedPlayerIds).toHaveLength(TOTAL_PLAYERS);

  // Chaque joueur qualifié choisit un thème et répond à ses 10 questions de Manche 2.
  const themesRes = await request.get(`/api/round2/${code}/themes`);
  expect(themesRes.ok(), await themesRes.text()).toBeTruthy();
  const { themes } = await themesRes.json();
  expect(themes.length).toBeGreaterThan(0);
  const themeId = themes[0].id;

  for (const playerId of qualifiedPlayerIds) {
    const selectRes = await request.post(`/api/round2/${code}/select-theme`, {
      data: { player_id: playerId, theme_id: themeId },
    });
    expect(selectRes.ok(), await selectRes.text()).toBeTruthy();

    for (let i = 0; i < 10; i++) {
      const questionRes = await request.get(`/api/round2/${code}/question?player_id=${playerId}`);
      expect(questionRes.ok(), await questionRes.text()).toBeTruthy();
      const question = await questionRes.json();

      const answerRes = await request.post(`/api/round2/${code}/answer`, {
        data: {
          player_id: playerId,
          question_id: question.question.id,
          player_answer: 'peu importe la justesse ici',
        },
      });
      expect(answerRes.ok(), await answerRes.text()).toBeTruthy();
    }
  }

  // 16 -> 8 -> 4 : selon l'implémentation actuelle, le statut QUALIFIED peut déjà être
  // posé dès la fin des 10 questions (pas seulement au moment de l'appel advance), donc
  // le premier appel peut atteindre directement "4_finalists" au lieu de s'arrêter à
  // "8_qualified". On appelle jusqu'à obtenir "4_finalists", sans figer l'ordre exact.
  let phase = '';
  for (let i = 0; i < 2 && phase !== '4_finalists'; i++) {
    const advanceRes = await request.post(`/api/round2/${code}/advance`);
    expect(advanceRes.ok(), await advanceRes.text()).toBeTruthy();
    phase = (await advanceRes.json()).new_phase;
  }
  expect(phase).toBe('4_finalists');
}

test.describe('Manche 3 - Grille mémoire (E2E réel)', () => {
  test.setTimeout(180_000); // 35 cellules x plusieurs appels réseau chacune

  test('crée une partie, atteint la Manche 3 et complète la grille jusqu\'aux résultats', async ({ page, request }) => {
    // ============================================================
    // Manche 1 par l'UI réelle
    // ============================================================
    await page.goto('/');
    await page.click('button:has-text("Nouvelle partie")');

    await page.fill('input[type="number"]', String(TOTAL_PLAYERS));
    await page.click(`button:has-text("${PLAYERS_PER_TEAM} joueurs")`);
    await page.click('button:has-text("🚀 Créer la partie")');

    await page.waitForURL(/\/lobby\//, { timeout: 10_000 });
    const code = page.url().split('/').pop()!;
    console.log(`Partie créée : ${code}`);

    for (let i = 1; i <= TEAM_COUNT; i++) {
      await page.fill('input[placeholder="Nom de l\'équipe"]', `Équipe ${i}`);
      await page.click('button:has-text("Ajouter")');
      await expect(page.locator(`text=Équipe ${i}`)).toBeVisible({ timeout: 5_000 });
    }

    await page.click('button:has-text("🎯 Démarrer le jeu")');

    // Lobby.tsx ne navigue pas automatiquement après le démarrage (gameStarted est un
    // état local) — l'écran hôte réel de la Manche 1 est HostGame.tsx (/game/:code/host).
    // Game.tsx (/game/:code) n'est pas atteint par un parcours utilisateur normal ; les
    // équipes répondent sur leur propre écran (TeamScreen.tsx), pas sur l'écran hôte.
    // Aucun AC de cette story n'exige de jouer les réponses de Manche 1 en détail — on
    // vérifie juste que l'écran hôte réel se charge, ce qui confirme que la partie est
    // bien passée en jeu actif avant la préparation API de la Manche 2.
    await page.goto(`/game/${code}/host`);
    await expect(page.locator('text=Manche 1 — Hôte')).toBeVisible({ timeout: 10_000 });

    // ============================================================
    // Manche 2 et entrée en Manche 3 : setup API direct (voir en-tête de fichier)
    // ============================================================
    await qualifyAndReachFinalists(request, code);

    // ============================================================
    // Manche 3 par l'UI réelle
    // ============================================================
    await page.goto(`/game/${code}/memory-grid`);
    await expect(page.locator('text=Manche 3')).toBeVisible({ timeout: 20_000 });

    // Boucle : révéler une cellule -> répondre -> attendre la mise à jour, jusqu'à 35/35.
    let previousProgress = -1;
    for (let cellIndex = 0; cellIndex < GRID_CELLS; cellIndex++) {
      await expect(page.locator('text=/Progression: \\d+\\/35/')).toBeVisible({ timeout: 15_000 });

      // Une cellule cachée affiche exactement "?" (MemoryGrid.tsx getCellContent) —
      // révélée = "❓", complétée = initiale du joueur ou "✓" ; le nom accessible
      // exact évite de confondre ces états.
      const cell = page.getByRole('button', { name: '?', exact: true }).first();

      if (!(await cell.isVisible({ timeout: 5_000 }).catch(() => false))) {
        break; // grille déjà complétée (aucune cellule cachée restante)
      }

      await cell.click();
      await expect(page.locator('h3:has-text("Cellule révélée !")')).toBeVisible({ timeout: 10_000 });

      await page.fill('input[placeholder="Saisir la réponse..."]', 'réponse de test');
      await page.click('button:has-text("Valider la réponse")');

      // La modale se ferme après soumission (bonne ou mauvaise réponse).
      await expect(page.locator('h3:has-text("Cellule révélée !")')).not.toBeVisible({ timeout: 10_000 });

      const progressText = await page.locator('text=/Progression: \\d+\\/35/').textContent();
      const match = progressText?.match(/Progression: (\d+)\/35/);
      const currentProgress = match ? parseInt(match[1], 10) : previousProgress;
      expect(currentProgress).toBeGreaterThan(previousProgress);
      previousProgress = currentProgress;

      if (currentProgress >= GRID_CELLS) break;
    }

    // ============================================================
    // Écran de victoire et redirection vers les résultats
    // ============================================================
    await expect(page.locator('text=Partie terminée !')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('text=4 finalistes')).toBeVisible();

    // C-004 : statistiques de fin de partie par finaliste (cellules contrôlées).
    await expect(page.locator('text=/cellules contrôlées/').first()).toBeVisible();
    await expect(page.locator('text=/propres, \\d+ volées, \\d+ neutres/').first()).toBeVisible();

    await page.click('button:has-text("Voir les résultats →")');
    await page.waitForURL(/\/results\//, { timeout: 10_000 });
    expect(page.url()).toContain(`/results/${code}`);

    await expect(page.locator('text=/Score|Classement|Résultats|Gagnant/i').first()).toBeVisible({ timeout: 10_000 });
  });
});
