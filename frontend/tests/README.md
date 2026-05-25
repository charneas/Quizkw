# Tests E2E Playwright - Quiz Application

This directory contains end-to-end tests for the Quiz application covering all 3 rounds.

## Test Structure

### 📁 Test Files

- **`round1.spec.ts`** - Round 1 Classic Quiz (3 tests)
- **`round2.spec.ts`** - Round 2 Thematic 1v1 (4 tests)
- **`round3.spec.ts`** - Round 3 Memory Grid 7x5 (10 tests)
- **`full-game.spec.ts`** - Complete game flow (1 test)

**Total: 18 E2E tests**

---

## Round 1: Classic Quiz

Round 1 tests team-based gameplay with tokens and scoreboards.

### Tests:
1. **Complete Round 1 flow** - Team creation, player addition, gameplay
2. **Token usage** - Verifies token panel and functionality
3. **Intermediate leaderboard** - Checks scoreboard display

### Key Features Tested:
- Team creation (2 teams, 2 players each)
- Question answering flow
- Token panel visibility
- Scoreboard display
- Navigation

---

## Round 2: Thematic 1v1 Battles

Round 2 tests individual player battles with theme selection.

### Tests:
1. **Full player flow** - Name entry, theme selection, 10 questions
2. **Theme selection** - Difficulty levels and categories
3. **Progressive difficulty** - Easy → Medium → Hard progression
4. **Score accumulation** - Points tracking across questions

### Key Features Tested:
- Player name input
- Theme selection interface (10 themes available)
- 10 questions per theme
- Difficulty progression (3 easy, 4 medium, 3 hard)
- Score display
- Completion message

---

## Round 3: Memory Grid 7x5

Round 3 tests the 35-cell memory grid with 4 players and color assignment.

### Tests:
1. **Complete Round 3 flow** - 4 player setup, color selection
2. **Color selection** - 20 color options for teams
3. **Theme selection** -  3 themes per team
4. **Memory grid display** - 7x5 grid (35 cells)
5. **Team turn rotation** - Turn-based gameplay
6. **Hard difficulty questions** - 6-point HARD questions only
7. **Cell color assignment** - Team ownership visualization
8. **Round 3 completion** - Final scores for 4 teams
9. **Grid state persistence** - Cell state after reload
10. **Question availability** - 85 HARD questions for 35 cells

### Key Features Tested:
- Exactly 4 players required
- 20 available colors
- 3 themes per team selection
- 7x5 memory grid (35 cells total)
- HARD difficulty only (6 points)
- Team turn rotation
- Cell ownership colors
- State persistence
- 85 imported questions available

---

## Full Game Flow

Comprehensive test that plays through all 3 rounds in sequence.

### Test Flow:
1. **Game Creation** - Create lobby, extract game code
2. **Round 1** - 2 teams, 4 players, answer 3 questions
3. **Round 2** - Join as player, select theme, answer 5 questions
4. **Round 3** - Setup 4 teams, color selection, play 3 cells
5. **Results** - Verify final results screen

### Duration: ~2-3 minutes

---

## Running the Tests

### Prerequisites
```bash
cd frontend
npm install
```

### Run All Tests
```bash
npm run test:e2e
```

### Run Specific Test Suite
```bash
# Round 1 only
npx playwright test round1.spec.ts

# Round 2 only
npx playwright test round2.spec.ts

# Round 3 only
npx playwright test round3.spec.ts

# Full game flow
npx playwright test full-game.spec.ts
```

### Run in UI Mode (Recommended for Development)
```bash
npx playwright test --ui
```

### Run in Debug Mode
```bash
npx playwright test --debug
```

### Run Headed (See Browser)
```bash
npx playwright test --headed
```

---

## Test Configuration

Configuration is in `playwright.config.ts`:

- **Browser**: Chromium (default), Firefox, WebKit available
- **Base URL**: `http://localhost:5173` (Vite dev server)
- **Timeout**: 10 seconds per action
- **Retries**: 2 retries on CI
- **Parallel**: Tests run in parallel by default

---

## Prerequisites for Tests

### Backend Must Be Running
```bash
cd backend
uvicorn main:app --reload
```

### Database Must Be Seeded
```bash
cd backend
python seed.py
```

This creates:
- 7 questions (Round 1)
- 100 questions in 10 themes (Round 2)
- 85 HARD questions in 20 themes (Round 3)

---

## Test Data

### Round 1
- Questions: Mixed difficulty (EASY, MEDIUM, HARD)
- Teams: 2-3 teams recommended
- Players: 2-4 per team

### Round 2
- Questions: 10 per theme, progressive difficulty
- Themes: 10 available (Serious, Pop Culture, Whimsical)
- Players: 16 individual players

### Round 3
- Questions: 85 HARD questions (50+ more than needed)
- Grid: 7 rows × 5 columns = 35 cells
- Players: Exactly 4 teams/players required
- Colors: 20 available colors
- Themes: Each team selects 3 unique themes

---

## Troubleshooting

### Test Fails: "text=Nouvelle partie not visible"
**Solution**: Ensure frontend dev server is running on `http://localhost:5173`

### Test Fails: "Backend API errors"
**Solution**: Ensure backend is running on `http://localhost:8000`

### Test Fails: "Not enough questions"
**Solution**: Run `python backend/seed.py` to populate database

### Test Timeout
**Solution**: Increase timeout in test or check network connectivity

### Flaky Tests
**Solution**: Use `--retries=2` or increase wait timeouts

---

## Best Practices

1. **Always seed database before tests**
2. **Run backend and frontend before E2E tests**
3. **Use UI mode for debugging** (`--ui`)
4. **Check console logs** for detailed test progress
5. **Run full-game.spec.ts last** (most comprehensive)

---

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run E2E Tests
  run: |
    cd backend && python seed.py &
    cd backend && uvicorn main:app &
    cd frontend && npm run dev &
    sleep 5
    cd frontend && npx playwright test
```

---

## Test Reports

After running tests, view the HTML report:
```bash
npx playwright show-report
```

---

## Coverage

- **Backend**: 85% code coverage (52/52 tests passing)
- **Frontend E2E**: 18 comprehensive tests
- **Database**: 232 questions total (147 + 85 imported)

---

## Contributing

When adding new tests:
1. Follow existing test structure
2. Use descriptive test names
3. Add appropriate timeouts
4. Include console.log for progress tracking
5. Update this README

---

## Questions?

Check the main project documentation or review existing test files for examples!

Happy Testing! 🎉
