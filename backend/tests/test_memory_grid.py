"""
Tests unitaires pour MemoryGridManager - Round 3 (Memory Grid)
"""
import pytest
import random
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound, GridCellStatus
from app.models import GameSession, Team, Player, Question, Theme, RoundType
from datetime import datetime

class TestMemoryGridManager:
    """Tests pour la classe MemoryGridManager."""
    
    def test_create_memory_grid_success(self, memory_grid_manager, db_session, sample_game_session, sample_team, sample_questions_for_theme):
        """Test création d'une grille mémoire 7x5."""
        # Créer plusieurs équipes pour le test
        team2 = Team(
            name="Team 2",
            game_session_id=sample_game_session.id,
            score=0
        )
        team3 = Team(
            name="Team 3",
            game_session_id=sample_game_session.id,
            score=0
        )
        team4 = Team(
            name="Team 4",
            game_session_id=sample_game_session.id,
            score=0
        )
        db_session.add_all([team2, team3, team4])
        db_session.commit()
        
        # Créer plus de questions pour remplir la grille 7x5 (35 cellules)
        questions = []
        for i in range(11, 36):  # On a déjà 10 questions de sample_questions_for_theme
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty="EASY",
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        # Créer la grille mémoire
        memory_grid = memory_grid_manager.create_memory_grid(sample_game_session.id, rows=7, cols=5)
        
        assert memory_grid is not None
        assert memory_grid.game_session_id == sample_game_session.id
        assert memory_grid.rows == 7
        assert memory_grid.cols == 5
        assert memory_grid.current_turn == 0
        assert memory_grid.is_completed == False
        
        # Vérifier que toutes les cellules sont créées
        cells = db_session.query(GridCell).filter(GridCell.memory_grid_id == memory_grid.id).all()
        assert len(cells) == 35  # 7x5 = 35 cellules
        
        # Vérifier que chaque cellule a une position unique
        positions = [(cell.row, cell.col) for cell in cells]
        assert len(set(positions)) == 35  # Toutes les positions sont uniques
        
        # Vérifier que 20 cellules sont assignées à des équipes (5 par équipe x 4 équipes)
        assigned_cells = [cell for cell in cells if cell.assigned_team_id is not None]
        assert len(assigned_cells) == 20
        
        # Vérifier que 15 cellules ne sont pas assignées
        unassigned_cells = [cell for cell in cells if cell.assigned_team_id is None]
        assert len(unassigned_cells) == 15
        
        # Vérifier que chaque équipe a exactement 5 cellules assignées
        team_ids = [sample_team.id, team2.id, team3.id, team4.id]
        for team_id in team_ids:
            team_cells = [cell for cell in cells if cell.assigned_team_id == team_id]
            assert len(team_cells) == 5
    
    def test_create_memory_grid_no_teams(self, memory_grid_manager, db_session, sample_game_session):
        """Test création d'une grille mémoire sans équipes."""
        # Supprimer toutes les équipes
        db_session.query(Team).delete()
        db_session.commit()
        
        with pytest.raises(ValueError, match="No teams found for this game session"):
            memory_grid_manager.create_memory_grid(sample_game_session.id)
    
    def test_create_memory_grid_insufficient_questions(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test création d'une grille mémoire avec pas assez de questions."""
        # Créer seulement 10 questions (besoin de 35)
        db_session.query(Question).delete()
        db_session.commit()
        
        questions = []
        for i in range(1, 11):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty="EASY",
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        with pytest.raises(ValueError, match="Not enough questions for the memory grid"):
            memory_grid_manager.create_memory_grid(sample_game_session.id)
    
    def test_start_memory_grid_round(self, memory_grid_manager, db_session, sample_game_session):
        """Test démarrage d'un tour de grille mémoire."""
        # Créer une grille mémoire d'abord
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Démarrer un tour
        round_obj = memory_grid_manager.start_memory_grid_round(sample_game_session.id, memory_grid.id)
        
        assert round_obj is not None
        assert round_obj.game_session_id == sample_game_session.id
        assert round_obj.memory_grid_id == memory_grid.id
        assert round_obj.is_active == True
    
    def test_reveal_cell_success(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test révélation d'une cellule."""
        # Créer une grille mémoire avec une cellule
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.HIDDEN,
            assigned_team_id=sample_team.id
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Révéler la cellule
        result = memory_grid_manager.reveal_cell(round_obj.id, sample_team.id, cell.id)
        
        assert result is not None
        assert "error" not in result
        assert result["status"] == "cell_revealed"
        assert result["cell"]["id"] == cell.id
        assert result["cell"]["row"] == 0
        assert result["cell"]["col"] == 0
        assert result["cell"]["question"]["id"] == question.id
        
        # Vérifier que la cellule est maintenant révélée
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.REVEALED
    
    def test_reveal_cell_already_revealed(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test révélation d'une cellule déjà révélée."""
        # Créer une grille mémoire avec une cellule déjà révélée
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule déjà révélée
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=sample_team.id
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Essayer de révéler la cellule déjà révélée
        result = memory_grid_manager.reveal_cell(round_obj.id, sample_team.id, cell.id)
        
        assert result is not None
        assert "error" in result
        assert result["error"] == "Cell already revealed or answered"
    
    def test_reveal_cell_invalid_ids(self, memory_grid_manager, db_session):
        """Test révélation avec des IDs invalides."""
        result = memory_grid_manager.reveal_cell(999, 999, 999)
        assert result is None
    
    def test_answer_cell_correct_own_theme(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test réponse correcte à une cellule de son propre thème."""
        # Créer une grille mémoire avec une cellule révélée
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule révélée assignée à l'équipe
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=sample_team.id,
            answered_by_team_id=None
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Répondre correctement (son propre thème)
        result = memory_grid_manager.answer_cell(round_obj.id, sample_team.id, cell.id, True)
        
        assert result is not None
        assert "error" not in result
        assert result["status"] == "answered"
        assert result["is_correct"] == True
        assert result["points_awarded"] == 2  # Own theme: 2 points
        assert result["cell_type"] == "own_theme"
        
        # Vérifier que la cellule est maintenant répondue
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.ANSWERED
        assert cell.answered_by_team_id == sample_team.id
        
        # Vérifier que l'équipe a reçu les points
        db_session.refresh(sample_team)
        assert sample_team.score == 2
    
    def test_answer_cell_correct_stolen(self, memory_grid_manager, db_session, sample_game_session):
        """Test réponse correcte à une cellule volée (thème d'une autre équipe)."""
        # Créer deux équipes
        team1 = Team(
            name="Team 1",
            game_session_id=sample_game_session.id,
            score=0
        )
        team2 = Team(
            name="Team 2",
            game_session_id=sample_game_session.id,
            score=0
        )
        db_session.add_all([team1, team2])
        db_session.commit()
        db_session.refresh(team1)
        db_session.refresh(team2)
        
        # Créer une grille mémoire
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule révélée assignée à team1, mais team2 répond
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=team1.id,
            answered_by_team_id=None
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Team2 répond correctement (voler la cellule)
        result = memory_grid_manager.answer_cell(round_obj.id, team2.id, cell.id, True)
        
        assert result is not None
        assert "error" not in result
        assert result["status"] == "answered"
        assert result["is_correct"] == True
        assert result["points_awarded"] == 3  # Stolen cell: 3 points
        assert result["cell_type"] == "stolen"
        
        # Vérifier que la cellule est maintenant répondue par team2
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.ANSWERED
        assert cell.answered_by_team_id == team2.id
        
        # Vérifier que team2 a reçu les points
        db_session.refresh(team2)
        assert team2.score == 3
        
        # Vérifier que team1 n'a pas reçu de points
        db_session.refresh(team1)
        assert team1.score == 0
    
    def test_answer_cell_correct_unassigned(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test réponse correcte à une cellule non assignée."""
        # Créer une grille mémoire avec une cellule révélée non assignée
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule révélée non assignée
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=None,
            answered_by_team_id=None
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Répondre correctement (cellule non assignée)
        result = memory_grid_manager.answer_cell(round_obj.id, sample_team.id, cell.id, True)
        
        assert result is not None
        assert "error" not in result
        assert result["status"] == "answered"
        assert result["is_correct"] == True
        assert result["points_awarded"] == 1  # Unassigned cell: 1 point
        assert result["cell_type"] == "unassigned"
        
        # Vérifier que la cellule est maintenant répondue
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.ANSWERED
        assert cell.answered_by_team_id == sample_team.id
        
        # Vérifier que l'équipe a reçu les points
        db_session.refresh(sample_team)
        assert sample_team.score == 1
    
    def test_answer_cell_incorrect(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test réponse incorrecte à une cellule."""
        # Créer une grille mémoire avec une cellule révélée
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule révélée
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=sample_team.id,
            answered_by_team_id=None
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Répondre incorrectement
        result = memory_grid_manager.answer_cell(round_obj.id, sample_team.id, cell.id, False)
        
        assert result is not None
        assert "error" not in result
        assert result["status"] == "answered"
        assert result["is_correct"] == False
        assert result["points_awarded"] == 0  # Incorrect: 0 points
        assert result["cell_type"] == "own_theme"
        
        # Vérifier que la cellule est maintenant répondue
        db_session.refresh(cell)
        assert cell.status == GridCellStatus.ANSWERED
        assert cell.answered_by_team_id == sample_team.id
        
        # Vérifier que l'équipe n'a pas reçu de points
        db_session.refresh(sample_team)
        assert sample_team.score == 0
    
    def test_answer_cell_not_revealed(self, memory_grid_manager, db_session, sample_game_session, sample_team):
        """Test réponse à une cellule non révélée."""
        # Créer une grille mémoire avec une cellule cachée
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer une cellule cachée
        cell = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.HIDDEN,
            assigned_team_id=sample_team.id,
            answered_by_team_id=None
        )
        db_session.add(cell)
        db_session.commit()
        db_session.refresh(cell)
        
        # Démarrer un tour
        round_obj = MemoryGridRound(
            game_session_id=sample_game_session.id,
            memory_grid_id=memory_grid.id,
            is_active=True
        )
        db_session.add(round_obj)
        db_session.commit()
        db_session.refresh(round_obj)
        
        # Essayer de répondre à une cellule cachée
        result = memory_grid_manager.answer_cell(round_obj.id, sample_team.id, cell.id, True)
        
        assert result is not None
        assert "error" in result
        assert result["error"] == "Cell must be revealed before answering"
    
    def test_get_grid_state(self, memory_grid_manager, db_session, sample_game_session):
        """Test récupération de l'état de la grille."""
        # Créer une grille mémoire avec des cellules
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=7,
            cols=5
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer une question
        question = Question(
            text="Test question",
            category="Test",
            difficulty="EASY",
            points=2,
            correct_answer="Answer",
            wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
            theme_id=None,
            question_number=1
        )
        db_session.add(question)
        db_session.commit()
        db_session.refresh(question)
        
        # Créer quelques cellules avec différents états
        cell1 = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=0,
            question_id=question.id,
            status=GridCellStatus.HIDDEN,
            assigned_team_id=None,
            answered_by_team_id=None
        )
        
        cell2 = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=1,
            question_id=question.id,
            status=GridCellStatus.REVEALED,
            assigned_team_id=1,
            answered_by_team_id=None
        )
        
        cell3 = GridCell(
            memory_grid_id=memory_grid.id,
            row=0,
            col=2,
            question_id=question.id,
            status=GridCellStatus.ANSWERED,
            assigned_team_id=1,
            answered_by_team_id=2
        )
        
        db_session.add_all([cell1, cell2, cell3])
        db_session.commit()
        
        # Récupérer l'état de la grille
        grid_state = memory_grid_manager.get_grid_state(memory_grid.id)
        
        assert grid_state is not None
        assert "memory_grid" in grid_state
        assert "cells" in grid_state
        
        memory_grid_info = grid_state["memory_grid"]
        assert memory_grid_info["id"] == memory_grid.id
        assert memory_grid_info["rows"] == 7
        assert memory_grid_info["cols"] == 5
        assert memory_grid_info["current_turn"] == 0
        assert memory_grid_info["is_completed"] == False
        
        cells = grid_state["cells"]
        assert len(cells) == 3
        
        # Vérifier les détails des cellules
        for cell_info in cells:
            assert "id" in cell_info
            assert "row" in cell_info
            assert "col" in cell_info
            assert "status" in cell_info
            assert "assigned_team_id" in cell_info
            assert "answered_by_team_id" in cell_info
            
            # Vérifier que les questions ne sont visibles que pour les cellules révélées/répondue
            if cell_info["status"] != GridCellStatus.HIDDEN.value:
                assert "question" in cell_info
                question_data = cell_info["question"]
                assert "id" in question_data
                assert "text" in question_data
                assert "category" in question_data
                
                if cell_info["status"] == GridCellStatus.ANSWERED.value:
                    assert "correct_answer" in question_data
                else:
                    assert question_data.get("correct_answer") is None
            else:
                assert "question" not in cell_info
    
    def test_get_grid_state_not_found(self, memory_grid_manager):
        """Test récupération de l'état d'une grille inexistante."""
        grid_state = memory_grid_manager.get_grid_state(999)
        assert grid_state is None
    
    def test_check_game_completion_all_answered(self, memory_grid_manager, db_session, sample_game_session):
        """Test vérification de complétion du jeu quand toutes les cellules sont répondue."""
        # Créer une grille mémoire 2x2 pour simplifier
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=2,
            cols=2
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer des questions
        questions = []
        for i in range(4):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty="EASY",
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        # Créer 4 cellules répondue
        cells = []
        for i in range(4):
            cell = GridCell(
                memory_grid_id=memory_grid.id,
                row=i // 2,
                col=i % 2,
                question_id=questions[i].id,
                status=GridCellStatus.ANSWERED,
                assigned_team_id=None,
                answered_by_team_id=1
            )
            cells.append(cell)
        
        db_session.add_all(cells)
        db_session.commit()
        
        # Vérifier que le jeu est complété
        is_completed = memory_grid_manager.check_game_completion(memory_grid.id)
        assert is_completed == True
        
        # Vérifier que la grille est marquée comme complétée
        db_session.refresh(memory_grid)
        assert memory_grid.is_completed == True
    
    def test_check_game_completion_not_all_answered(self, memory_grid_manager, db_session, sample_game_session):
        """Test vérification de complétion du jeu quand toutes les cellules ne sont pas répondue."""
        # Créer une grille mémoire 2x2
        memory_grid = MemoryGrid(
            game_session_id=sample_game_session.id,
            rows=2,
            cols=2
        )
        db_session.add(memory_grid)
        db_session.commit()
        db_session.refresh(memory_grid)
        
        # Créer des questions
        questions = []
        for i in range(4):
            question = Question(
                text=f"Test question {i}",
                category="Test",
                difficulty="EASY",
                points=2,
                correct_answer=f"Answer {i}",
                wrong_answers='["Wrong 1", "Wrong 2", "Wrong 3"]',
                theme_id=None,
                question_number=i
            )
            questions.append(question)
        
        db_session.add_all(questions)
        db_session.commit()
        
        # Créer 2 cellules répondue et 2 cachées
        cells = []
        for i in range(4):
            status = GridCellStatus.ANSWERED if i < 2 else GridCellStatus.HIDDEN
            cell = GridCell(
                memory_grid_id=memory_grid.id,
                row=i // 2,
                col=i % 2,
                question_id=questions[i].id,
                status=status,
                assigned_team_id=None,
                answered_by_team_id=1 if i < 2 else None
            )
            cells.append(cell)
        
        db_session.add_all(cells)
        db_session.commit()
        
        # Vérifier que le jeu n'est pas complété
        is_completed = memory_grid_manager.check_game_completion(memory_grid.id)
        assert is_completed == False
        
        # Vérifier que la grille n'est pas marquée comme complétée
        db_session.refresh(memory_grid)
        assert memory_grid.is_completed == False
    
    def test_check_game_completion_grid_not_found(self, memory_grid_manager):
        """Test vérification de complétion pour une grille inexistante."""
        is_completed = memory_grid_manager.check_game_completion(999)
        assert is_completed == False