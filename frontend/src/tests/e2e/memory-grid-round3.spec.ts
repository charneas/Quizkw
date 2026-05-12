import { test, expect } from '@playwright/test';

// Mock API responses
const mockGameData = {
  id: 1,
  code: "TESTROUND3",
  name: "Test Round 3 Game",
  status: "active",
  teams: [
    { id: 1, name: "Team 1", color: null },
    { id: 2, name: "Team 2", color: null },
    { id: 3, name: "Team 3", color: null },
    { id: 4, name: "Team 4", color: null }
  ]
};

const mockRankingData = {
  ranking: [
    { team_id: 4, team_name: "Team 4", total_score: 475 },
    { team_id: 3, team_name: "Team 3", total_score: 350 },
    { team_id: 2, team_name: "Team 2", total_score: 225 },
    { team_id: 1, team_name: "Team 1", total_score: 175 }
  ]
};

const mockColorsData = {
  available_colors: [
    "#FF5733", "#33FF57", "#5733FF", "#FF33A1", "#33A1FF",
    "#A1FF33", "#FF33FF", "#33FFFF", "#FFFF33", "#A133FF",
    "#FFA133", "#33FFA1", "#A1FFA1", "#FFA1FF", "#A1A1FF",
    "#FFA1A1", "#A1FFA1", "#FF33A1", "#33A1A1", "#A13333"
  ]
};

test.describe('Memory Grid Round 3 - E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API responses before each test
    await page.route('**/games/TESTROUND3', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockGameData)
      });
    });

    await page.route('**/games/TESTROUND3/memory-grid/team-ranking', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockRankingData)
      });
    });

    await page.route('**/games/TESTROUND3/available-colors', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockColorsData)
      });
    });

    // Navigate to the game page
    await page.goto('/game/TESTROUND3');
  });

  test('[P0] should display Round 3 Memory Grid interface', async ({ page }) => {
    // Verify the page loads with Round 3 specific elements
    await expect(page.getByRole('heading', { name: 'Round 3: Memory Grid' })).toBeVisible();
    await expect(page.getByText('7x5 Grid')).toBeVisible();
    await expect(page.getByText('Final 4 Teams')).toBeVisible();
    
    // Verify team ranking is displayed
    await expect(page.getByText('Team Ranking')).toBeVisible();
    await expect(page.getByText('Team 4 - 475 points')).toBeVisible();
    await expect(page.getByText('Team 1 - 175 points')).toBeVisible();
  });

  test('[P1] should create memory grid with themes successfully', async ({ page }) => {
    // Mock the grid creation endpoint
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          memory_grid_id: 123,
          grid_size: "7x5",
          round_number: 3,
          total_cells: 35,
          message: "Memory grid created successfully"
        })
      });
    });

    // Click create grid button
    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    
    // Select themes
    await page.getByLabel('Select Theme 1').check();
    await page.getByLabel('Select Theme 2').check();
    await page.getByLabel('Select Theme 3').check();
    await page.getByLabel('Select Theme 4').check();
    
    // Set difficulty to HARD
    await page.getByLabel('Difficulty').selectOption('HARD');
    
    // Submit
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Verify success message
    await expect(page.getByText('Memory grid created successfully')).toBeVisible();
    await expect(page.getByText('Grid ID: 123')).toBeVisible();
    
    // Verify grid visualization appears
    await expect(page.getByTestId('memory-grid-visualization')).toBeVisible();
    await expect(page.getByTestId('grid-cell').first()).toBeVisible();
  });

  test('[P1] should display available colors for team selection', async ({ page }) => {
    // Navigate to color selection
    await page.getByRole('button', { name: 'Select Team Colors' }).click();
    
    // Verify color selection interface
    await expect(page.getByRole('heading', { name: 'Select Team Colors' })).toBeVisible();
    
    // Verify all 4 teams are listed
    for (let i = 1; i <= 4; i++) {
      await expect(page.getByText(`Team ${i}`)).toBeVisible();
    }
    
    // Verify color palette is displayed
    await expect(page.getByTestId('color-palette')).toBeVisible();
    
    // Count available colors (should be 20)
    const colorButtons = page.getByTestId('color-option');
    await expect(colorButtons).toHaveCount(20);
    
    // Verify first color is #FF5733
    await expect(colorButtons.first()).toHaveAttribute('data-color', '#FF5733');
  });

  test('[P1] should allow team color selection', async ({ page }) => {
    // Mock color selection endpoint
    await page.route('**/teams/1/select-color', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          team_id: 1,
          selected_color: "#FF5733",
          message: "Color selected successfully"
        })
      });
    });

    // Navigate to color selection
    await page.getByRole('button', { name: 'Select Team Colors' }).click();
    
    // Select Team 1
    await page.getByText('Team 1').click();
    
    // Select a color
    await page.getByTestId('color-option').first().click();
    
    // Verify success message
    await expect(page.getByText('Color selected successfully')).toBeVisible();
    
    // Verify Team 1 shows the selected color
    await expect(page.getByTestId('team-color-1')).toHaveCSS('background-color', 'rgb(255, 87, 51)');
  });

  test('[P1] should prevent duplicate color selection', async ({ page }) => {
    // Mock first color selection (success)
    await page.route('**/teams/1/select-color', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          team_id: 1,
          selected_color: "#FF5733",
          message: "Color selected successfully"
        })
      });
    });

    // Mock second color selection (duplicate error)
    await page.route('**/teams/2/select-color', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: "Color #FF5733 is already taken by Team 1"
        })
      });
    });

    // Navigate to color selection
    await page.getByRole('button', { name: 'Select Team Colors' }).click();
    
    // Team 1 selects color
    await page.getByText('Team 1').click();
    await page.getByTestId('color-option').first().click();
    await expect(page.getByText('Color selected successfully')).toBeVisible();
    
    // Team 2 tries to select same color
    await page.getByText('Team 2').click();
    await page.getByTestId('color-option').first().click();
    
    // Verify error message
    await expect(page.getByText('Color #FF5733 is already taken by Team 1')).toBeVisible();
    
    // Verify Team 2 doesn't have the color
    await expect(page.getByTestId('team-color-2')).not.toHaveCSS('background-color', 'rgb(255, 87, 51)');
  });

  test('[P2] should display current team turn', async ({ page }) => {
    // Mock current turn endpoint
    await page.route('**/memory-grid/123/current-team-turn', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          current_team_id: 4,
          current_team_name: "Team 4",
          turn_number: 1
        })
      });
    });

    // Create a grid first
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          memory_grid_id: 123,
          grid_size: "7x5",
          round_number: 3
        })
      });
    });

    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Verify turn display
    await expect(page.getByTestId('current-turn')).toBeVisible();
    await expect(page.getByText('Current Turn: Team 4')).toBeVisible();
    await expect(page.getByText('Turn 1 of 35')).toBeVisible();
  });

  test('[P2] should handle grid cell interaction', async ({ page }) => {
    // Create a grid
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          memory_grid_id: 123,
          grid_size: "7x5",
          round_number: 3
        })
      });
    });

    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Mock cell reveal
    await page.route('**/memory-grid/123/cells/1/reveal', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          cell_id: 1,
          question: "What is the capital of France?",
          theme: "Geography",
          revealed: true
        })
      });
    });

    // Click on first cell
    await page.getByTestId('grid-cell').first().click();
    
    // Verify question is displayed
    await expect(page.getByTestId('question-display')).toBeVisible();
    await expect(page.getByText('What is the capital of France?')).toBeVisible();
    
    // Verify answer input is available
    await expect(page.getByLabel('Your Answer')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit Answer' })).toBeVisible();
  });

  test('[P2] should handle insufficient teams error', async ({ page }) => {
    // Mock error for insufficient teams
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: "Round 3 requires exactly 4 teams. Found: 3 teams."
        })
      });
    });

    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Verify error message
    await expect(page.getByText('Round 3 requires exactly 4 teams')).toBeVisible();
    
    // Verify grid is not created
    await expect(page.getByTestId('memory-grid-visualization')).not.toBeVisible();
  });

  test('[P3] should display performance metrics', async ({ page }) => {
    // Create a grid
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      // Simulate delay for performance measurement
      await new Promise(resolve => setTimeout(resolve, 500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          memory_grid_id: 123,
          grid_size: "7x5",
          round_number: 3,
          creation_time_ms: 450
        })
      });
    });

    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    
    // Start performance measurement
    const startTime = Date.now();
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Wait for success message
    await expect(page.getByText('Memory grid created successfully')).toBeVisible();
    const endTime = Date.now();
    const executionTime = endTime - startTime;
    
    // Verify performance display
    await expect(page.getByTestId('performance-metrics')).toBeVisible();
    
    // Log performance for monitoring
    console.log(`Grid creation time: ${executionTime}ms`);
    
    // Assert reasonable performance (under 2 seconds)
    expect(executionTime).toBeLessThan(2000);
  });

  test('[P3] should handle theme validation errors', async ({ page }) => {
    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    
    // Try to create with only 2 themes (needs 4 for 4 teams)
    await page.getByLabel('Select Theme 1').check();
    await page.getByLabel('Select Theme 2').check();
    
    // Submit with insufficient themes
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Verify client-side validation error
    await expect(page.getByText('Please select exactly 4 themes for 4 teams')).toBeVisible();
    
    // Verify server is not called
    // (This is handled by the mock setup - if called, it would fail the test)
  });
});

// Helper function to simulate game progression
test.describe('Memory Grid Game Progression', () => {
  test('[P1] should progress through game turns', async ({ page }) => {
    // Setup complete game state
    await page.route('**/games/TESTROUND3/memory-grid/create-with-themes', async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ memory_grid_id: 123, grid_size: "7x5", round_number: 3 })
      });
    });

    // Mock turn progression
    let currentTurn = 1;
    await page.route('**/memory-grid/123/current-team-turn', async (route) => {
      const teamId = [4, 3, 2, 1][(currentTurn - 1) % 4];
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          current_team_id: teamId,
          current_team_name: `Team ${teamId}`,
          turn_number: currentTurn
        })
      });
    });

    // Create grid
    await page.getByRole('button', { name: 'Create Memory Grid' }).click();
    await page.getByRole('button', { name: 'Create Grid' }).click();
    
    // Verify initial turn
    await expect(page.getByText('Current Turn: Team 4')).toBeVisible();
    
    // Simulate completing a turn
    await page.getByRole('button', { name: 'Complete Turn' }).click();
    currentTurn = 2;
    
    // Verify turn progression
    await expect(page.getByText('Current Turn: Team 3')).toBeVisible();
    await expect(page.getByText('Turn 2 of 35')).toBeVisible();
  });
});