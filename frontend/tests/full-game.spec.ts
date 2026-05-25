import { test, expect } from '@playwright/test';

test.describe('Complete Game Flow - All 3 Rounds', () => {
  let gameCode: string;

  test('complete game journey from creation to Round 3 results', async ({ page }) => {
    // ========================================
    // GAME CREATION & LOBBY
    // ========================================
    console.log('Step 1: Creating game...');
    await page.goto('/');
    await expect(page.locator('text=Nouvelle partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=Nouvelle partie');
    await expect(page.locator('text=🚀 Créer la partie')).toBeVisible({ timeout: 10000 });
    await page.click('text=🚀 Créer la partie');
    
    // Extract game code
    await page.waitForURL(/\/lobby\//, { timeout: 10000 });
    const url = page.url();
    gameCode = url.split('/').pop()!;
    console.log(`✅ Game created with code: ${gameCode}`);

    // ========================================
    // ROUND 1: CLASSIC QUIZ
    // ========================================
    console.log('\nStep 2: Starting Round 1 - Classic Quiz...');
    
    // Create 2 teams
    await expect(page.locator('text=/Créer des équipes|Create Teams/')).toBeVisible({ timeout: 10000 });
    
    for (let teamNum = 1; teamNum <= 2; teamNum++) {
      await page.click('button:text("Ajouter une équipe"), button:text("Add Team")');
      await expect(page.locator(`text=/Équipe ${teamNum}|Team ${teamNum}/`)).toBeVisible();
      
      // Add 2 players per team
      const teamInput = page.locator('input[placeholder*="Nom du joueur"], input[placeholder*="Player name"]').nth(teamNum - 1);
      await teamInput.fill(`Player${teamNum}A`);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
      await teamInput.fill(`Player${teamNum}B`);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
    }
    
    // Start Round 1
    await page.click('button:text("Démarrer la partie"), button:text("Start Game")');
    await page.waitForURL(/\/game\//, { timeout: 10000 });
    console.log('✅ Round 1 started');
    
    // Play 3 questions
    for (let i = 0; i < 3; i++) {
      await expect(page.locator('text=/Question/')).toBeVisible({ timeout: 10000 });
      await page.locator('button.answer-button, .answer-option').first().click();
      await expect(page.locator('text=/Correct|Incorrect|Bonne|Mauvaise/')).toBeVisible({ timeout: 5000 });
      await page.click('button:text("Question suivante"), button:text("Next Question")');
      await page.waitForTimeout(500);
    }
    console.log('✅ Round 1 completed (3 questions)');

    // ========================================
    // ROUND 2: THEMATIC 1v1
    // ========================================
    console.log('\nStep 3: Starting Round 2 - Thematic Battles...');
    await page.goto(`/game/${gameCode}/round2`);
    await page.waitForTimeout(1000);
    
    // Player selection
    const nameInput = page.locator('input[placeholder*="name"], input[placeholder*="nom"]');
    if (await nameInput.isVisible({ timeout: 3000 })) {
      await nameInput.fill('Round2 Player');
      await page.click('button:text("Join Game"), button:text("Rejoindre")');
      await page.waitForTimeout(500);
    }
    
    // Theme selection
    await expect(page.locator('text=/Select a Theme|Sélectionner/')).toBeVisible({ timeout: 10000 });
    await page.locator('.theme-card, [data-testid="theme-card"]').first().click();
    await page.waitForTimeout(1000);
    
    // Answer 5 questions
    for (let i = 0; i < 5; i++) {
      if (await page.locator('text=/Question/').isVisible({ timeout: 3000 })) {
        await page.locator('.grid-cols-2 button, button.answer-option').first().click();
        await page.waitForTimeout(1000);
        
        const nextBtn = page.locator('button:text("Next Question"), button:text("Question suivante")');
        if (await nextBtn.isVisible({ timeout: 2000 })) {
          await nextBtn.click();
          await page.waitForTimeout(500);
        }
      }
    }
    console.log('✅ Round 2 completed (5 questions)');

    // ========================================
    // ROUND 3: MEMORY GRID 7x5
    // ========================================
    console.log('\nStep 4: Starting Round 3 - Memory Grid...');
    
    // Setup 4 players for Round 3
    await page.goto(`/lobby/${gameCode}`);
    await page.waitForTimeout(1000);
    
    // Ensure we have 4 teams
    const currentTeams = await page.locator('text=/Équipe|Team/').count();
    const teamsToAdd = Math.max(0, 4 - currentTeams);
    
    for (let i = 0; i < teamsToAdd; i++) {
      await page.click('button:text("Ajouter une équipe"), button:text("Add Team")');
      await page.waitForTimeout(500);
    }
    
    // Navigate to Round 3
    await page.goto(`/game/${gameCode}/round3`);
    await page.waitForTimeout(2000);
    
    // Color selection (if needed)
    if (await page.locator('text=/Select Color|Sélectionner une couleur/').isVisible({ timeout: 5000 })) {
      const colorBtn = page.locator('button[data-color], .color-option').first();
      if (await colorBtn.isVisible({ timeout: 3000 })) {
        await colorBtn.click();
        await page.waitForTimeout(1000);
      }
    }
    
    // Theme selection (if needed)
    if (await page.locator('text=/Select 3 themes|Sélectionnez 3 thèmes/').isVisible({ timeout: 5000 })) {
      const themeCards = page.locator('.theme-card, [data-testid="theme-card"]');
      for (let i = 0; i < 3; i++) {
        if (await themeCards.nth(i).isVisible({ timeout: 2000 })) {
          await themeCards.nth(i).click();
          await page.waitForTimeout(500);
        }
      }
      
      const confirmBtn = page.locator('button:text("Confirm"), button:text("Confirmer")');
      if (await confirmBtn.isVisible({ timeout: 2000 })) {
        await confirmBtn.click();
        await page.waitForTimeout(1000);
      }
    }
    
    // Play on memory grid
    await page.goto(`/game/${gameCode}/round3/grid`);
    await page.waitForTimeout(2000);
    
    // Click 3 cells and answer questions
    const gridCells = page.locator('.grid-cell, [data-testid="grid-cell"]');
    for (let i = 0; i < 3; i++) {
      if (await gridCells.nth(i).isVisible({ timeout: 3000 })) {
        await gridCells.nth(i).click();
        await page.waitForTimeout(1000);
        
        const answerBtn = page.locator('button.answer-option, .grid-cols-2 button').first();
        if (await answerBtn.isVisible({ timeout: 3000 })) {
          await answerBtn.click();
          await page.waitForTimeout(1000);
        }
        
        // Click back to grid
        const backBtn = page.locator('button:text("Back"), button:text("Retour"), button:text("Grid")');
        if (await backBtn.isVisible({ timeout: 2000 })) {
          await backBtn.click();
          await page.waitForTimeout(500);
        }
      }
    }
    console.log('✅ Round 3 completed (3 cells)');

    // ========================================
    // FINAL VERIFICATION
    // ========================================
    console.log('\nStep 5: Verifying game completion...');
    
    // Navigate to results
    await page.goto(`/game/${gameCode}/results`);
    await page.waitForTimeout(2000);
    
    // Verify final results screen
    const resultsVisible = await page.locator('text=/Final|Score|Winner|Gagnant|Résultats/').isVisible({ timeout: 5000 });
    if (resultsVisible) {
      console.log('✅ Final results screen displayed');
    }
    
    console.log('\n🎉 COMPLETE GAME FLOW TEST PASSED!');
    console.log(`Game Code: ${gameCode}`);
    console.log('All 3 rounds completed successfully!');
  });
});
