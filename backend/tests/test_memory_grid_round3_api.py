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
from app.memory_grid import MemoryGrid, GridCell


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
        self.host_headers = {"X-Host-Token": game_session.host_token}

        yield

        # Pas de nettoyage manuel : la fixture db_session de conftest isole
        # chaque test par un rollback. Le nettoyage explicite d'avant entrait en
        # conflit avec le rollback que les endpoints déclenchent sur les chemins
        # d'erreur, et faisait échouer le teardown.

    # --- Création de grille ---

    def test_create_memory_grid_with_themes_success(self):
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
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
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
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
        # BUG-302 : seules les 12 couleurs exposées par PlayerColorEnum (le
        # schéma API) sont réellement sélectionnables — get_available_colors
        # renvoyait auparavant les 20 valeurs de l'enum interne PlayerColor,
        # dont 8 que le client ne peut de toute façon jamais choisir.
        assert len(data["available_colors"]) == 12
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

    # --- Tours et synchronisation (C-003) ---

    def _create_grid_and_round(self):
        create_response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
        )
        memory_grid_id = create_response.json()["id"]

        start_response = self.client.post(f"/games/{self.game.code}/memory-grid/start", headers=self.host_headers)
        round_id = start_response.json()["round_id"]

        # Playtest 2026-08-15 : reveal_cell refuse tant que la phase de
        # mémorisation (MEMORIZE_DURATION_SECONDS) n'est pas écoulée — ces
        # tests jouent immédiatement après le start, donc on recule
        # created_at pour se placer après cette phase.
        from app.memory_grid import MemoryGridRound, MEMORIZE_DURATION_SECONDS
        from datetime import timedelta
        round_obj = self.db_session.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        round_obj.created_at = datetime.now() - timedelta(seconds=MEMORIZE_DURATION_SECONDS + 10)
        self.db_session.commit()

        return memory_grid_id, round_id

    def test_answer_cell_advances_turn(self):
        memory_grid_id, round_id = self._create_grid_and_round()
        first_player = self.finalists[0].id
        first_player_headers = {"X-Player-Token": self.finalists[0].player_token}

        cell = self.db_session.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid_id
        ).first()
        question = self.db_session.query(Question).filter(Question.id == cell.question_id).first()

        self.client.post("/memory-grid/reveal-cell", json={
            "round_id": round_id, "player_id": first_player, "cell_id": cell.id,
        }, headers=first_player_headers)
        self.client.post("/memory-grid/answer-cell", json={
            "round_id": round_id, "player_id": first_player, "cell_id": cell.id,
            "player_answer": question.correct_answer,
        }, headers=first_player_headers)

        turn_response = self.client.get(f"/memory-grid/{memory_grid_id}/current-player-turn")
        assert turn_response.json()["current_player_id"] != first_player

    def test_skip_turn_advances_without_answering(self):
        memory_grid_id, _ = self._create_grid_and_round()
        first_player = self.finalists[0].id

        response = self.client.post(f"/memory-grid/{memory_grid_id}/skip-turn")
        assert response.status_code == 200
        assert response.json()["current_turn"] == 1

        turn_response = self.client.get(f"/memory-grid/{memory_grid_id}/current-player-turn")
        assert turn_response.json()["current_player_id"] != first_player

    def test_skip_turn_missing_grid(self):
        response = self.client.post("/memory-grid/999999/skip-turn")
        assert response.status_code == 404

    def test_skip_turn_wraps_around_finalists(self):
        """Le tourniquet boucle : après 4 skip-turn, on retrouve le premier joueur."""
        memory_grid_id, _ = self._create_grid_and_round()
        first_player = self.finalists[0].id

        for _ in range(4):
            response = self.client.post(f"/memory-grid/{memory_grid_id}/skip-turn")
            assert response.status_code == 200

        turn_response = self.client.get(f"/memory-grid/{memory_grid_id}/current-player-turn")
        assert turn_response.json()["current_player_id"] == first_player

    def test_skip_turn_ignores_stale_expected_turn(self):
        """C-003 : un second client dont le timer expire pour le même tour ne doit pas
        avancer une deuxième fois (compare-and-set sur expected_turn)."""
        memory_grid_id, _ = self._create_grid_and_round()

        first = self.client.post(f"/memory-grid/{memory_grid_id}/skip-turn?expected_turn=0")
        assert first.status_code == 200
        assert first.json()["current_turn"] == 1

        # Un autre onglet, dont le timer avait démarré avant ce premier skip,
        # rappelle avec le même expected_turn périmé : ignoré, pas de second avancement.
        stale = self.client.post(f"/memory-grid/{memory_grid_id}/skip-turn?expected_turn=0")
        assert stale.status_code == 200
        assert stale.json()["current_turn"] == 1

    def test_skip_turn_marks_revealed_cell_permanently_lost(self):
        """Playtest 2026-08-15 : une cellule révélée dont le temps de réponse
        expire est définitivement perdue (comme une mauvaise réponse), pas
        remise en jeu — personne ne doit pouvoir la re-choisir, ni la
        "contrôler" sans y avoir répondu."""
        memory_grid_id, round_id = self._create_grid_and_round()
        first_player = self.finalists[0].id

        cell = self.db_session.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid_id
        ).first()
        self.client.post("/memory-grid/reveal-cell", json={
            "round_id": round_id, "player_id": first_player, "cell_id": cell.id,
        }, headers={"X-Player-Token": self.finalists[0].player_token})

        self.client.post(f"/memory-grid/{memory_grid_id}/skip-turn")

        self.db_session.expire_all()
        refreshed = self.db_session.query(GridCell).filter(GridCell.id == cell.id).first()
        assert refreshed.status.value == "answered"
        assert refreshed.answered_by_player_id is None
        assert refreshed.points_awarded == 0

        # Ni le premier joueur ni un autre ne peuvent la re-choisir.
        second_player = self.finalists[1].id
        reveal_again = self.client.post("/memory-grid/reveal-cell", json={
            "round_id": round_id, "player_id": second_player, "cell_id": cell.id,
        }, headers={"X-Player-Token": self.finalists[1].player_token})
        assert reveal_again.status_code == 400

    def test_create_memory_grid_is_idempotent(self):
        """C-003 Scenario 6 : un rechargement de page ne doit pas recréer la grille."""
        first = self.client.post(f"/games/{self.game.code}/memory-grid/create", headers=self.host_headers)
        assert first.status_code == 200
        second = self.client.post(f"/games/{self.game.code}/memory-grid/create", headers=self.host_headers)
        assert second.status_code == 200

        assert first.json()["id"] == second.json()["id"]

        cells = self.db_session.query(GridCell).filter(
            GridCell.memory_grid_id == first.json()["id"]
        ).all()
        assert len(cells) == 35

    def test_start_memory_grid_round_is_idempotent(self):
        """C-003 Scenario 6 : un rechargement de page ne doit pas repartir sur un nouveau round."""
        self.client.post(f"/games/{self.game.code}/memory-grid/create", headers=self.host_headers)

        first = self.client.post(f"/games/{self.game.code}/memory-grid/start", headers=self.host_headers)
        second = self.client.post(f"/games/{self.game.code}/memory-grid/start", headers=self.host_headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["round_id"] == second.json()["round_id"]

    # --- Performance ---

    def test_performance_create_memory_grid(self):
        import time

        start_time = time.time()
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5",
            headers=self.host_headers,
        )
        execution_time = time.time() - start_time

        assert response.status_code == 200
        assert execution_time < 2.0, f"Création grille trop lente: {execution_time:.2f}s"
