import { test, expect } from '@playwright/test';

test.describe('Round 1 E2E Flow - Classic Quiz', () => {
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
    console.log(`Game Code: ${gameCode}`);
  });

  test('complete Round 1 flow with team creation and gameplay', async ({ page, context }) => {
    // 1. Host adds teams and players
    await expect(page.locator('text=Créer des équipes')).toBeVisible({ timeout: 10000 });
    
    // Add first team
    await page.click('button:text("Ajouter une équipe")');
    await expect(page.locator('text=Équipe 1')).toBeVisible();
    
    // Add players to first team
    const team1Input = page.locator('input[placeholder*="Nom du joueur"]').first();
    await team1Input.fill('Alice');
    await page.keyboard.press('Enter');
    
    await team1Input.fill('Bob');
    await page.keyboard.press('Enter');
    
    // Add second team
    await page.click('button:text("Ajouter une équipe")');
    await expect(page.locator('text=Équipe 2')).toBeVisible();
    
    // Add players to second team
    const team2Input = page.locator('input[placeholder*="Nom du joueur"]').nth(1);
    await team2Input.fill('Charlie');
    await page.keyboard.press('Enter');
    
    await team2Input.fill('Diana');
    await page.keyboard.press('Enter');
    
    // Start the game
    await page.click('button:text("Démarrer la partie")');
    await page.waitForURL(/\/game\//);
    
    // 2. Play through several questions
    for (let i = 0; i < 5; i++) {
      // Wait for question to be visible
      await expect(page.locator('text=/Question \\d+/')).toBeVisible({ timeout: 10000 });
      
      // Select first answer
      const firstAnswer = page.locator('button.answer-button, .answer-option').first();
      await expect(firstAnswer).toBeVisible();
      await firstAnswer.click();
      
      // Wait for feedback
      await expect(page.locator('text=/Correct|Incorrect|Bonne réponse|Mauvaise réponse/')).toBeVisible({ timeout: 5000 });
      
      // Click next question button
      await page.click('button:text("Question suivante"), button:text("Next")');
      await page.waitForTimeout(500);
    }
    
    // 3. Verify scoreboard is visible
    await expect(page.locator('text=/Score|Classement/')).toBeVisible({ timeout: 10000 });
  });

  test('token usage during Round 1', async ({ page }) => {
    // Skip to game (simplified setup)
    await page.goto(`/game/${gameCode}`);
    
    // Verify tokens panel is visible
    await expect(page.locator('text=/Jetons|Tokens/')).toBeVisible({ timeout: 10000 });
    
    // Check that token buttons are present
    const tokenButtons = page.locator('button[data-testid*="token"], button:has-text("Swap"), button:has-text("Joker")');
    await expect(tokenButtons.first()).toBeVisible();
  });

  test('intermediate leaderboard display', async ({ page }) => {
    await page.goto(`/game/${gameCode}`);
    
    // Answer enough questions to trigger intermediate leaderboard
    for (let i = 0; i < 10; i++) {
      const question = page.locator('text=/Question/');
      if (await question.isVisible({ timeout: 2000 })) {
        await page.locator('button.answer-button, .answer-option').first().click({ timeout: 5000 });
        await page.waitForTimeout(500);
        
        const nextBtn = page.locator('button:text("Question suivante"), button:text("Next")');
        if (await nextBtn.isVisible({ timeout: 2000 })) {
          await nextBtn.click();
        }
      } else {
        break;
      }
    }
    
    // Check for leaderboard
    const leaderboard = page.locator('text=/Classement|Leaderboard|Score/');
    await expect(leaderboard).toBeVisible({ timeout: 10000 });
  });
});
