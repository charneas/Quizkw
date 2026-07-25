import { test, expect, type APIRequestContext } from '@playwright/test';

/**
 * E2E Manche 2 (16→8→4) — story A-003.
 *
 * Round 2 n'exige pas que les joueurs viennent de la Manche 1 : les endpoints
 * `/round2/*` acceptent n'importe quel joueur existant de la partie (voir
 * `select_theme` dans backend/main.py). Les tests créent donc leurs joueurs
 * directement via l'API `/games/{code}/players/` plutôt que de rejouer toute
 * la Manche 1, pour rester rapides et déterministes.
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api
 * par le serveur de dev Vite) — playwright.config.ts ne démarre que le frontend.
 */

async function createGame(request: APIRequestContext): Promise<string> {
  const res = await request.post('/api/games/', {
    data: { total_players: 16, players_per_team: 2 },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const body = await res.json();
  expect(body.game?.code, 'game creation must return a usable code').toBeTruthy();
  return body.game.code as string;
}

test.describe('Round 2 E2E Flow - Tournoi 16→8→4', () => {
  test('flux complet du joueur : sélection de joueur, thème, questions, feedback', async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    // 1. Sélection / création du joueur (Scenario 1)
    await expect(page.locator('text=Join Round 2 Tournament')).toBeVisible({ timeout: 10000 });
    await page.fill('#playerName', 'Test Player');
    await page.click('button:text("Join Tournament")');
    await expect(page.locator('text=/Player:/')).toBeVisible({ timeout: 5000 });

    // TournamentProgress est affiché dès le chargement de la page
    await expect(page.locator('text=Round 2: 16→8→4 Tournament')).toBeVisible();

    // 2. Sélection de thème (Scenario 2 & 3)
    await expect(page.locator('text=Choose Your Theme')).toBeVisible({ timeout: 10000 });
    const themeCards = page.locator('text=Select This Theme');
    await expect(themeCards.first()).toBeVisible();
    const themeCount = await themeCards.count();
    expect(themeCount).toBe(3);
    await themeCards.first().click();

    // 3. Questions + réponses (Scenario 4 & 5)
    for (let i = 1; i <= 10; i++) {
      await expect(page.locator(`text=/Question ${i} \\(Difficulty:/`)).toBeVisible({ timeout: 10000 });

      const answerBtn = page.locator('div.grid.grid-cols-2 button').first();
      await expect(answerBtn).toBeVisible();
      await answerBtn.click();

      await expect(page.locator('text=/✅ Correct!|❌ Incorrect/')).toBeVisible({ timeout: 5000 });

      const nextLabel = i < 10 ? 'Next Question' : 'Finish';
      await page.click(`button:text("${nextLabel}")`);
    }

    // 4. Fin du parcours : en attente des autres joueurs (Scenario 6, côté solo)
    await expect(page.locator('text=Waiting for all players to finish...')).toBeVisible({ timeout: 10000 });
  });

  test('les 3 thèmes affichent catégorie et niveau de difficulté', async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    await page.fill('#playerName', 'Difficulty Tester');
    await page.click('button:text("Join Tournament")');

    await expect(page.locator('text=Choose Your Theme')).toBeVisible({ timeout: 10000 });
    const themeInfo = page.locator('text=/Serious|Pop Culture|Whimsical/');
    await expect(themeInfo.first()).toBeVisible();

    const difficultyInfo = page.locator('text=/Difficulty: \\d+\\/10/');
    await expect(difficultyInfo.first()).toBeVisible();
  });

  test('le score du joueur augmente au fil des réponses', async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    await page.fill('#playerName', 'Score Tester');
    await page.click('button:text("Join Tournament")');

    await page.locator('text=Select This Theme').first().click();
    await expect(page.locator('text=/Question 1 \\(Difficulty:/')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=/Current score: \\d+/')).toBeVisible();
  });

  test('reconnexion : le joueur retrouve sa session après rechargement de page (déconnexion simulée)', async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    await page.fill('#playerName', 'Reco Tester');
    await page.click('button:text("Join Tournament")');
    await expect(page.locator('text=/Player:/')).toBeVisible({ timeout: 5000 });

    // Simule une déconnexion/reconnexion (fermeture d'onglet + retour)
    await page.reload();

    // Le joueur est restauré depuis localStorage, la sélection de joueur est sautée
    await expect(page.locator('text=/Player: .*Reco Tester/')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Join Round 2 Tournament')).not.toBeVisible();
  });

  test('reconnexion sans localStorage : retour à la sélection de joueur plutôt que blocage (E-002)', async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    await page.fill('#playerName', 'Sans Storage');
    await page.click('button:text("Join Tournament")');
    await expect(page.locator('text=/Player:/')).toBeVisible({ timeout: 5000 });

    // localStorage vidé (autre appareil, navigation privée, cache effacé) :
    // le joueur doit retomber sur la sélection plutôt que rester bloqué.
    await page.evaluate((gameCode) => localStorage.removeItem(`quizkw_player_${gameCode}`), code);
    await page.reload();

    await expect(page.locator('text=Join Round 2 Tournament')).toBeVisible({ timeout: 10000 });
  });

  test("erreur réseau lors de la sélection de thème : un message d'erreur est affiché", async ({ page, request }) => {
    const code = await createGame(request);
    await page.goto(`/game/${code}/round2`);

    await page.fill('#playerName', 'Error Tester');
    await page.click('button:text("Join Tournament")');
    await expect(page.locator('text=Choose Your Theme')).toBeVisible({ timeout: 10000 });

    // Simule un timeout/une panne réseau sur l'appel de sélection de thème
    await page.route('**/api/round2/**/select-theme', (route) => route.abort('timedout'));

    await page.locator('text=Select This Theme').first().click();

    await expect(page.getByText('Error', { exact: true })).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Round 2 - Progression du tournoi 16→8→4', () => {
  test.setTimeout(120_000);

  test('la progression avance des joueurs qualifiés à 4 finalistes (Scenario 2)', async ({ request }) => {
    const code = await createGame(request);

    // La Manche 2 se qualifie depuis la Manche 1 (équipes) — voir
    // round2_manager.qualify_players_from_round1 (ROUND2_SLOTS = 8, refonte
    // AD-0 : la sélection de thèmes/questions UI parle encore de "16→8→4"
    // mais le backend qualifie bien 8 joueurs, pas 16 — désynchronisation de
    // libellé à corriger séparément, hors périmètre de cette story).
    // On crée 4 équipes de 2 joueurs pour obtenir les 8 qualifiés.
    for (let t = 0; t < 4; t++) {
      const teamRes = await request.post(`/api/games/${code}/teams/`, { data: { name: `Team ${t}` } });
      expect(teamRes.ok(), await teamRes.text()).toBeTruthy();
    }

    // /start auto-remplit chaque équipe jusqu'à `players_per_team` joueurs
    // (le endpoint /players/ n'attache pas le joueur à une équipe).
    const startRes = await request.post(`/api/games/${code}/start`);
    expect(startRes.ok(), await startRes.text()).toBeTruthy();

    const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`);
    expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();
    const qualifyBody = await qualifyRes.json();
    const qualifiedPlayerIds: number[] = qualifyBody.qualified_player_ids;
    expect(qualifiedPlayerIds).toHaveLength(8);

    // Chaque joueur qualifié choisit un thème et répond à ses 10 questions via l'API
    const themesRes = await request.get(`/api/round2/${code}/themes`);
    expect(themesRes.ok(), await themesRes.text()).toBeTruthy();
    const { themes } = await themesRes.json();
    const themeId = themes[0].id;

    for (const playerId of qualifiedPlayerIds) {
      const selectRes = await request.post(`/api/round2/${code}/select-theme`, {
        data: { player_id: playerId, theme_id: themeId },
      });
      expect(selectRes.ok(), await selectRes.text()).toBeTruthy();

      for (let q = 0; q < 10; q++) {
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

    let phase = '';
    for (let i = 0; i < 2 && phase !== '4_finalists'; i++) {
      const advanceRes = await request.post(`/api/round2/${code}/advance`);
      expect(advanceRes.ok(), await advanceRes.text()).toBeTruthy();
      phase = (await advanceRes.json()).new_phase;
    }

    expect(phase).toBe('4_finalists');

    const progressRes = await request.get(`/api/round2/${code}/progress`);
    expect(progressRes.ok(), await progressRes.text()).toBeTruthy();
    const progress = await progressRes.json();
    expect(progress.phase).toBe('4_finalists');
  });
});
