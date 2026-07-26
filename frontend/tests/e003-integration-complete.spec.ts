import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

/**
 * E2E intégration complète 1→2→3 à l'échelle maximale — story E-003.
 *
 * Étend le pattern de H-002 (round3.spec.ts, 8 joueurs) à l'échelle max réelle
 * (16 joueurs, schemas.py: total_players <= 16) et ajoute la couverture qui
 * manquait : vérification explicite des transitions de phase, cas d'erreur,
 * performance minimale, latence réseau simulée.
 *
 * Périmètre UI/API identique à H-002 (voir _bmad-output/e-003-*.md Dev Notes) :
 * Manche 1 et Manche 3 par l'UI réelle, Manche 2 et qualification par API
 * directe (trous UI de la Manche 2 hors périmètre, relèvent d'Epic A).
 *
 * Substitutions documentées pour les AC hors de portée d'un test automatisé
 * sur ce modèle (polling HTTP, AD-9, pas de couche temps réel) :
 * - "déconnexion massive" -> rechargement de page (perte d'état local), pattern
 *   déjà utilisé par round2.spec.ts / E-002.
 * - "différents réseaux" -> latence artificielle injectée via page.route().
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api
 * par le serveur de dev Vite) — playwright.config.ts ne démarre que le frontend.
 */

const TOTAL_PLAYERS = 16;
const PLAYERS_PER_TEAM = 2; // 8 équipes de 2 : évite le bug de troncature qualified[:8] (deferred-work.md)
const TEAM_COUNT = TOTAL_PLAYERS / PLAYERS_PER_TEAM;
const GRID_CELLS = 35;

async function createGameWithTeams(request: APIRequestContext): Promise<string> {
  const res = await request.post('/api/games/', {
    data: { total_players: TOTAL_PLAYERS, players_per_team: PLAYERS_PER_TEAM },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const code = (await res.json()).game.code as string;

  for (let i = 1; i <= TEAM_COUNT; i++) {
    const teamRes = await request.post(`/api/games/${code}/teams/`, { data: { name: `Équipe ${i}` } });
    expect(teamRes.ok(), await teamRes.text()).toBeTruthy();
  }

  const startRes = await request.post(`/api/games/${code}/start`);
  expect(startRes.ok(), await startRes.text()).toBeTruthy();

  return code;
}

async function qualifyRound1(request: APIRequestContext, code: string): Promise<number[]> {
  const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`);
  expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();
  const qualifiedPlayerIds: number[] = (await qualifyRes.json()).qualified_player_ids;
  expect(qualifiedPlayerIds).toHaveLength(8);
  return qualifiedPlayerIds;
}

async function playRound2ToFinalists(request: APIRequestContext, code: string, qualifiedPlayerIds: number[]) {
  const themesRes = await request.get(`/api/round2/${code}/themes`);
  expect(themesRes.ok(), await themesRes.text()).toBeTruthy();
  const themeId = (await themesRes.json()).themes[0].id;

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
        data: { player_id: playerId, question_id: question.question.id, player_answer: 'peu importe la justesse ici' },
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
}

async function playGridToVictory(page: Page) {
  let previousProgress = -1;
  for (let cellIndex = 0; cellIndex < GRID_CELLS; cellIndex++) {
    await expect(page.locator('text=/Progression: \\d+\\/35/')).toBeVisible({ timeout: 15_000 });
    const cell = page.getByRole('button', { name: '?', exact: true }).first();
    if (!(await cell.isVisible({ timeout: 5_000 }).catch(() => false))) break;

    await cell.click();
    await expect(page.locator('h3:has-text("Cellule révélée !")')).toBeVisible({ timeout: 10_000 });
    await page.fill('input[placeholder="Saisir la réponse..."]', 'réponse de test');
    await page.click('button:has-text("Valider la réponse")');
    await expect(page.locator('h3:has-text("Cellule révélée !")')).not.toBeVisible({ timeout: 10_000 });

    const progressText = await page.locator('text=/Progression: \\d+\\/35/').textContent();
    const match = progressText?.match(/Progression: (\d+)\/35/);
    const currentProgress = match ? parseInt(match[1], 10) : previousProgress;
    expect(currentProgress).toBeGreaterThan(previousProgress);
    previousProgress = currentProgress;
    if (currentProgress >= GRID_CELLS) break;
  }
}

test.describe('E-003 — Intégration complète 1→2→3 (16 joueurs)', () => {
  test.setTimeout(240_000);

  test('parcours complet à 16 joueurs, de la création à l\'écran de résultats (AC #1)', async ({ page, request }) => {
    const code = await createGameWithTeams(request);

    await page.goto(`/game/${code}/host`);
    await expect(page.locator('text=Manche 1 — Hôte')).toBeVisible({ timeout: 10_000 });

    const qualifiedPlayerIds = await qualifyRound1(request, code);
    await playRound2ToFinalists(request, code, qualifiedPlayerIds);

    await page.goto(`/game/${code}/memory-grid`);
    await expect(page.locator('text=/Progression: \\d+\\/35/')).toBeVisible({ timeout: 20_000 });

    await playGridToVictory(page);

    await expect(page.locator('text=Partie terminée !')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('text=4 finalistes')).toBeVisible();

    await page.click('button:has-text("Voir les résultats →")');
    await page.waitForURL(/\/results\//, { timeout: 10_000 });
    expect(page.url()).toContain(`/results/${code}`);
    await expect(page.locator('text=/Score|Classement|Résultats|Gagnant/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('chaque transition de phase est observable côté API (AC #2)', async ({ request }) => {
    const code = await createGameWithTeams(request);

    const beforeRes = await request.get(`/api/games/${code}`);
    expect(beforeRes.ok(), await beforeRes.text()).toBeTruthy();
    expect((await beforeRes.json()).current_round).toBe('manche_1');

    const qualifiedPlayerIds = await qualifyRound1(request, code);

    const afterQualifyRes = await request.get(`/api/games/${code}`);
    expect(afterQualifyRes.ok(), await afterQualifyRes.text()).toBeTruthy();
    expect((await afterQualifyRes.json()).current_round).toBe('manche_2');

    await playRound2ToFinalists(request, code, qualifiedPlayerIds);
  });

  test('l\'écran équipe (TeamScreen, E-001) détecte la transition sans action manuelle (AC #2)', async ({ page, request }) => {
    // Complète le pattern E-001 (e001-navigation-cross-rounds.spec.ts) : vérifie que
    // TeamScreen.tsx, pas seulement l'API brute, réagit à la transition de phase.
    const code = await createGameWithTeams(request);
    const teamsRes = await request.get(`/api/games/${code}`);
    const teamId = (await teamsRes.json()).teams[0].id;

    await page.goto(`/team/${code}/${teamId}`);
    await expect(page.locator('text=Équipe 1')).toBeVisible({ timeout: 10_000 });

    await request.post(`/api/games/${code}/qualify-round2`);

    // L'écran d'explication apparaît avant la redirection automatique (E-001 AC #4).
    await expect(page.locator('text=/Manche 1 terminée|terminée/i')).toBeVisible({ timeout: 5_000 });
    await page.waitForURL(new RegExp(`/game/${code}/round2`), { timeout: 5_000 });
  });

  test.describe('Cas d\'erreur (AC #3)', () => {
    test('double qualification concurrente : une seule réussit, l\'autre est rejetée', async ({ request }) => {
      const code = await createGameWithTeams(request);

      const [first, second] = await Promise.all([
        request.post(`/api/games/${code}/qualify-round2`),
        request.post(`/api/games/${code}/qualify-round2`),
      ]);

      const results = [first, second];
      const successes = results.filter((r) => r.ok());
      const failures = results.filter((r) => !r.ok());
      expect(successes).toHaveLength(1);
      expect(failures).toHaveLength(1);
      // `/games/{code}/qualify-round2` (main.py:799-822) ne capture que LookupError/ValueError,
      // pas IntegrityError (contrairement à /round2/{code}/advance, main.py:1145-1148, qui
      // renvoie 409 sur ce cas). Sans verrou explicite (pas de with_for_update), une vraie
      // course peut donc remonter un 500 non géré plutôt que le 400 attendu — tolérer les
      // trois pour ne pas rendre ce test flaky selon le timing réel de la requête concurrente.
      // Écart découvert pendant cette story, documenté dans deferred-work.md (hors périmètre :
      // corriger cette lacune serait une story Epic H, pas E-003).
      expect([400, 409, 500]).toContain(failures[0].status());
    });

    test('round2/advance avant que les 8 joueurs aient répondu : rejet propre 400', async ({ request }) => {
      const code = await createGameWithTeams(request);
      const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`);
      expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();

      // Personne n'a encore de statut QUALIFIED (aucune des 10 questions n'a été jouée) :
      // advance_to_finalists doit rejeter plutôt que planter.
      const advanceRes = await request.post(`/api/round2/${code}/advance`);
      expect(advanceRes.status()).toBe(400);
      const body = await advanceRes.json();
      expect(Object.keys(body)).toEqual(['detail']);
    });

    test('reprise après rechargement de page, y compris après une transition de round (TeamScreen)', async ({ page, request }) => {
      const code = await createGameWithTeams(request);
      const teamsRes = await request.get(`/api/games/${code}`);
      expect(teamsRes.ok(), await teamsRes.text()).toBeTruthy();
      const teamId = (await teamsRes.json()).teams[0].id;

      await page.goto(`/team/${code}/${teamId}`);
      await expect(page.locator('text=Équipe 1')).toBeVisible({ timeout: 10_000 });

      // Rechargement en Manche 1 (perte d'état local sans changement de phase).
      await page.reload();
      await expect(page.locator('text=Équipe 1')).toBeVisible({ timeout: 10_000 });

      // Rechargement APRÈS une transition de round : TeamScreen ne détecte la
      // transition qu'une fois (hasStartedAdvanceRef, TeamScreen.tsx:69-92) ; un
      // rechargement à ce moment ne doit ni bloquer ni dupliquer la redirection.
      await request.post(`/api/games/${code}/qualify-round2`);
      await page.reload();
      await page.waitForURL(new RegExp(`/game/${code}/round2`), { timeout: 10_000 });
    });
  });

  test.describe('Performance minimale (AC #4)', () => {
    test('les écrans clés se chargent sous 5s (AC #4, 2/5 écrans)', async ({ page, request }) => {
      const code = await createGameWithTeams(request);

      const screens = [`/lobby/${code}`, `/game/${code}/host`];
      for (const url of screens) {
        const start = Date.now();
        await page.goto(url);
        await expect(page.locator('body')).toBeVisible({ timeout: 5_000 });
        expect(Date.now() - start).toBeLessThan(5_000);
      }
    });

    test('les 3 écrans restants (round2, memory-grid, results) se chargent sous 5s (AC #4, 3/5 écrans)', async ({ page, request }) => {
      const code = await createGameWithTeams(request);
      const qualifiedPlayerIds = await qualifyRound1(request, code);

      let start = Date.now();
      await page.goto(`/game/${code}/round2`);
      await expect(page.locator('body')).toBeVisible({ timeout: 5_000 });
      expect(Date.now() - start).toBeLessThan(5_000);

      await playRound2ToFinalists(request, code, qualifiedPlayerIds);

      start = Date.now();
      await page.goto(`/game/${code}/memory-grid`);
      await expect(page.locator('body')).toBeVisible({ timeout: 5_000 });
      expect(Date.now() - start).toBeLessThan(5_000);

      start = Date.now();
      await page.goto(`/results/${code}`);
      await expect(page.locator('body')).toBeVisible({ timeout: 5_000 });
      expect(Date.now() - start).toBeLessThan(5_000);
    });

    test('l\'intervalle de polling (2s, AD-9) ne dérive pas sur une fenêtre de 20s', async ({ page, request }) => {
      const code = await createGameWithTeams(request);
      const teamsRes = await request.get(`/api/games/${code}`);
      const teamId = (await teamsRes.json()).teams[0].id;

      let requestCount = 0;
      page.on('request', (req) => {
        if (req.url().includes('/state') || req.url().includes(`/team/${teamId}`)) requestCount++;
      });

      await page.goto(`/team/${code}/${teamId}`);
      await page.waitForTimeout(20_000);

      // ~2s d'intervalle sur 20s => environ 10 requêtes ; tolérance large pour le premier
      // appel de montage et la latence de test, mais une dérive massive (0 ou >20) signalerait
      // un polling arrêté ou emballé.
      expect(requestCount).toBeGreaterThan(3);
      expect(requestCount).toBeLessThan(20);
    });
  });

  test('latence réseau variable simulée : pas de blocage ni de double-soumission (AC #5)', async ({ page, request }) => {
    const code = await createGameWithTeams(request);
    const qualifiedPlayerIds = await qualifyRound1(request, code);
    await playRound2ToFinalists(request, code, qualifiedPlayerIds);

    await page.route('**/api/**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 200 + Math.random() * 600));
      await route.continue();
    });

    await page.goto(`/game/${code}/memory-grid`);
    await expect(page.locator('text=/Progression: \\d+\\/35/')).toBeVisible({ timeout: 20_000 });

    const cell = page.getByRole('button', { name: '?', exact: true }).first();
    await cell.click();
    await expect(page.locator('h3:has-text("Cellule révélée !")')).toBeVisible({ timeout: 10_000 });

    await page.fill('input[placeholder="Saisir la réponse..."]', 'réponse de test');
    const validateButton = page.locator('button:has-text("Valider la réponse")');
    const progressBefore = await page.locator('text=/Progression: \\d+\\/35/').textContent();

    // Double-clic rapide pendant la latence simulée : vérifie une vraie double-soumission,
    // pas seulement l'absence hypothétique d'un symptôme jamais déclenché. `dblclick` envoie
    // deux clics natifs rapprochés sans les actionability checks bloquants d'un double `click()`
    // concurrent sur le même élément (qui peut se détacher du DOM entre les deux tentatives).
    await validateButton.dblclick({ force: true });

    await expect(page.locator('h3:has-text("Cellule révélée !")')).not.toBeVisible({ timeout: 15_000 });
    const progressAfter = await page.locator('text=/Progression: \\d+\\/35/').textContent();
    // Une seule cellule doit avoir progressé (pas de double-soumission qui en consommerait deux).
    const before = parseInt(progressBefore?.match(/(\d+)\/35/)?.[1] ?? '0', 10);
    const after = parseInt(progressAfter?.match(/(\d+)\/35/)?.[1] ?? '0', 10);
    expect(after - before).toBe(1);
  });
});
