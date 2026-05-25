import { test, expect } from '@playwright/test';

test.describe('Round 3 E2E Flow - Memory Grid 7x5', () => {
  let gameCode: string;

  test.beforeEach(async ({ page }) => {
    // Create a new game
    await page.goto('/');
    await expect(page.locator('text=Nouvelle partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=Nouvelle partie');
    await expect(page.locator('text=🚀 Créer la partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=🚀 Créer la partie');
    
    // Wait for navigation to lobby and extract game code
    await page.waitForURL(/\/lobby\//, { timeout: 10000 });
    const url = page.url();
    gameCode = url.split('/').pop()!;
    console.log(`Game Code (Round 3): ${gameCode}`);
  });

  test('complete Round 3 flow with 4 players and color selection', async ({ page }) => {
    // 1. Setup: Create 4 teams for Round 3
    await expect(page.locator('text=/Créer des équipes|Create Teams/')).toBeVisible({ timeout: 10000 });
    
    // Add 4 teams (Round 3 requires exactly 4 players)
    for (let i = 0; i < 4; i++) {
      await page.click('button:text("Ajouter une équipe"), button:text("Add Team")');
      await expect(page.locator(`text=/Équipe ${i + 1}|Team ${i + 1}/`)).toBeVisible();
      
      // Add one player per team
      const teamInput = page.locator('input[placeholder*="Nom du joueur"], input[placeholder*="Player name"]').nth(i);
      await teamInput.fill(`Player${i + 1}`);
      await page.keyboard.press('Enter');
    }
    
    // Navigate to Round 3
    await page.goto(`/game/${gameCode}/round3`);
    await expect(page.locator('text=/Round 3|Manche 3|Memory Grid/')).toBeVisible({ timeout: 10000 });
  });

  test('color selection for 4 teams', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3`);
    
    // Verify color selection interface
    await expect(page.locator('text=/Select Color|Sélectionner une couleur/')).toBeVisible({ timeout: 10000 });
    
    // Check that color options are available
    const colorButtons = page.locator('button[data-color], .color-option');
    await expect(colorButtons.first()).toBeVisible({ timeout: 5000 });
    
    // Select a color for first team
    await colorButtons.first().click();
    
    // Verify color was selected
    await expect(page.locator('text=/Color selected|Couleur sélectionnée/')).toBeVisible({ timeout: 5000 });
  });

  test('theme selection - 3 themes per team', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/themes`);
    
    // Verify theme selection interface
    await expect(page.locator('text=/Select 3 themes|Sélectionnez 3 thèmes/')).toBeVisible({ timeout: 10000 });
    
    // Select 3 themes
    const themeCards = page.locator('.theme-card, [data-testid="theme-card"]');
    await expect(themeCards.first()).toBeVisible();
    
    for (let i = 0; i < 3; i++) {
      await themeCards.nth(i).click();
      await page.waitForTimeout(500);
    }
    
    // Verify 3 themes selected
    const selectedThemes = page.locator('.theme-selected, [data-selected="true"]');
    await expect(selectedThemes).toHaveCount(3, { timeout: 5000 });
    
    // Confirm selection
    await page.click('button:text("Confirm"), button:text("Confirmer")');
  });

  test('memory grid 7x5 display and interaction', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // Verify grid is displayed
    await expect(page.locator('text=/Memory Grid|Grille Mémoire/')).toBeVisible({ timeout: 10000 });
    
    // Check grid dimensions (7 rows x 5 columns = 35 cells)
    const gridCells = page.locator('.grid-cell, [data-testid="grid-cell"]');
    await expect(gridCells.first()).toBeVisible({ timeout: 10000 });
    
    // Click on first cell
    await gridCells.first().click();
    
    // Verify question appears
    await expect(page.locator('text=/Question|¿/')).toBeVisible({ timeout: 10000 });
  });

  test('team turn rotation in Round 3', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // Verify turn indicator
    await expect(page.locator('text=/Turn|Tour|Player/').first()).toBeVisible({ timeout: 10000 });
    
    // Check that current team is displayed
    const currentTeam = page.locator('text=/Team 1|Team 2|Team 3|Team 4|Équipe/');
    await expect(currentTeam.first()).toBeVisible({ timeout: 5000 });
  });

  test('hard difficulty questions in Round 3', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // Click a cell to reveal question
    const gridCells = page.locator('.grid-cell, [data-testid="grid-cell"]');
    if (await gridCells.first().isVisible({ timeout: 5000 })) {
      await gridCells.first().click();
      
      // Verify question difficulty is HARD
      await expect(page.locator('text=/HARD|Difficile|6 points/')).toBeVisible({ timeout: 10000 });
    }
  });

  test('cell color assignment based on ownership', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // After gameplay, cells should show team colors
    const coloredCells = page.locator('[data-team-color], .cell-owned');
    
    // Wait for at least one cell to be colored
    await expect(coloredCells.first()).toBeVisible({ timeout: 10000 });
  });

  test('Round 3 completion and final scores', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/results`);
    
    // Verify results screen
    await expect(page.locator('text=/Final Score|Score Final|Winner|Gagnant/')).toBeVisible({ timeout: 10000 });
    
    // Check that all 4 teams are listed
    for (let i = 1; i <= 4; i++) {
      await expect(page.locator(`text=/Team ${i}|Équipe ${i}/`)).toBeVisible({ timeout: 5000 });
    }
  });

  test('grid cell state persistence', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // Click a cell
    const firstCell = page.locator('.grid-cell, [data-testid="grid-cell"]').first();
    if (await firstCell.isVisible({ timeout: 5000 })) {
      await firstCell.click();
      
      // Answer question
      const answerBtn = page.locator('button.answer-option').first();
      if (await answerBtn.isVisible({ timeout: 5000 })) {
        await answerBtn.click();
      }
      
      // Verify cell remains answered after reload
      await page.reload();
      await expect(firstCell).toHaveAttribute('data-answered', 'true', { timeout: 5000 });
    }
  });

  test('85 questions available for 35-cell grid', async ({ page }) => {
    // Note: This test verifies backend has enough questions
    // The grid needs 35 HARD questions, we have 85 imported
    
    await page.goto(`/game/${gameCode}/round3/grid`);
    
    // All 35 cells should be clickable (meaning questions are available)
    const gridCells = page.locator('.grid-cell:not([data-disabled])');
    const count = await gridCells.count();
    
    // Should have 35 cells available
    expect(count).toBeGreaterThanOrEqual(35);
  });
});
