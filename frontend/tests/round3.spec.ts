import { test, expect, type APIRequestContext, type Browser } from '@playwright/test';

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

async function qualifyAndReachFinalists(request: APIRequestContext, code: string, hostToken: string) {
  const hostHeaders = { 'X-Host-Token': hostToken };

  // Manche 1 -> Manche 2 : peuple PlayerRound2Stats et passe current_round à MANCHE_2.
  const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`, { headers: hostHeaders });
  expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();
  const qualifyBody = await qualifyRes.json();
  const qualifiedPlayerIds: number[] = qualifyBody.qualified_player_ids;
  expect(qualifiedPlayerIds).toHaveLength(TOTAL_PLAYERS);

  // La Manche 2 se joue en tour par rôle (round2_turn_order) : un seul joueur
  // à la fois a le droit de choisir un thème / répondre (_check_players_turn
  // lève "Ce n'est pas votre tour" sinon). Chaque joueur joue 2 rounds de 10
  // questions (2 thèmes) avant de passer QUALIFIED — le tour n'avance qu'une
  // fois les 10 questions d'un round terminées (round2_manager._advance_turn).
  // On suit donc le tour désigné par le serveur au lieu d'itérer dans un
  // ordre fixe.
  let guard = 0;
  while (guard++ < qualifiedPlayerIds.length * 25) {
    const progressRes = await request.get(`/api/round2/${code}/progress`);
    expect(progressRes.ok(), await progressRes.text()).toBeTruthy();
    const progress = await progressRes.json();
    if (progress.phase !== '16_players') break;

    const playerId = progress.current_turn_player_id;
    if (!playerId) break;

    const playersRes = await request.get(`/api/round2/${code}/players`);
    expect(playersRes.ok(), await playersRes.text()).toBeTruthy();
    const players = await playersRes.json();
    const me = players.find((p: { id: number }) => p.id === playerId);

    if (!me.round2_stats.theme_id) {
      // BUG-210 : les thèmes sont exclusifs entre joueurs — liste fraîche à
      // chaque sélection plutôt que de réutiliser un id déjà pris.
      const themesRes = await request.get(`/api/round2/${code}/themes`);
      expect(themesRes.ok(), await themesRes.text()).toBeTruthy();
      const { themes } = await themesRes.json();
      expect(themes.length).toBeGreaterThan(0);

      const selectRes = await request.post(`/api/round2/${code}/select-theme`, {
        data: { player_id: playerId, theme_id: themes[0].id },
      });
      expect(selectRes.ok(), await selectRes.text()).toBeTruthy();
      continue;
    }

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

  // 16 -> 8 -> 4 : selon l'implémentation actuelle, le statut QUALIFIED peut déjà être
  // posé dès la fin des 10 questions (pas seulement au moment de l'appel advance), donc
  // le premier appel peut atteindre directement "4_finalists" au lieu de s'arrêter à
  // "8_qualified". On appelle jusqu'à obtenir "4_finalists", sans figer l'ordre exact.
  let phase = '';
  for (let i = 0; i < 2 && phase !== '4_finalists'; i++) {
    const advanceRes = await request.post(`/api/round2/${code}/advance`, { headers: hostHeaders });
    expect(advanceRes.ok(), await advanceRes.text()).toBeTruthy();
    phase = (await advanceRes.json()).new_phase;
  }
  expect(phase).toBe('4_finalists');
}

/**
 * Playtest 2026-08-15 : la Manche 3 n'est plus un « écran partagé » où
 * n'importe quel appareil peut configurer/jouer à la place d'un finaliste —
 * chaque finaliste agit désormais depuis SON PROPRE appareil (identifié via
 * `quizkw_player_${code}` en localStorage, cf. MemoryGrid.tsx). Un vrai test
 * E2E doit donc ouvrir un contexte de navigateur distinct par finaliste.
 */
async function openFinalistContext(browser: Browser, code: string, playerId: number) {
  const context = await browser.newContext();
  await context.addInitScript(
    ([c, id]) => {
      window.localStorage.setItem(`quizkw_player_${c}`, JSON.stringify({ id }));
    },
    [code, playerId]
  );
  const page = await context.newPage();
  return { context, page };
}

test.describe('Manche 3 - Grille mémoire (E2E réel)', () => {
  test.setTimeout(180_000); // 35 cellules x plusieurs appels réseau chacune

  test('crée une partie, atteint la Manche 3 et complète la grille jusqu\'aux résultats', async ({ page, request, browser }) => {
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

    // BUG-103 : le host_token est stocké côté navigateur (localStorage) par
    // Home.tsx à la création — nécessaire pour les appels API directs de
    // qualifyAndReachFinalists ci-dessous (qualify-round2, advance).
    const hostToken = await page.evaluate(
      (c) => localStorage.getItem(`quizkw_host_token_${c}`),
      code
    );
    if (!hostToken) throw new Error('host_token introuvable dans localStorage après création de partie');

    for (let i = 1; i <= TEAM_COUNT; i++) {
      await page.fill('input[placeholder="Nom de l\'équipe"]', `Équipe ${i}`);
      await page.click('button:has-text("Ajouter")');
      await expect(page.locator(`text=Équipe ${i}`)).toBeVisible({ timeout: 5_000 });
    }

    // BUG-201 : le bouton "Démarrer" reste désactivé tant que chaque équipe
    // n'a pas son quota réel de joueurs (l'auto-fill silencieux côté serveur
    // a été retiré) — il faut donc réellement les faire rejoindre ici.
    for (let i = 1; i <= TEAM_COUNT; i++) {
      const teamCard = page.locator('div.bg-surface-raised', { hasText: `Équipe ${i}` });
      for (let j = 1; j <= PLAYERS_PER_TEAM; j++) {
        await teamCard.locator('input[placeholder="Votre pseudo"]').fill(`Joueur ${i}-${j}`);
        await teamCard.locator('button:has-text("Rejoindre cette équipe")').click();
        await expect(teamCard.locator(`text=Joueur ${i}-${j}`)).toBeVisible({ timeout: 5_000 });
      }
    }

    await expect(page.locator('button:has-text("🎯 Démarrer le jeu")')).toBeEnabled({ timeout: 5_000 });
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
    await qualifyAndReachFinalists(request, code, hostToken);

    // ============================================================
    // Manche 3 par l'UI réelle — chaque finaliste sur son PROPRE appareil
    // (playtest 2026-08-15), l'hôte (cette `page`) n'orchestre que la
    // création/démarrage de la grille, il ne joue jamais à sa place.
    // ============================================================
    const finalistsRes = await request.get(`/api/games/${code}/memory-grid/finalists`);
    expect(finalistsRes.ok(), await finalistsRes.text()).toBeTruthy();
    const { finalists: finalistIds } = await finalistsRes.json();
    expect(finalistIds).toHaveLength(4);

    await page.goto(`/game/${code}/memory-grid`);
    await expect(page.locator('text=Manche 3')).toBeVisible({ timeout: 20_000 });

    // L'hôte ne doit jamais voir de bouton "Configurer" (il n'est finaliste
    // d'aucun setup) — seulement le statut prêt/pas prêt de chacun.
    await expect(page.getByRole('button', { name: 'Configurer' })).toHaveCount(0);

    const finalistContexts = await Promise.all(
      finalistIds.map((id: number) => openFinalistContext(browser, code, id))
    );

    for (const { page: finalistPage } of finalistContexts) {
      await finalistPage.goto(`/game/${code}/memory-grid`);

      // Seul CE finaliste voit son propre bouton "Configurer" — jamais celui
      // des 3 autres (chacun sur son propre appareil, cf. openFinalistContext).
      const configureButton = finalistPage.getByRole('button', { name: 'Configurer' });
      await expect(configureButton).toHaveCount(1, { timeout: 15_000 });
      await configureButton.click();

      await expect(finalistPage.locator('h3:has-text("Setup de")')).toBeVisible({ timeout: 10_000 });

      // Couleur : la première proposée est toujours disponible (les prises sont
      // exclues côté serveur, BUG-302). Sélecteur scopé au conteneur des
      // couleurs (flex-wrap) pour ne jamais matcher "Annuler"/"Valider" en bas
      // de la modale pendant que le fetch async des couleurs est encore en vol.
      const colorButtons = finalistPage.locator('div.card.max-w-lg .flex-wrap button');
      await expect(colorButtons.first()).toBeVisible({ timeout: 10_000 });
      await colorButtons.first().click();

      // 3 premiers thèmes disponibles.
      const themeButtons = finalistPage.locator('div.card.max-w-lg .grid button');
      await expect(themeButtons.first()).toBeVisible({ timeout: 10_000 });
      for (let i = 0; i < 3; i++) {
        await themeButtons.nth(i).click();
      }

      await finalistPage.getByRole('button', { name: 'Valider' }).click();
      await expect(finalistPage.locator('h3:has-text("Setup de")')).not.toBeVisible({ timeout: 10_000 });
    }

    // Tous les finalistes prêts -> l'hôte crée/démarre la grille automatiquement
    // (polling côté host), les finalistes la rejoignent en attente (waitingForGrid).
    await expect(page.locator('text=Manche 3 — Grille Mémoire')).toBeVisible({ timeout: 20_000 });
    for (const { page: finalistPage } of finalistContexts) {
      await expect(finalistPage.locator('text=Manche 3 — Grille Mémoire')).toBeVisible({ timeout: 20_000 });
    }

    // ============================================================
    // Phase de mémorisation (playtest 2026-08-15) : la grille complète
    // (couleurs par propriétaire) doit être visible sur CHAQUE appareil avant
    // de se cacher — MEMORY_GRID_MEMORIZE_SECONDS doit être réduite côté
    // backend pour ce test (120s réelles sinon), voir DEPLOY/CI.
    // ============================================================
    await expect(page.locator('text=Mémorisez la grille')).toBeVisible({ timeout: 10_000 });
    for (const { page: finalistPage } of finalistContexts) {
      await expect(finalistPage.locator('text=Mémorisez la grille')).toBeVisible({ timeout: 10_000 });
    }
    await expect(page.locator('text=Mémorisez la grille')).not.toBeVisible({ timeout: 30_000 });
    for (const { page: finalistPage } of finalistContexts) {
      await expect(finalistPage.locator('text=Mémorisez la grille')).not.toBeVisible({ timeout: 30_000 });
    }

    // ============================================================
    // Boucle de jeu : à chaque itération, on interroge le serveur pour savoir
    // à qui est le tour, et on agit UNIQUEMENT depuis l'appareil de ce
    // finaliste — un autre appareil ne doit pas pouvoir jouer à sa place.
    // ============================================================
    const stateRes = await request.get(`/api/games/${code}/memory-grid/state`);
    expect(stateRes.ok(), await stateRes.text()).toBeTruthy();
    const gridId: number = (await stateRes.json()).memory_grid.id;

    const CELLS_TO_PLAY = 6; // échantillon suffisant pour valider le flux réel sans 35 tours complets
    let previousProgress = -1;
    for (let i = 0; i < CELLS_TO_PLAY; i++) {
      const turnRes = await request.get(`/api/memory-grid/${gridId}/current-player-turn`);
      expect(turnRes.ok(), await turnRes.text()).toBeTruthy();
      const { current_player_id: currentPlayerId } = await turnRes.json();

      const actor = finalistContexts[finalistIds.indexOf(currentPlayerId)];
      expect(actor, `aucun contexte ouvert pour le joueur ${currentPlayerId}`).toBeTruthy();
      const actingPage = actor.page;

      // Chaque client ne rafraîchit son état que toutes les 2s (polling,
      // C-003 AC4) — on laisse le temps à SON appareil de rattraper le tour
      // désigné par le serveur (interrogé juste au-dessus en temps réel)
      // avant de vérifier quoi que ce soit dépendant de currentPlayerId.
      await actingPage.waitForTimeout(2_500);

      // Les 3 AUTRES finalistes ne doivent voir aucune case cliquable tant
      // que ce n'est pas leur tour (myPlayerId !== currentPlayerId).
      for (const { page: otherPage } of finalistContexts) {
        if (otherPage === actingPage) continue;
        const enabledCells = otherPage.locator('div.grid.gap-2 button:not([disabled])');
        expect(await enabledCells.count()).toBe(0);
      }

      await expect(actingPage.locator('text=/Progression: \\d+\\/35/')).toBeVisible({ timeout: 15_000 });
      const cell = actingPage.getByRole('button', { name: '?', exact: true }).first();
      if (!(await cell.isVisible({ timeout: 5_000 }).catch(() => false))) break;
      await expect(cell).toBeEnabled({ timeout: 10_000 });

      await cell.click();
      await expect(actingPage.locator('h3:has-text("Cellule révélée !")')).toBeVisible({ timeout: 10_000 });

      // Playtest 2026-08-15 : le timer de réponse (60s) doit apparaître dans
      // la modale dès que la question est visible — pas avant.
      await expect(actingPage.locator('text=/⏱ \\d+s/').first()).toBeVisible({ timeout: 5_000 });

      await actingPage.fill('input[placeholder="Saisir la réponse..."]', 'réponse de test');
      await actingPage.click('button:has-text("Valider la réponse")');

      await expect(actingPage.locator('h3:has-text("Cellule révélée !")')).not.toBeVisible({ timeout: 10_000 });

      const progressText = await actingPage.locator('text=/Progression: \\d+\\/35/').textContent();
      const match = progressText?.match(/Progression: (\d+)\/35/);
      const currentProgress = match ? parseInt(match[1], 10) : previousProgress;
      expect(currentProgress).toBeGreaterThan(previousProgress);
      previousProgress = currentProgress;
    }

    for (const { context } of finalistContexts) {
      await context.close();
    }
  });
});
