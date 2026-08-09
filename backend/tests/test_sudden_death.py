"""
Tests de la mort subite en fin de Manche 3 (story L.001, BUG-305).

AD-0 : la Manche 3 est individuelle, 4 finalistes.
AD-1 : la mort subite départage, elle n'écrit jamais dans PlayerRound3Stats.score.
AD-3 : le serveur juge la correction, jamais le client.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import (
    GameSession, Team, Player, PlayerRound3Stats,
    Theme, ThemeCategory, Question, Difficulty, RoundType,
)
from app.memory_grid import MemoryGrid, GridCell, GridCellStatus, SuddenDeathRound


class TestSuddenDeath:
    @pytest.fixture(autouse=True)
    def setup_test_data(self, test_client, db_session: Session):
        game_session = GameSession(
            code="TESTSUDDEN",
            total_players=4,
            players_per_team=1,
            current_round=RoundType.MANCHE_3,
            created_at=datetime.utcnow(),
        )
        db_session.add(game_session)
        db_session.flush()

        theme = Theme(name="Theme Sudden Death", category=ThemeCategory.SERIOUS,
                       difficulty_level=5, description="Theme de test")
        db_session.add(theme)
        db_session.flush()

        # 6 questions HARD : 1 utilisée par une cellule de grille (à exclure),
        # les autres disponibles pour la mort subite (et son éventuel rejeu).
        questions = [
            Question(
                text=f"Question mort subite {i + 1}",
                category="General",
                difficulty=Difficulty.HARD,
                points=6,
                correct_answer=f"bonne reponse {i + 1}",
                wrong_answers='["a", "b", "c"]',
                theme_id=theme.id,
                question_number=i + 1,
            )
            for i in range(6)
        ]
        db_session.add_all(questions)
        db_session.flush()

        team = Team(game_session_id=game_session.id, name="Equipe porteuse")
        db_session.add(team)
        db_session.flush()

        finalists = [Player(name=f"Finaliste {i + 1}", team_id=team.id) for i in range(4)]
        db_session.add_all(finalists)
        db_session.flush()

        memory_grid = MemoryGrid(game_session_id=game_session.id, rows=7, cols=5, is_completed=True)
        db_session.add(memory_grid)
        db_session.flush()

        # Une cellule utilise déjà questions[0] : elle ne doit jamais être
        # reproposée en mort subite.
        db_session.add(GridCell(
            memory_grid_id=memory_grid.id, row=0, col=0,
            question_id=questions[0].id, status=GridCellStatus.ANSWERED,
            assigned_player_id=finalists[0].id, answered_by_player_id=finalists[0].id,
            points_awarded=3,
        ))

        # Égalité au sommet entre finalists[0] et finalists[1] (score=10).
        db_session.add(PlayerRound3Stats(game_session_id=game_session.id, player_id=finalists[0].id, score=10, cells_claimed=3))
        db_session.add(PlayerRound3Stats(game_session_id=game_session.id, player_id=finalists[1].id, score=10, cells_claimed=2))
        db_session.add(PlayerRound3Stats(game_session_id=game_session.id, player_id=finalists[2].id, score=6, cells_claimed=1))
        db_session.add(PlayerRound3Stats(game_session_id=game_session.id, player_id=finalists[3].id, score=4, cells_claimed=1))
        db_session.commit()

        self.client = test_client
        self.game = game_session
        self.memory_grid = memory_grid
        self.finalists = finalists
        self.questions = questions
        self.db_session = db_session
        self.host_headers = {"X-Host-Token": game_session.host_token}

        yield

    # --- Détection de l'égalité (régression, comportement existant) ---

    def test_standings_report_tie_without_triggering_sudden_death(self):
        response = self.client.get(f"/games/{self.game.code}/memory-grid/standings")
        assert response.status_code == 200
        data = response.json()
        assert data["is_tie"] is True
        assert data["winner"] is None

    # --- Déclenchement ---

    def test_start_sudden_death_fails_without_tie(self):
        # Casse l'égalité : plus aucune raison de déclencher une mort subite.
        stats = self.db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == self.finalists[1].id
        ).first()
        stats.score = 2
        self.db_session.commit()

        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start",
            headers=self.host_headers,
        )
        assert response.status_code == 400

    def test_start_sudden_death_requires_host_token(self):
        response = self.client.post(f"/games/{self.game.code}/memory-grid/sudden-death/start")
        assert response.status_code == 403

    def test_start_sudden_death_creates_round_for_tied_players_only(self):
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start",
            headers=self.host_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert set(data["tied_player_ids"]) == {self.finalists[0].id, self.finalists[1].id}
        assert data["is_completed"] is False
        assert data["question_text"]

        # La question de la cellule déjà jouée n'est jamais reproposée.
        round_obj = self.db_session.query(SuddenDeathRound).filter(SuddenDeathRound.id == data["id"]).first()
        assert round_obj.question_id != self.questions[0].id

    def test_start_sudden_death_supports_three_way_tie(self):
        stats = self.db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == self.finalists[2].id
        ).first()
        stats.score = 10
        self.db_session.commit()

        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start",
            headers=self.host_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert set(data["tied_player_ids"]) == {
            self.finalists[0].id, self.finalists[1].id, self.finalists[2].id,
        }

    def test_start_sudden_death_is_idempotent(self):
        first = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start", headers=self.host_headers
        )
        second = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start", headers=self.host_headers
        )
        assert first.json()["id"] == second.json()["id"]

    # --- Résolution ---

    def _start(self):
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start", headers=self.host_headers
        )
        round_id = response.json()["id"]
        round_obj = self.db_session.query(SuddenDeathRound).filter(SuddenDeathRound.id == round_id).first()
        question = self.db_session.query(Question).filter(Question.id == round_obj.question_id).first()
        return round_id, question

    def test_correct_answer_resolves_round_without_touching_score(self):
        round_id, question = self._start()
        winner = self.finalists[0]

        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/answer",
            json={"sudden_death_round_id": round_id, "player_id": winner.id, "player_answer": question.correct_answer},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_correct"] is True
        assert data["is_completed"] is True
        assert data["winner_player_id"] == winner.id

        # AC #5 : la mort subite départage, elle n'ajoute pas de points.
        stats = self.db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == winner.id
        ).first()
        assert stats.score == 10

        standings = self.client.get(f"/games/{self.game.code}/memory-grid/standings").json()
        assert standings["is_tie"] is False
        assert standings["winner"]["player_id"] == winner.id

    def test_wrong_answer_lets_other_tied_player_still_win(self):
        round_id, question = self._start()
        loser, winner = self.finalists[0], self.finalists[1]

        wrong = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/answer",
            json={"sudden_death_round_id": round_id, "player_id": loser.id, "player_answer": "reponse fausse"},
        )
        assert wrong.status_code == 200
        assert wrong.json()["is_correct"] is False
        assert wrong.json()["is_completed"] is False

        right = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/answer",
            json={"sudden_death_round_id": round_id, "player_id": winner.id, "player_answer": question.correct_answer},
        )
        assert right.status_code == 200
        assert right.json()["is_completed"] is True
        assert right.json()["winner_player_id"] == winner.id

    def test_all_tied_players_wrong_triggers_replay_with_new_question(self):
        round_id, question = self._start()
        first_used_question_id = question.id

        for player in (self.finalists[0], self.finalists[1]):
            resp = self.client.post(
                f"/games/{self.game.code}/memory-grid/sudden-death/answer",
                json={"sudden_death_round_id": round_id, "player_id": player.id, "player_answer": "reponse fausse"},
            )
            assert resp.status_code == 200

        exhausted = self.db_session.query(SuddenDeathRound).filter(SuddenDeathRound.id == round_id).first()
        assert exhausted.is_completed is True
        assert exhausted.winner_player_id is None

        replay = self.client.post(
            f"/games/{self.game.code}/memory-grid/sudden-death/start", headers=self.host_headers
        )
        assert replay.status_code == 200
        replay_data = replay.json()
        assert replay_data["id"] != round_id

        replay_round = self.db_session.query(SuddenDeathRound).filter(SuddenDeathRound.id == replay_data["id"]).first()
        assert replay_round.question_id != first_used_question_id

    def test_answer_state_endpoint_reflects_active_round(self):
        round_id, _ = self._start()

        response = self.client.get(f"/games/{self.game.code}/memory-grid/sudden-death/state")
        assert response.status_code == 200
        assert response.json()["id"] == round_id