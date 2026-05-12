"""
Tests unitaires pour MemoryGridManager - Round 3 (Memory Grid)
Version consolidée avec tous les tests étendus et edge cases
"""
import pytest
import random
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound, GridCellStatus
from app.models import GameSession, Team, Player, Question, Theme, RoundType, Difficulty
from datetime import datetime

class TestMemoryGridManager:
    """Tests pour la classe MemoryGridManager."""
    
    def test_create_memory_grid_success(self, memory_grid_manager, db_session, sample_game_session, sample_team, sample_questions_for_theme):
        """Test création d'une grille mémoire 7x5."""
        team2 = Team(name="Team 2", game_session_id=sample_game_session.id, score=0)
        team3 = Team(name="Team 3", game_session_id=sample_game_session.id, score=0)
        team4 = Team(name="Team 4", game_session_id=sample_game_session.id, score=0)
        db_session.add_all([team2, team3, team4])
        db_session.commit()
        
        questions = []
        for i in range(11, 36):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty=Difficulty.EASY,
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        memory_grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        
        assert memory_grid is not None
        assert memory_grid.game_session_id == sample_game_session.id
        assert memory_grid.rows == 7
        assert memory_grid.cols == 5
        
        cells = db_session.query(GridCell).filter(GridCell.memory_grid_id == memory_grid.id).all()
        assert len(cells) == 35
        
    def test_create_memory_grid_no_teams(self, memory_grid_manager, db_session, sample_game_session):
        db_session.query(Team).filter(Team.game_session_id == sample_game_session.id).delete()
        db_session.commit()
        
        questions = []
        for i in range(35):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty=Difficulty.EASY,
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.create_memory_grid(
                game_session_id=sample_game_session.id,
                rows=7,
                cols=5
            )
        
        assert "No teams found for this game session" in str(exc_info.value)
        
    def test_create_memory_grid_insufficient_questions(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        db_session.query(Question).delete()
        db_session.commit()                
        
        questions = []
        for i in range(10):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty=Difficulty.EASY,
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        with pytest.raises(ValueError) as exc_info:
            memory_grid_manager.create_memory_grid(
                game_session_id=sample_game_session.id,
                rows=7,
                cols=5
            )
        
        assert "Not enough questions for the memory grid" in str(exc_info.value)
    
    def test_reveal_cell_success(self, memory_grid_manager, db_session, sample_game_session, sample_team, sample_questions_for_theme):
        team2 = Team(name="Team 2", game_session_id=sample_game_session.id, score=0)
        team3 = Team(name="Team 3", game_session_id=sample_game_session.id, score=0)
        team4 = Team(name="Team 4", game_session_id=sample_game_session.id, score=0)
        
        questions = []
        for i in range(11, 36):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty=Difficulty.EASY,
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all([team2, team3, team4] + questions)
        db_session.commit()
        
        memory_grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        
        memory_grid_round = memory_grid_manager.start_memory_grid_round(sample_game_session.id, memory_grid.id)
        
        cell = db_session.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid.id,
            GridCell.status == GridCellStatus.HIDDEN
        ).first()
        
        result = memory_grid_manager.reveal_cell(memory_grid_round.id, sample_team.id, cell.id)
        
        assert result is not None
        assert result["status"] == "cell_revealed"
        
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.REVEALED

    def test_answer_cell_not_revealed(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        team2 = Team(name="Team 2", game_session_id=sample_game_session.id, score=0)
        team3 = Team(name="Team 3", game_session_id=sample_game_session.id, score=0)
        team4 = Team(name="Team 4", game_session_id=sample_game_session.id, score=0)
        db_session.add_all([team2, team3, team4])
        db_session.commit()
        
        questions = [Question(text=f"Q{i}", category="T", difficulty=Difficulty.EASY, points=1, correct_answer="A", wrong_answers="[]", theme_id=None, question_number=i) for i in range(35)]
        db_session.add_all(questions)
        db_session.commit()
        
        grid = memory_grid_manager.create_memory_grid(
            game_session_id=sample_game_session.id, rows=7, cols=5
        )
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        
        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id).first()
        result = memory_grid_manager.answer_cell(round_id=round_obj.id, team_id=sample_team.id, cell_id=cell.id, is_correct=True)
        assert result == {"error": "Cell must be revealed before answering"}

    def test_answer_cell_stolen_points(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test that stealing a cell from another team awards 3 points."""
        # Setup another team
        team2 = Team(name="Team 2", game_session_id=sample_game_session.id, score=0)
        db_session.add(team2)
        db_session.commit()
        
        # Create questions
        questions = [Question(text=f"Q{i}", category="T", difficulty=Difficulty.EASY, points=1, correct_answer="A", wrong_answers="[]", theme_id=None, question_number=i) for i in range(35)]
        db_session.add_all(questions)
        db_session.commit()

        # Create grid with a cell assigned to Team 2
        grid = memory_grid_manager.create_memory_grid(game_session_id=sample_game_session.id, rows=7, cols=5)
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, grid.id)
        
        # Find cell assigned to Team 2
        cell = db_session.query(GridCell).filter(GridCell.memory_grid_id == grid.id, GridCell.assigned_team_id == team2.id).first()
        
        # Reveal and answer with Sample Team (Stealing)
        memory_grid_manager.reveal_cell(round_obj.id, sample_team.id, cell.id)
        result = memory_grid_manager.answer_cell(round_id=round_obj.id, team_id=sample_team.id, cell_id=cell.id, is_correct=True)
        
        assert result["status"] == "answered"
        assert result["points_awarded"] == 3
        assert result["cell_type"] == "stolen"
        assert sample_team.score == 3
