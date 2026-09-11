import { test, expect } from '@playwright/test';

/**
 * E2E "Manche 3 directe" (spec-manche-3-seule, story 1).
 *
 * Parcours complet par l'UI réelle : checkbox à la création, 4 joins en
 * équipe-de-1, refus du 5e, démarrage direct en Manche 3, sélection de
 * thèmes par les 4 joueurs (chacun sur son propre appareil, comme
 * round3.spec.ts), classement final.
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api
 * par le serveur de dev Vite) — playwright.config.ts ne démarre que le
 * frontend.
 */

const PLAYER_COUNT = 4;

test.describe('Manche 3 directe (E2E réel)', () => {
  test.setTimeout(180_000);

  test('4 joueurs créent une partie Manche 3 directe et vont jusqu\'au classement final', async ({ page, request, browser }) => {
    // ============================================================
    // Création de partie avec la checkbox "Manche 3 directe"
    // ============================================================
    await page.goto('/');
    await page.click('button:has-text("Nouvelle partie")');
    await page.click('text=🏁 Manche 3 directe');

    // Les sélecteurs solo/duo/trio et le total de joueurs disparaissent au
    // profit du badge fixe.
    await expect(page.locator('text=4 joueurs, chacun pour soi')).toBeVisible({ timeout: 5_000 });

    await page.click('button:has-text("🚀 Créer la partie")');
    await page.waitForURL(/\/lobby\//, { timeout: 10_000 });
    const code = page.url().split('/').pop()!;

    // ============================================================
    // 4 joins en équipe-de-1
    // ============================================================
    for (let i = 1; i <= PLAYER_COUNT; i++) {
      await page.fill('input[placeholder="Nom de l\'équipe"]', `Solo ${i}`);
      await page.click('button:has-text("Ajouter")');
      await expect(page.locator(`text=Solo ${i}`)).toBeVisible({ timeout: 5_000 });

      const teamCard = page.locator('div.bg-surface-raised', { hasText: `Solo ${i}` });
      await teamCard.locator('input[placeholder="Votre pseudo"]').fill(`Joueur ${i}`);
      await teamCard.locator('button:has-text("Rejoindre cette équipe")').click();
      await expect(teamCard.locator(`text=Joueur ${i}`)).toBeVisible({ timeout: 5_000 });
    }

    // Refus du 5e joueur : la partie est déjà à 4/4 (total_players=4 forcé
    // côté backend), plus aucun bouton "Ajouter une équipe" disponible ou
    // rejeté par le backend si on force l'appel.
    const fifthTeamRes = await request.post(`/api/games/${code}/teams/`, { data: { name: 'Solo 5' } });
    expect(fifthTeamRes.status()).toBe(400);

    // ============================================================
    // Démarrage : saute directement en Manche 3
    // ============================================================
    await expect(page.locator('button:has-text("🎯 Démarrer le jeu")')).toBeEnabled({ timeout: 5_000 });
    await page.click('button:has-text("🎯 Démarrer le jeu")');

    // Attendre la confirmation UI (started=true côté frontend) avant
    // d'interroger l'API : le clic ne bloque pas sur la résolution du
    // fetch, sans quoi la requête API suivante peut arriver avant le commit.
    await expect(page.locator('text=🎯 Jeu démarré !')).toBeVisible({ timeout: 10_000 });

    const gameRes = await request.get(`/api/games/${code}`);
    expect(gameRes.ok(), await gameRes.text()).toBeTruthy();
    const gameBody = await gameRes.json();
    expect(gameBody.current_round).toBe('manche_3');

    // ============================================================
    // Sélection de thèmes par les 4 joueurs, chacun sur son propre appareil
    // (comme round3.spec.ts) — le memory grid réutilise le flow existant.
    // ============================================================
    const finalistsRes = await request.get(`/api/games/${code}/memory-grid/finalists`);
    expect(finalistsRes.ok(), await finalistsRes.text()).toBeTruthy();
    const { finalists: finalistIds } = await finalistsRes.json();
    expect(finalistIds).toHaveLength(4);

    // Les 4 joins ont eu lieu dans `page` : son localStorage contient déjà
    // le vrai player_token de chacun (clé par player_id, api.ts
    // playerTokenStorageKey) — sans lui, l'API rejette en 403 "Action
    // réservée à ce joueur" même avec le bon player_id dans le payload.
    async function readPlayerToken(playerId: number): Promise<string | null> {
      return page.evaluate((id) => window.localStorage.getItem(`quizkw_player_token_${id}`), playerId);
    }

    async function openFinalistContext(playerId: number, playerToken: string) {
      const context = await browser.newContext();
      await context.addInitScript(
        ([c, id, token]) => {
          window.localStorage.setItem(`quizkw_player_${c}`, JSON.stringify({ id, name: '', team_id: null }));
          window.localStorage.setItem(`quizkw_player_token_${id}`, token);
        },
        [code, playerId, playerToken]
      );
      const finalistPage = await context.newPage();
      return { context, page: finalistPage };
    }

    const finalistContexts = await Promise.all(
      finalistIds.map(async (id: number) => {
        const token = await readPlayerToken(id);
        expect(token, `player_token manquant en localStorage pour le joueur ${id}`).toBeTruthy();
        return openFinalistContext(id, token!);
      })
    );

    await page.goto(`/game/${code}/memory-grid`);
    await expect(page.locator('text=Manche 3')).toBeVisible({ timeout: 20_000 });

    for (const { page: finalistPage } of finalistContexts) {
      await finalistPage.goto(`/game/${code}/memory-grid`);

      const configureButton = finalistPage.getByRole('button', { name: 'Configurer' });
      await expect(configureButton).toHaveCount(1, { timeout: 15_000 });
      await configureButton.click();

      await expect(finalistPage.locator('h3:has-text("Setup de")')).toBeVisible({ timeout: 10_000 });

      const colorButtons = finalistPage.locator('div.card.max-w-lg .flex-wrap button');
      await expect(colorButtons.first()).toBeVisible({ timeout: 10_000 });
      await colorButtons.first().click();

      const themeButtons = finalistPage.locator('div.card.max-w-lg .grid button');
      await expect(themeButtons.first()).toBeVisible({ timeout: 10_000 });
      for (let i = 0; i < 3; i++) {
        await themeButtons.nth(i).click();
      }

      await finalistPage.getByRole('button', { name: 'Valider' }).click();
      await expect(finalistPage.locator('h3:has-text("Setup de")')).not.toBeVisible({ timeout: 10_000 });
    }

    // ============================================================
    // La grille se crée une fois les 4 sélections faites — classement
    // final calculable ensuite via /memory-grid/standings (AC de la story).
    // ============================================================
    await expect(page.locator('text=Manche 3 — Grille Mémoire')).toBeVisible({ timeout: 20_000 });

    const standingsRes = await request.get(`/api/games/${code}/memory-grid/standings`);
    expect(standingsRes.ok(), await standingsRes.text()).toBeTruthy();

    for (const { context } of finalistContexts) {
      await context.close();
    }
  });
});
