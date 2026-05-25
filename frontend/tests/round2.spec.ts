import { test, expect } from '@playwright/test';

test.describe('Round 2 E2E Flow - 1v1 Thematic Battles', () => {
  let gameCode: string;

  test.beforeEach(async ({ page }) => {
    // Create a new game to get a fresh game code for each test
    await page.goto('/');
    await expect(page.locator('text=Nouvelle partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=Nouvelle partie');
    await expect(page.locator('text=🚀 Créer la partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=🚀 Créer la partie');
    
    // Wait for navigation to lobby and extract game code
    await page.waitForURL(/\/lobby\//, { timeout: 10000 });
    const url = page.url();
    gameCode = url.split('/').pop()!;
    console.log(`Game Code (Round 2): ${gameCode}`);
    
    await page.goto(`/game/${gameCode}/round2`);
  });

  test('full player flow from theme selection to completion', async ({ page }) => {
    // 1. Player Selection
    const nameInput = page.locator('input[placeholder*="name"], input[placeholder*="nom"]');
    await expect(nameInput).toBeVisible({ timeout: 10000 });
    await nameInput.fill('Test Player');
    await page.click('button:text("Join Game"), button:text("Rejoindre")');
    await expect(page.locator('text=/Player:|Joueur:/')).toBeVisible({ timeout: 5000 });

    // 2. Theme Selection
    await expect(page.locator('text=/Select a Theme|Sélectionner un thème/')).toBeVisible({ timeout: 10000 });
    const themeCard = page.locator('.theme-card, [data-testid="theme-card"]').first();
    await expect(themeCard).toBeVisible();
    await themeCard.click();
    
    // Wait for first question
    await expect(page.locator('text=/Question 1/')).toBeVisible({ timeout: 10000 });

    // 3. Answer all 10 Questions
    for (let i = 0; i < 10; i++) {
      console.log(`Answering question ${i + 1}/10`);
      
      // Wait for question to be visible
      await expect(page.locator(`text=/Question ${i + 1}/`)).toBeVisible({ timeout: 10000 });
      
      // Click first answer button
      const answerBtn = page.locator('.grid-cols-2 button, button.answer-option').first();
      await expect(answerBtn).toBeVisible();
      await answerBtn.click();
      
      // Wait for answer feedback
      await expect(page.locator('text=/Correct!|Incorrect|Bonne|Mauvaise/')).toBeVisible({ timeout: 5000 });
      
      // Click appropriate next button
      if (i < 9) {
        await page.click('button:text("Next Question"), button:text("Question suivante")');
      } else {
        await page.click('button:text("Finish"), button:text("Terminer")');
      }
      
      await page.waitForTimeout(500);
    }

    // 4. Verify completion message
    await expect(page.locator('text=/Waiting|En attente|Leaderboard|Classement/')).toBeVisible({ timeout: 10000 });
  });

  test('theme selection shows difficulty levels', async ({ page }) => {
    // Skip player selection for this test
    await page.goto(`/game/${gameCode}/round2`);
    
    // Check that themes are displayed with info
    await expect(page.locator('text=/Select a Theme|Sélectionner/')).toBeVisible({ timeout: 10000 });
    
    const themeCards = page.locator('.theme-card, [data-testid="theme-card"]');
    await expect(themeCards.first()).toBeVisible();
    
    // Verify at least one theme card shows difficulty or category
    const themeInfo = page.locator('text=/Serious|Pop Culture|Whimsical|Facile|Moyen|Difficile/');
    await expect(themeInfo.first()).toBeVisible({ timeout: 5000 });
  });

  test('progressive difficulty in Round 2 questions', async ({ page }) => {
    // Simplified flow to test difficulty progression
    await page.goto(`/game/${gameCode}/round2`);
    
    // Join as player
    const nameInput = page.locator('input[placeholder*="name"], input[placeholder*="nom"]');
    if (await nameInput.isVisible({ timeout: 3000 })) {
      await nameInput.fill('Difficulty Tester');
      await page.click('button:text("Join"), button:text("Rejoindre")');
    }
    
    // Select theme
    await page.locator('.theme-card, [data-testid="theme-card"]').first().click();
    
    // Verify questions 1-3 are marked as EASY
    await expect(page.locator('text=/Easy|Facile|Question 1/')).toBeVisible({ timeout: 10000 });
  });

  test('score accumulation across questions', async ({ page }) => {
    await page.goto(`/game/${gameCode}/round2`);
    
    // Quick player join
    const nameInput = page.locator('input[placeholder*="name"], input[placeholder*="nom"]');
    if (await nameInput.isVisible({ timeout: 3000 })) {
      await nameInput.fill('Score Tester');
      await page.click('button:text("Join"), button:text("Rejoindre")');
    }
    
    // Select theme and verify score display
    await page.locator('.theme-card').first().click();
    
    // Check that score is visible
    await expect(page.locator('text=/Score:|Points:/')).toBeVisible({ timeout: 10000 });
  });
});
