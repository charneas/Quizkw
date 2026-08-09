"""
Tests Manche 3 « enhanced » : finalistes, tours, couleurs, thèmes, grille à thèmes.

Réécrits sur la VRAIE base en mémoire (convention de la spine : SQLite mémoire,
rollback par test) au lieu de MagicMock(spec=Session). Les mocks masquaient le
modèle réel, et c'est précisément ce modèle qui vient de changer :

AD-0 : la Manche 3 est individuelle — 4 finalistes, jamais des équipes.
AD-1 : le score de Manche 3 vit sur PlayerRound3Stats.
AD-5 : le manager ne commit pas ; les tests committent.
"""
import pytest

from app.memory_grid import MemoryGridManager, GridCell
from app.models import PlayerRound3Stats, Question, Difficulty


class TestFinalistSelection:
    """AD-0 : qui joue la Manche 3."""

    def test_finalists_are_top_four_by_round2_score(self, memory_grid_manager,
                                                    sample_game_session, round3_finalists):
        finalists = memory_grid_manager.get_finalists_from_round2(sample_game_session.id)

        assert len(finalists) == MemoryGridManager.FINALIST_COUNT
        assert finalists == [p.id for p in round3_finalists]

    def test_finalists_without_round2_results_raises(self, memory_grid_manager,
                                                     sample_game_session):
        with pytest.raises(LookupError):
            memory_grid_manager.get_finalists_from_round2(sample_game_session.id)


class TestTurnRotation:
    """Le tourniquet sur les 4 finalistes."""

    def test_turn_rotates_through_finalists(self, memory_grid_manager, db_session,
                                            sample_game_session, round3_finalists,
                                            grid_questions):
        grid = memory_grid_manager.create_memory_grid(sample_game_session.id, rows=7, cols=5)
        ranking = [p.id for p in round3_finalists]

        seen = []
        for _ in range(len(ranking) + 1):
            seen.append(memory_grid_manager.get_current_player_turn(grid.id, ranking))
            grid.current_turn += 1
            db_session.commit()

        # Un tour complet, puis retour au premier
        assert seen[:4] == ranking
        assert seen[4] == ranking[0]

    def test_turn_without_ranking_is_none(self, memory_grid_manager, db_session,
                                          sample_game_session, round3_finalists,
                                          grid_questions):
        grid = memory_grid_manager.create_memory_grid(sample_game_session.id, rows=7, cols=5)

        assert memory_grid_manager.get_current_player_turn(grid.id, []) is None
        assert memory_grid_manager.get_current_player_turn(999999, [1, 2]) is None


class TestPlayerColors:
    """AD-0 : les couleurs appartiennent aux finalistes."""

    def test_select_color_persists_on_round3_stats(self, memory_grid_manager, db_session,
                                                   sample_game_session, round3_finalists):
        player = round3_finalists[0]

        result = memory_grid_manager.select_player_color(
            sample_game_session.id, player.id, "red"
        )
        db_session.commit()

        assert result["success"] is True
        assert result["player_id"] == player.id
        assert result["color"] == "red"

        stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == player.id,
            PlayerRound3Stats.game_session_id == sample_game_session.id,
        ).first()
        assert stats.color == "red"

    def test_duplicate_color_is_rejected(self, memory_grid_manager, db_session,
                                         sample_game_session, round3_finalists):
        first, second = round3_finalists[0], round3_finalists[1]

        memory_grid_manager.select_player_color(sample_game_session.id, first.id, "blue")
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.select_player_color(sample_game_session.id, second.id, "blue")

        assert "déjà prise" in str(exc_info.value)

    def test_same_player_can_reselect_its_own_colour(self, memory_grid_manager, db_session,
                                                     sample_game_session, round3_finalists):
        player = round3_finalists[0]

        memory_grid_manager.select_player_color(sample_game_session.id, player.id, "green")
        db_session.commit()
        result = memory_grid_manager.select_player_color(sample_game_session.id, player.id, "green")
        db_session.commit()

        assert result["success"] is True

    def test_invalid_colour_is_rejected(self, memory_grid_manager, sample_game_session,
                                        round3_finalists):
        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.select_player_color(
                sample_game_session.id, round3_finalists[0].id, "#FF5733"
            )

        assert "invalide" in str(exc_info.value).lower()

    def test_taken_colour_leaves_the_available_palette(self, memory_grid_manager, db_session,
                                                       sample_game_session, round3_finalists):
        before = memory_grid_manager.get_available_colors(sample_game_session.id)
        assert "red" in before

        memory_grid_manager.select_player_color(
            sample_game_session.id, round3_finalists[0].id, "red"
        )
        db_session.commit()

        after = memory_grid_manager.get_available_colors(sample_game_session.id)
        assert "red" not in after
        assert len(after) == len(before) - 1


class TestPlayerThemes:
    """AD-0 : chaque finaliste choisit ses 3 thèmes."""

    def test_select_three_themes_persists(self, memory_grid_manager, db_session,
                                          sample_game_session, round3_finalists):
        player = round3_finalists[0]

        result = memory_grid_manager.select_player_themes(
            sample_game_session.id, player.id, [1, 2, 3]
        )
        db_session.commit()

        assert result["success"] is True

        stats = db_session.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.player_id == player.id
        ).first()
        assert stats.selected_theme_ids == [1, 2, 3]

    @pytest.mark.parametrize("theme_ids", [[1, 2], [1, 2, 3, 4], []])
    def test_theme_count_must_be_exactly_three(self, memory_grid_manager, sample_game_session,
                                               round3_finalists, theme_ids):
        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.select_player_themes(
                sample_game_session.id, round3_finalists[0].id, theme_ids
            )

        assert "3 thèmes" in str(exc_info.value)


class TestGridWithThemes:
    """La variante de grille bâtie sur les thèmes choisis."""

    def _seed_hard_questions(self, db_session, count=40):
        questions = [
            Question(text=f"Difficile {i}", category="T", difficulty=Difficulty.HARD,
                     points=6, correct_answer=f"R{i}", wrong_answers="[]",
                     theme_id=None, question_number=i)
            for i in range(500, 500 + count)
        ]
        db_session.add_all(questions)
        db_session.commit()
        return questions

    def test_requires_every_finalist_to_have_chosen_themes(self, memory_grid_manager, db_session,
                                                           sample_game_session, round3_finalists):
        self._seed_hard_questions(db_session)

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.create_memory_grid_with_themes(sample_game_session.id)

        assert "thèmes" in str(exc_info.value)

    def test_creates_grid_assigning_five_cells_per_finalist(self, memory_grid_manager, db_session,
                                                            sample_game_session, round3_finalists):
        self._seed_hard_questions(db_session)

        # BUG-302 : les thèmes sont désormais exclusifs entre finalistes
        # (select_player_themes rejette un conflit), chaque finaliste doit
        # donc choisir un triplet distinct.
        for i, player in enumerate(round3_finalists):
            memory_grid_manager.select_player_themes(
                sample_game_session.id, player.id, [i * 3 + 1, i * 3 + 2, i * 3 + 3]
            )
        db_session.commit()

        grid = memory_grid_manager.create_memory_grid_with_themes(sample_game_session.id)
        db_session.commit()

        cells = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).all()
        assert len(cells) == 35

        for player in round3_finalists:
            owned = [c for c in cells if c.assigned_player_id == player.id]
            assert len(owned) == 5

    def test_insufficient_hard_questions_raises(self, memory_grid_manager, db_session,
                                                sample_game_session, round3_finalists):
        self._seed_hard_questions(db_session, count=5)

        for i, player in enumerate(round3_finalists):
            memory_grid_manager.select_player_themes(
                sample_game_session.id, player.id, [i * 3 + 1, i * 3 + 2, i * 3 + 3]
            )
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.create_memory_grid_with_themes(sample_game_session.id)

        assert "Not enough difficult questions" in str(exc_info.value)
