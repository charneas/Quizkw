"""
Découverte de la grille mémoire (Manche 3) par code de partie, pour un
spectateur (joueur éliminé en Manche 1/2) — BUG-401, #32.

GET /games/{code}/memory-grid/state doit renvoyer exactement le même
contenu que GET /memory-grid/{memory_grid_id}/state pour la grille active
de cette partie, sans exiger de token host (accès public, même niveau que
l'endpoint existant par id).
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import (
    GameSession, Team, Player, PlayerRound2Stats, PlayerRound3Stats,
    Theme, ThemeCategory, Question, Difficulty, RoundType,
)


class TestMemoryGridSpectatorState:
    @pytest.fixture(autouse=True)
    def setup_test_data(self, test_client, db_session: Session):
        game_session = GameSession(
            code="SPECTM3",
            total_players=4,
            players_per_team=1,
            current_round=RoundType.MANCHE_3,
            created_at=datetime.utcnow(),
        )
        db_session.add(game_session)
        db_session.flush()

        themes = [
            Theme(name=f"Theme Spectator {i + 1}", category=ThemeCategory.SERIOUS,
                  difficulty_level=5, description=f"Theme de test {i + 1}")
            for i in range(12)
        ]
        db_session.add_all(themes)
        db_session.flush()

        questions = [
            Question(
                text=f"Question HARD Spectator {i + 1}",
                category="General",
                difficulty=Difficulty.HARD,
                points=6,
                correct_answer=f"Correct answer {i + 1}",
                wrong_answers='["a", "b", "c"]',
                theme_id=themes[i % len(themes)].id,
                question_number=i + 1,
            )
            for i in range(40)
        ]
        db_session.add_all(questions)
        db_session.flush()

        team = Team(game_session_id=game_session.id, name="Equipe porteuse")
        db_session.add(team)
        db_session.flush()

        finalists = [Player(name=f"Finaliste {i + 1}", team_id=team.id) for i in range(4)]
        db_session.add_all(finalists)
        db_session.flush()

        theme_index = 0
        for rank, player in enumerate(finalists):
            db_session.add(PlayerRound2Stats(
                game_session_id=game_session.id,
                player_id=player.id,
                score=100 - rank * 10,
            ))
            db_session.add(PlayerRound3Stats(
                game_session_id=game_session.id,
                player_id=player.id,
                selected_theme_ids=[themes[theme_index + j].id for j in range(3)],
            ))
            theme_index += 3

        db_session.commit()

        self.client = test_client
        self.game = game_session
        self.db_session = db_session
        self.host_headers = {"X-Host-Token": game_session.host_token}

        yield

    def test_spectator_state_matches_state_by_id(self):
        create = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
        )
        assert create.status_code == 200
        grid_id = create.json()["id"]

        by_id = self.client.get(f"/memory-grid/{grid_id}/state")
        assert by_id.status_code == 200

        by_code = self.client.get(f"/games/{self.game.code}/memory-grid/state")
        assert by_code.status_code == 200

        assert by_code.json() == by_id.json()

    def test_spectator_state_requires_no_host_token(self):
        """Un spectateur n'a jamais de token host — l'endpoint doit rester accessible sans."""
        self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
        )

        response = self.client.get(f"/games/{self.game.code}/memory-grid/state")
        assert response.status_code == 200

    def test_spectator_state_404_when_no_grid_yet(self):
        response = self.client.get(f"/games/{self.game.code}/memory-grid/state")
        assert response.status_code == 404

    def test_spectator_state_404_for_unknown_game(self):
        response = self.client.get("/games/DOESNOTEXIST/memory-grid/state")
        assert response.status_code == 404

    def test_state_by_id_endpoint_unaffected(self):
        """Non-régression : le contrat de l'endpoint existant par id ne change pas."""
        create = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
        )
        grid_id = create.json()["id"]

        response = self.client.get(f"/memory-grid/{grid_id}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["memory_grid"]["id"] == grid_id
        assert len(data["cells"]) == 35