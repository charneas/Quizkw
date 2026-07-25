"""
Tests API de la Manche 3 (grille mémoire).

AD-0 : la Manche 3 est INDIVIDUELLE — 4 finalistes désignés par la Manche 2.
       La fixture crée donc de VRAIS joueurs, là où l'ancienne version fabriquait
       des player_id fictifs sans ligne Player correspondante.
AD-3 : la réponse à une cellule porte le texte du joueur, jamais un verdict.
AD-12 : la sélection de couleur passe par un corps de requête, plus par un
        paramètre d'URL.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import (
    GameSession, Team, Player, PlayerRound2Stats, PlayerRound3Stats,
    Theme, ThemeCategory, Question, Difficulty, RoundType,
)
from app.memory_grid import MemoryGrid


class TestMemoryGridRound3API:
    """Tests API pour la Manche 3."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, test_client, db_session: Session):
        game_session = GameSession(
            code="TESTROUND3",
            total_players=4,
            players_per_team=1,
            current_round=RoundType.MANCHE_3,
            created_at=datetime.utcnow(),
        )
        db_session.add(game_session)
        db_session.flush()

        themes = [
            Theme(name=f"Theme Round3 {i + 1}", category=ThemeCategory.SERIOUS,
                  difficulty_level=5, description=f"Theme de test {i + 1}")
            for i in range(12)
        ]
        db_session.add_all(themes)
        db_session.flush()

        questions = [
            Question(
                text=f"Question HARD Round3 {i + 1}",
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

        # Une équipe porteuse : en Manche 3 elle ne joue plus, mais Player.team_id
        # reste la relation d'appartenance issue de la Manche 1.
        team = Team(game_session_id=game_session.id, name="Equipe porteuse")
        db_session.add(team)
        db_session.flush()

        # 4 VRAIS finalistes, classés par leur score de Manche 2
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
            # Chaque finaliste choisit 3 thèmes distincts
            db_session.add(PlayerRound3Stats(
                game_session_id=game_session.id,
                player_id=player.id,
                selected_theme_ids=[themes[theme_index + j].id for j in range(3)],
            ))
            theme_index += 3

        db_session.commit()

        self.client = test_client
        self.game = game_session
        self.finalists = finalists
        self.themes = themes
        self.db_session = db_session

        yield

        # Pas de nettoyage manuel : la fixture db_session de conftest isole
        # chaque test par un rollback. Le nettoyage explicite d'avant entrait en
        # conflit avec le rollback que les endpoints déclenchent sur les chemins
        # d'erreur, et faisait échouer le teardown.

    # --- Création de grille ---

    def test_create_memory_grid_with_themes_success(self):
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["game_session_id"] == self.game.id
        assert data["grid_size"] == 5

        memory_grid = self.db_session.query(MemoryGrid).filter(
            MemoryGrid.game_session_id == self.game.id
        ).first()
        assert memory_grid is not None
        assert memory_grid.rows == 7
        assert memory_grid.cols == 5

    def test_create_memory_grid_missing_game(self):
        response = self.client.post(
            "/games/INVALIDCODE/memory-grid/create-with-themes?rows=7&cols=5"
        )
        assert response.status_code == 404

    # --- Finalistes et tours ---

    def test_get_finalists_success(self):
        """AD-0 : l'API classe des JOUEURS, exactement quatre."""
        response = self.client.get(f"/games/{self.game.code}/memory-grid/finalists")

        assert response.status_code == 200
        data = response.json()
        assert data["finalists"] == [p.id for p in self.finalists]
        assert len(data["finalists"]) == 4

    def test_get_finalists_missing_game(self):
        response = self.client.get("/games/INVALIDCODE/memory-grid/finalists")
        assert response.status_code == 404

    def test_get_current_player_turn_success(self):
        create_response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5"
        )
        assert create_response.status_code == 200
        memory_grid_id = create_response.json()["id"]

        response = self.client.get(f"/memory-grid/{memory_grid_id}/current-player-turn")

        assert response.status_code == 200
        data = response.json()
        assert data["current_player_id"] == self.finalists[0].id
        assert data["finalists"] == [p.id for p in self.finalists]

    def test_get_current_player_turn_missing_grid(self):
        response = self.client.get("/memory-grid/999999/current-player-turn")
        assert response.status_code == 404

    # --- Couleurs ---

    def test_get_available_colors_success(self):
        response = self.client.get(f"/games/{self.game.code}/available-colors")

        assert response.status_code == 200
        data = response.json()
        assert len(data["available_colors"]) == 20
        assert all(isinstance(color, str) for color in data["available_colors"])

    def test_select_player_color_success(self):
        player = self.finalists[0]

        response = self.client.post("/memory-grid/select-color", json={
            "game_session_id": self.game.id,
            "player_id": player.id,
            "color": "red",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["player_id"] == player.id
        assert data["color"] == "red"

        stats = self.db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == player.id,
            PlayerRound3Stats.game_session_id == self.game.id,
        ).first()
        assert stats.color == "red"

    def test_select_player_color_duplicate(self):
        first, second = self.finalists[0], self.finalists[1]

        self.client.post("/memory-grid/select-color", json={
            "game_session_id": self.game.id, "player_id": first.id, "color": "red",
        })

        response = self.client.post("/memory-grid/select-color", json={
            "game_session_id": self.game.id, "player_id": second.id, "color": "red",
        })

        assert response.status_code == 400
        assert "déjà prise" in response.json()["detail"]

    def test_select_player_color_invalid_color(self):
        response = self.client.post("/memory-grid/select-color", json={
            "game_session_id": self.game.id,
            "player_id": self.finalists[0].id,
            "color": "NOTACOLOR",
        })

        assert response.status_code == 400
        assert "invalide" in response.json()["detail"].lower()

    # --- Performance ---

    def test_performance_create_memory_grid(self):
        import time

        start_time = time.time()
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5"
        )
        execution_time = time.time() - start_time

        assert response.status_code == 200
        assert execution_time < 2.0, f"Création grille trop lente: {execution_time:.2f}s"
