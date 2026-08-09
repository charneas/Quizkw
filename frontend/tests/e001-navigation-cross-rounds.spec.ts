import { test, expect, type APIRequestContext } from '@playwright/test';

/**
 * E2E navigation cross-rounds — story E-001.
 *
 * Avant cette story, l'écran équipe (`TeamScreen.tsx`, route `/team/:code/:teamId`)
 * n'avait aucune détection de changement de phase : seul l'hôte, en cliquant sur son
 * propre écran, se déplaçait vers `/round2`. Un vrai joueur sur son propre appareil
 * restait bloqué sur l'écran Manche 1 même une fois la partie qualifiée pour la
 * Manche 2. Ce test vérifie que l'écran équipe détecte la transition côté serveur
 * (`game_phase` renvoyé par `/game/{code}/team/{teamId}/state`, dérivé de
 * `GameSession.current_round`, AD-8) et redirige automatiquement, avec un écran
 * d'explication (AC #4) plutôt qu'une navigation silencieuse.
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api par le
 * serveur de dev Vite) — playwright.config.ts ne démarre que le frontend.
 */

async function createGameWithTeam(request: APIRequestContext): Promise<{ code: string; teamId: number; hostToken: string }> {
  const gameRes = await request.post('/api/games/', {
    data: { total_players: 4, players_per_team: 2 },
  });
  expect(gameRes.ok(), await gameRes.text()).toBeTruthy();
  const gameBody = await gameRes.json();
  const code = gameBody.game.code as string;
  const hostHeaders = { 'X-Host-Token': gameBody.host_token as string };

  const teamRes = await request.post(`/api/games/${code}/teams/`, {
    data: { name: 'Équipe Test' },
  });
  expect(teamRes.ok(), await teamRes.text()).toBeTruthy();
  const teamId = (await teamRes.json()).id as number;

  // Deuxième équipe requise par /start (au moins 2 équipes).
  const secondTeamRes = await request.post(`/api/games/${code}/teams/`, {
    data: { name: 'Équipe Adverse' },
  });
  expect(secondTeamRes.ok(), await secondTeamRes.text()).toBeTruthy();
  const secondTeamId = (await secondTeamRes.json()).id as number;

  // BUG-201 : /start n'auto-remplit plus les joueurs manquants — chaque
  // équipe doit avoir son quota réel (players_per_team=2 ici). Le vrai point
  // d'entrée du pseudo est /teams/{team_id}/players/ (join_team), pas
  // /players/ (create_player, réservé à la Manche 2 individuelle, qui
  // ignore bien team_id — bug préexistant documenté dans deferred-work.md,
  // non concerné ici).
  for (const [tid, names] of [[teamId, ['J1', 'J2']], [secondTeamId, ['J3', 'J4']]] as const) {
    for (const name of names) {
      const playerRes = await request.post(`/api/games/${code}/teams/${tid}/players/`, { data: { name } });
      expect(playerRes.ok(), await playerRes.text()).toBeTruthy();
    }
  }

  const startRes = await request.post(`/api/games/${code}/start`, { headers: hostHeaders });
  expect(startRes.ok(), await startRes.text()).toBeTruthy();

  return { code, teamId, hostToken: gameBody.host_token as string };
}

test.describe('E-001 — Navigation cross-rounds', () => {
  test('une équipe sur son propre écran est redirigée automatiquement quand la Manche 1 se termine', async ({ page, request }) => {
    const { code, teamId, hostToken } = await createGameWithTeam(request);

    await page.goto(`/team/${code}/${teamId}`);
    await expect(page.locator('text=Équipe Test')).toBeVisible({ timeout: 10_000 });

    // Simule la fin de la Manche 1 côté serveur (qualification réelle, H-007) sans
    // passer par le clic hôte — c'est exactement le scénario que E-001 corrige :
    // le changement de phase doit être détecté par CE navigateur tout seul.
    const qualifyRes = await request.post(`/api/games/${code}/qualify-round2`, {
      headers: { 'X-Host-Token': hostToken },
    });
    expect(qualifyRes.ok(), await qualifyRes.text()).toBeTruthy();

    // L'écran d'explication apparaît avant la redirection (AC #4).
    await expect(page.locator('text=Manche 1 terminée !')).toBeVisible({ timeout: 5_000 });

    // Puis la redirection automatique a bien lieu (AC #1).
    await page.waitForURL(new RegExp(`/game/${code}/round2`), { timeout: 5_000 });
  });
});
