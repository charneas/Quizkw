"""
Tests unitaires pour MemoryGridManager - Manche 3 (grille mémoire).

AD-0 : la Manche 3 est INDIVIDUELLE — exactement 4 finalistes, pas des équipes.
AD-1 : le score de Manche 3 vit dans PlayerRound3Stats ; Team.score n'est
       jamais touché par cette manche.
AD-3 : le serveur juge la correction ; answer_cell reçoit le TEXTE de la
       réponse, pas un booléen fourni par le client.
AD-5 : le manager ne commit pas — les tests committent eux-mêmes quand il faut.
AD-15 : grid_cells.points_awarded est la sentinelle d'idempotence.
"""
import pytest

from app.memory_grid import MemoryGridManager, GridCell, GridCellStatus
from app.models import Question, PlayerRound3Stats, Difficulty


class TestMemoryGridManager:
    """Tests pour la classe MemoryGridManager."""

    def test_create_memory_grid_success(self, memory_grid_manager, db_session,
                                        sample_game_session, round3_finalists,
                                        grid_questions):
        """Une grille 7x5 se crée avec 35 cellules, 5 par finaliste."""
        memory_grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )

        assert memory_grid is not None
        assert memory_grid.game_session_id == sample_game_session.id
        assert memory_grid.rows == 7
        assert memory_grid.cols == 5

        cells = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid.id
        ).all()
        assert len(cells) == 35

        # AD-0 : 5 cellules assignées à chacun des 4 finalistes, 15 neutres
        for finalist in round3_finalists:
            owned = [c for c in cells if c.assigned_player_id == finalist.id]
            assert len(owned) == 5, f"le finaliste {finalist.id} doit posséder 5 cellules"

        neutral = [c for c in cells if c.assigned_player_id is None]
        assert len(neutral) == 15

        # Aucune cellule ne doit être attribuée avant d'avoir été jouée (AD-15)
        assert all(c.points_awarded == 0 for c in cells)

    def test_create_memory_grid_starts_finalists_at_zero_regardless_of_round2_score(
        self, memory_grid_manager, db_session, sample_game_session, round3_finalists, grid_questions
    ):
        """E-002 (AD-1) : les axes de score sont scellés par manche — un
        finaliste au score de Manche 2 élevé (100, fixture round3_finalists)
        ne doit démarrer la Manche 3 qu'à zéro, jamais avec un report."""
        from app.models import PlayerRound2Stats

        round2_scores = {
            s.player_id: s.score for s in db_session.query(PlayerRound2Stats).filter(
                PlayerRound2Stats.game_session_id == sample_game_session.id
            ).all()
        }
        assert len(set(round2_scores.values())) > 1, "la fixture doit varier les scores de Manche 2"

        memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )

        round3_stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.game_session_id == sample_game_session.id
        ).all()
        assert len(round3_stats) == len(round3_finalists)
        assert all(s.score == 0 for s in round3_stats), \
            "aucun score de Manche 2 ne doit être reporté dans PlayerRound3Stats"

    def test_create_memory_grid_excludes_non_finalists(self, memory_grid_manager, db_session,
                                                        sample_game_session, round3_finalists,
                                                        grid_questions):
        """E-001 AC #3 : un joueur de Manche 2 non retenu comme finaliste ne
        doit avoir aucune ligne PlayerRound3Stats — il ne doit pas pouvoir
        se retrouver dans la Manche 3."""
        from app.models import PlayerRound2Stats

        all_round2_players = db_session.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.game_session_id == sample_game_session.id
        ).all()
        finalist_ids = {p.id for p in round3_finalists}
        non_finalist_ids = {p.player_id for p in all_round2_players} - finalist_ids
        assert non_finalist_ids, "la fixture doit contenir des joueurs non finalistes"

        memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )

        stats_player_ids = {
            s.player_id for s in db_session.query(PlayerRound3Stats).filter(
                PlayerRound3Stats.game_session_id == sample_game_session.id
            ).all()
        }
        assert stats_player_ids == finalist_ids
        assert not (stats_player_ids & non_finalist_ids)

    def test_create_memory_grid_no_round2_results(self, memory_grid_manager,
                                                  sample_game_session, grid_questions):
        """Sans résultat de Manche 2, aucun finaliste ne peut être désigné."""
        with pytest.raises(LookupError) as exc_info:
            memory_grid_manager.create_memory_grid(
                game_session_id=sample_game_session.id, rows=7, cols=5
            )

        assert "Manche 2" in str(exc_info.value)

    def test_create_memory_grid_insufficient_questions(self, memory_grid_manager, db_session,
                                                      sample_game_session, round3_finalists):
        """Il faut au moins 35 questions pour remplir la grille."""
        db_session.query(Question).delete()
        db_session.add_all([
            Question(text=f"Q{i}", category="T", difficulty=Difficulty.EASY, points=2,
                     correct_answer="A", wrong_answers="[]", theme_id=None, question_number=i)
            for i in range(10)
        ])
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.create_memory_grid(
                game_session_id=sample_game_session.id, rows=7, cols=5
            )

        assert "Not enough questions for the memory grid" in str(exc_info.value)

    def test_reveal_cell_success(self, memory_grid_manager, db_session, sample_game_session,
                                 round3_finalists, grid_questions):
        """Révéler une cellule la passe en REVEALED et fixe le tour du joueur."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        finalist = round3_finalists[0]

        cell = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == grid.id,
            GridCell.status == GridCellStatus.HIDDEN
        ).first()

        result = memory_grid_manager.reveal_cell(round_obj.id, finalist.id, cell.id)
        db_session.commit()

        assert result["status"] == "cell_revealed"
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.REVEALED

        db_session.refresh(round_obj)
        assert round_obj.current_player_id == finalist.id

    def test_answer_cell_not_revealed(self, memory_grid_manager, db_session, sample_game_session,
                                      round3_finalists, grid_questions):
        """AD-6 : répondre à une cellule non révélée lève une ValueError."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).first()

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.answer_cell(
                round_id=round_obj.id,
                player_id=round3_finalists[0].id,
                cell_id=cell.id,
                player_answer="peu importe",
            )

        assert "révélée" in str(exc_info.value)

    def test_answer_cell_stolen_points(self, memory_grid_manager, db_session, sample_game_session,
                                       round3_finalists, grid_questions):
        """Voler la cellule d'un autre finaliste rapporte 3 points, sur son axe à lui."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)

        thief, victim = round3_finalists[0], round3_finalists[1]
        cell = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == grid.id,
            GridCell.assigned_player_id == victim.id
        ).first()
        question = db_session.query(Question).filter(Question.id == cell.question_id).first()

        memory_grid_manager.reveal_cell(round_obj.id, thief.id, cell.id)
        result = memory_grid_manager.answer_cell(
            round_id=round_obj.id,
            player_id=thief.id,
            cell_id=cell.id,
            player_answer=question.correct_answer,
        )
        db_session.commit()

        assert result["status"] == "answered"
        assert result["is_correct"] is True
        assert result["points_awarded"] == 3
        assert result["cell_type"] == "stolen"

        # AD-1 : le score atterrit sur l'axe Manche 3 du joueur
        stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == thief.id,
            PlayerRound3Stats.game_session_id == sample_game_session.id,
        ).first()
        assert stats.score == 3
        assert stats.cells_claimed == 1

    def test_answer_cell_own_cell_points(self, memory_grid_manager, db_session, sample_game_session,
                                         round3_finalists, grid_questions):
        """Répondre à sa propre cellule rapporte 3 points également."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)

        owner = round3_finalists[2]
        cell = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == grid.id,
            GridCell.assigned_player_id == owner.id
        ).first()
        question = db_session.query(Question).filter(Question.id == cell.question_id).first()

        memory_grid_manager.reveal_cell(round_obj.id, owner.id, cell.id)
        result = memory_grid_manager.answer_cell(
            round_id=round_obj.id, player_id=owner.id, cell_id=cell.id,
            player_answer=question.correct_answer,
        )
        db_session.commit()

        assert result["points_awarded"] == 3
        assert result["cell_type"] == "own"

    def test_answer_cell_wrong_answer_scores_nothing(self, memory_grid_manager, db_session,
                                                     sample_game_session, round3_finalists,
                                                     grid_questions):
        """AD-3 : le serveur juge — une mauvaise réponse ne rapporte rien."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        player = round3_finalists[0]

        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).first()
        memory_grid_manager.reveal_cell(round_obj.id, player.id, cell.id)

        result = memory_grid_manager.answer_cell(
            round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
            player_answer="une reponse totalement fausse",
        )
        db_session.commit()

        assert result["is_correct"] is False
        assert result["points_awarded"] == 0

        stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == player.id
        ).first()
        assert stats is None or stats.score == 0

    def test_answer_normalisation_is_case_and_space_insensitive(self, memory_grid_manager,
                                                                db_session, sample_game_session,
                                                                round3_finalists, grid_questions):
        """AD-3 : normalisation strip + lower, et rien d'autre."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        player = round3_finalists[0]

        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).first()
        question = db_session.query(Question).filter(Question.id == cell.question_id).first()

        memory_grid_manager.reveal_cell(round_obj.id, player.id, cell.id)
        result = memory_grid_manager.answer_cell(
            round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
            player_answer=f"   {question.correct_answer.upper()}   ",
        )
        db_session.commit()

        assert result["is_correct"] is True

    def test_award_is_idempotent(self, memory_grid_manager, db_session, sample_game_session,
                                 round3_finalists, grid_questions):
        """AD-15 : la sentinelle empêche une seconde attribution sur la même cellule."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        player = round3_finalists[0]

        cell = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == grid.id,
            GridCell.assigned_player_id == player.id
        ).first()
        question = db_session.query(Question).filter(Question.id == cell.question_id).first()

        memory_grid_manager.reveal_cell(round_obj.id, player.id, cell.id)
        memory_grid_manager.answer_cell(
            round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
            player_answer=question.correct_answer,
        )
        db_session.commit()

        db_session.refresh(cell)
        assert cell.points_awarded == 3

        # Premier rempart : le statut ANSWERED refuse déjà le rejeu
        with pytest.raises(ValueError):
            memory_grid_manager.answer_cell(
                round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
                player_answer=question.correct_answer,
            )

        # Second rempart, celui qu'AD-15 exige : même si le statut repasse à
        # REVEALED (rejeu concurrent, reprise, bug amont), la sentinelle tient.
        cell.status = GridCellStatus.REVEALED
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.answer_cell(
                round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
                player_answer=question.correct_answer,
            )
        assert "déjà été attribuée" in str(exc_info.value)

        stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == player.id
        ).first()
        assert stats.score == 3

    def test_finalists_are_the_top_four_of_round2(self, memory_grid_manager, sample_game_session,
                                                  round3_finalists):
        """AD-0 : exactement 4 finalistes, dans l'ordre du classement de Manche 2."""
        finalists = memory_grid_manager.get_finalists_from_round2(sample_game_session.id)

        assert len(finalists) == 4
        assert finalists == [p.id for p in round3_finalists]

    def test_answer_cell_returns_memory_grid_id(self, memory_grid_manager, db_session,
                                                sample_game_session, round3_finalists,
                                                grid_questions):
        """C-003 : le manager expose memory_grid_id pour que l'endpoint avance le tour."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        player = round3_finalists[0]

        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).first()
        question = db_session.query(Question).filter(Question.id == cell.question_id).first()

        memory_grid_manager.reveal_cell(round_obj.id, player.id, cell.id)
        result = memory_grid_manager.answer_cell(
            round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
            player_answer=question.correct_answer,
        )

        assert result["memory_grid_id"] == grid.id

    def test_advance_turn_does_not_commit(self, memory_grid_manager, db_session,
                                          sample_game_session, monkeypatch):
        """AD-5 : advance_turn ne doit que flush — l'appelant possède la transaction."""
        from app.memory_grid import MemoryGrid

        grid = MemoryGrid(game_session_id=sample_game_session.id, rows=7, cols=5, current_turn=0)
        db_session.add(grid)
        db_session.commit()

        commit_called = []
        monkeypatch.setattr(db_session, "commit", lambda: commit_called.append(True))

        result = memory_grid_manager.advance_turn(grid.id)

        assert result == 1
        assert grid.current_turn == 1  # visible dans la session (flush), sans commit
        assert commit_called == []  # advance_turn n'a pas appelé commit lui-même

    def test_check_completion_marks_grid_completed(self, memory_grid_manager, db_session,
                                                    sample_game_session, round3_finalists,
                                                    grid_questions):
        """C-003 : toutes les cellules répondues -> is_completed devient vrai."""
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        player = round3_finalists[0]

        cells = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).all()
        for cell in cells:
            memory_grid_manager.reveal_cell(round_obj.id, player.id, cell.id)
            question = db_session.query(Question).filter(Question.id == cell.question_id).first()
            memory_grid_manager.answer_cell(
                round_id=round_obj.id, player_id=player.id, cell_id=cell.id,
                player_answer=question.correct_answer,
            )
        db_session.commit()

        assert memory_grid_manager.check_completion(grid.id) is True
        db_session.commit()
        db_session.refresh(grid)
        assert grid.is_completed is True
