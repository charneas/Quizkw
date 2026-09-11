import { test, expect } from '@playwright/test';

/**
 * E2E "File d'attente publique" (spec-rooms-publiques, story 1).
 *
 * Parcours complet par l'UI réelle : 4 contextes de navigateur distincts
 * (inconnus, jamais de code partagé au départ) rejoignent la file publique
 * depuis l'accueil, sont assemblés automatiquement à 4, la partie démarre
 * sans host_token, puis un 5e joueur qui rejoint après coup atterrit dans
 * une nouvelle file distincte.
 *
 * Prérequis : le backend FastAPI doit tourner en parallèle (proxié via /api
 * par le serveur de dev Vite) — playwright.config.ts ne démarre que le
 * frontend.
 */

const PLAYER_COUNT = 4;

test.describe('File d\'attente publique (E2E réel)', () => {
  test.setTimeout(120_000);

  test('4 inconnus rejoignent la file publique, sont assemblés auto, et un 5e atterrit dans une nouvelle file', async ({ browser }) => {
    // ============================================================
    // 4 contextes distincts (chacun représente un inconnu séparé, sans
    // localStorage partagé) rejoignent la file publique sans code.
    // ============================================================
    const contexts = await Promise.all(
      Array.from({ length: PLAYER_COUNT }, () => browser.newContext())
    );
    const pages = await Promise.all(contexts.map((c) => c.newPage()));

    let sharedCode: string | null = null;

    for (let i = 0; i < PLAYER_COUNT; i++) {
      const page = pages[i];
      await page.goto('/');
      await page.fill('input[placeholder="Ton pseudo"]', `Inconnu ${i + 1}`);
      await page.click('button:has-text("Jouer avec des inconnus")');
      await page.waitForURL(/\/public-queue\//, { timeout: 10_000 });

      const code = page.url().split('/').pop()!;
      if (sharedCode === null) {
        sharedCode = code;
      } else {
        // Les 4 joueurs doivent atterrir dans la MÊME file (CAP-2).
        expect(code).toBe(sharedCode);
      }

      // Le code de partie n'est jamais affiché tant que started=False.
      await expect(page.locator(`text=${code}`)).toHaveCount(0);
    }

    // ============================================================
    // Démarrage automatique au 4e : chaque contexte doit être redirigé vers
    // le lobby (le code y est révélé) sans intervention d'un host_token.
    // ============================================================
    for (const page of pages) {
      await page.waitForURL(/\/lobby\//, { timeout: 15_000 });
      await expect(page.locator(`text=${sharedCode}`).first()).toBeVisible({ timeout: 10_000 });
    }

    // ============================================================
    // Un 5e joueur qui rejoint après l'assemblage atterrit dans une
    // nouvelle file distincte (CAP-4), jamais dans celle déjà démarrée.
    // ============================================================
    const fifthContext = await browser.newContext();
    const fifthPage = await fifthContext.newPage();
    await fifthPage.goto('/');
    await fifthPage.fill('input[placeholder="Ton pseudo"]', 'Inconnu 5');
    await fifthPage.click('button:has-text("Jouer avec des inconnus")');
    await fifthPage.waitForURL(/\/public-queue\//, { timeout: 10_000 });
    const fifthCode = fifthPage.url().split('/').pop()!;
    expect(fifthCode).not.toBe(sharedCode);

    await fifthContext.close();
    for (const context of contexts) {
      await context.close();
    }
  });
});
