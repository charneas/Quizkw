# Workflow Current State analysis

## Phase 1 & 2 Workflow
1. **Landing Page (`Home.tsx`)**:
   - Create game: POST `/games/`
   - Join game: Navigation
2. **Lobby (`Lobby.tsx`)**:
   - Create Team: POST `/games/{code}/teams/`
   - **Gap**: No player association mechanism, but `start_game` (in `main.py`) enforces player-to-team count.
   - Start Game: POST `/games/{code}/start`
3. **Round 1 / Main Game (`Game.tsx`)**:
   - Manages question rounds.
   - **Transition**: `handleAdvanceToPhase3` triggers:
     - POST `/games/{code}/advance-to-phase3`
     - POST `/games/{code}/memory-grid/create`
     - POST `/games/{code}/memory-grid/start`
     - Navigate to `/game/{code}/memory-grid`

## Current Bottlenecks
- **Lobby Start-Game constraint**: Backend requires `players.count == game.players_per_team` for each team, but we have no UI to create/join players into a team.
- **Initialization sequence**: Memory grid needs `get_grid_state` immediately after creation, but `createMemoryGrid` response was missing fields. (Fixed).

## Proposed Revisions for Workflow
1. **Lobby**: Add functionality to either:
   - Provide a way to add a player to a specific team.
   - Or, make the backend `start_game` smarter (we already did a "patch" here with auto-filling players).
2. **Advancement Logic**: The `handleAdvanceToPhase3` is doing too much at once. It should likely return a state, and navigate based on backend success, possibly pausing for the user to understand they are changing phases.

---
**What would you like to review first?**
- Shall I draft a sequence diagram or a checklist for the desired flow to validate against your vision?
