from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLAlchemyEnum, JSON
from sqlalchemy.orm import relationship
from app.models import Base, Question, Team
import enum

class GridCellStatus(enum.Enum):
    HIDDEN = "hidden"
    REVEALED = "revealed"
    ANSWERED = "answered"

class MemoryGrid(Base):
    __tablename__ = "memory_grids"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    rows = Column(Integer, default=7)  # 7 rows
    cols = Column(Integer, default=5)  # 5 columns
    current_turn = Column(Integer, default=0)  # Track turns
    is_completed = Column(Boolean, default=False)
    
    game_session = relationship("GameSession")
    cells = relationship("GridCell", back_populates="memory_grid")

class GridCell(Base):
    __tablename__ = "grid_cells"
    
    id = Column(Integer, primary_key=True, index=True)
    memory_grid_id = Column(Integer, ForeignKey("memory_grids.id"))
    row = Column(Integer)
    col = Column(Integer)
    question_id = Column(Integer, ForeignKey("questions.id"))
    status = Column(SQLAlchemyEnum(GridCellStatus), default=GridCellStatus.HIDDEN)
    assigned_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)  # Which team owns this cell initially
    answered_by_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)  # Which team answered it
    
    memory_grid = relationship("MemoryGrid", back_populates="cells")
    question = relationship("Question")
    assigned_team = relationship("Team", foreign_keys=[assigned_team_id])
    answered_by_team = relationship("Team", foreign_keys=[answered_by_team_id])

class MemoryGridRound(Base):
    __tablename__ = "memory_grid_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    memory_grid_id = Column(Integer, ForeignKey("memory_grids.id"))
    current_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    
    game_session = relationship("GameSession")
    memory_grid = relationship("MemoryGrid")
    current_team = relationship("Team")

# Memory grid logic
class MemoryGridManager:
    def __init__(self, db):
        self.db = db
    
    def create_memory_grid(self, game_session_id, rows=7, cols=5):
        """Create a new memory grid for the final round (7x5 grid)"""
        memory_grid = MemoryGrid(
            game_session_id=game_session_id,
            rows=rows,
            cols=cols
        )
        self.db.add(memory_grid)
        self.db.commit()
        self.db.refresh(memory_grid)
        
        # Get all teams for this game session
        teams = self.db.query(Team).filter(Team.game_session_id == game_session_id).all()
        if not teams:
            raise ValueError("No teams found for this game session")
        
        # Get questions for the grid
        questions = self.db.query(Question).all()
        total_cells = rows * cols
        
        if len(questions) < total_cells:
            raise ValueError(f"Not enough questions for the memory grid. Need {total_cells}, have {len(questions)}")
        
        # Shuffle questions
        import random
        random.shuffle(questions)
        
        # Create grid cells
        cells = []
        question_index = 0
        
        # Assign 5 cells per team (their color/theme)
        cells_per_team = 5
        assigned_cells = []
        
        # Assign cells to teams
        for team in teams:
            for _ in range(cells_per_team):
                if question_index >= len(questions):
                    break
                
                # Find an unassigned cell position
                while True:
                    row = random.randint(0, rows - 1)
                    col = random.randint(0, cols - 1)
                    position = (row, col)
                    if position not in assigned_cells:
                        assigned_cells.append(position)
                        break
                
                cell = GridCell(
                    memory_grid_id=memory_grid.id,
                    row=row,
                    col=col,
                    question_id=questions[question_index].id,
                    status=GridCellStatus.HIDDEN,
                    assigned_team_id=team.id
                )
                cells.append(cell)
                question_index += 1
        
        # Fill remaining cells with unassigned questions
        for row in range(rows):
            for col in range(cols):
                if (row, col) not in assigned_cells:
                    if question_index < len(questions):
                        cell = GridCell(
                            memory_grid_id=memory_grid.id,
                            row=row,
                            col=col,
                            question_id=questions[question_index].id,
                            status=GridCellStatus.HIDDEN,
                            assigned_team_id=None  # Unassigned cell
                        )
                        cells.append(cell)
                        question_index += 1
                    else:
                        # If we run out of questions, use a random one
                        random_question = random.choice(questions)
                        cell = GridCell(
                            memory_grid_id=memory_grid.id,
                            row=row,
                            col=col,
                            question_id=random_question.id,
                            status=GridCellStatus.HIDDEN,
                            assigned_team_id=None
                        )
                        cells.append(cell)
        
        self.db.add_all(cells)
        self.db.commit()
        
        return memory_grid
    
    def start_memory_grid_round(self, game_session_id, memory_grid_id):
        """Start the memory grid round"""
        round_obj = MemoryGridRound(
            game_session_id=game_session_id,
            memory_grid_id=memory_grid_id
        )
        self.db.add(round_obj)
        self.db.commit()
        self.db.refresh(round_obj)
        return round_obj
    
    def reveal_cell(self, round_id, team_id, cell_id):
        """Reveal a cell in the memory grid"""
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        
        if not round_obj or not cell:
            return None
        
        # Check if cell is already revealed or answered
        if cell.status != GridCellStatus.HIDDEN:
            return {"error": "Cell already revealed or answered"}
        
        # Reveal the cell
        cell.status = GridCellStatus.REVEALED
        self.db.commit()
        
        return {
            "status": "cell_revealed",
            "cell": {
                "id": cell.id,
                "row": cell.row,
                "col": cell.col,
                "question": {
                    "id": cell.question.id,
                    "text": cell.question.text,
                    "category": cell.question.category,
                    "correct_answer": cell.question.correct_answer
                },
                "assigned_team_id": cell.assigned_team_id
            }
        }
    
    def answer_cell(self, round_id, team_id, cell_id, is_correct):
        """Answer a revealed cell"""
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        
        if not round_obj or not cell:
            return None
        
        # Check if cell is revealed but not answered
        if cell.status != GridCellStatus.REVEALED:
            return {"error": "Cell must be revealed before answering"}
        
        # Calculate points based on cell assignment
        points = 0
        if is_correct:
            if cell.assigned_team_id is None:
                # Unassigned cell: 1 point
                points = 1
            elif cell.assigned_team_id == team_id:
                # Own theme cell: 2 points
                points = 2
            else:
                # Stolen cell (other team's theme): 3 points
                points = 3
        
        # Update cell status and record answer
        cell.status = GridCellStatus.ANSWERED
        cell.answered_by_team_id = team_id
        
        # Award points to the team
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if team:
            team.score += points
        
        self.db.commit()
        
        # Check if game is completed
        self.check_game_completion(round_obj.memory_grid_id)
        
        return {
            "status": "answered",
            "is_correct": is_correct,
            "points_awarded": points,
            "team_score": team.score if team else 0,
            "cell_type": "stolen" if cell.assigned_team_id and cell.assigned_team_id != team_id else 
                         "own_theme" if cell.assigned_team_id == team_id else "unassigned"
        }
    
    def get_grid_state(self, memory_grid_id):
        """Get the current state of the memory grid"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None
        
        cells = self.db.query(GridCell).filter(GridCell.memory_grid_id == memory_grid_id).all()
        
        grid_state = []
        for cell in cells:
            cell_info = {
                "id": cell.id,
                "row": cell.row,
                "col": cell.col,
                "status": cell.status.value,
                "assigned_team_id": cell.assigned_team_id,
                "answered_by_team_id": cell.answered_by_team_id
            }
            
            # Only show question details if cell is revealed or answered
            if cell.status != GridCellStatus.HIDDEN:
                cell_info["question"] = {
                    "id": cell.question.id,
                    "text": cell.question.text,
                    "category": cell.question.category,
                    "correct_answer": cell.question.correct_answer if cell.status == GridCellStatus.ANSWERED else None
                }
            
            grid_state.append(cell_info)
        
        return {
            "memory_grid": {
                "id": memory_grid.id,
                "rows": memory_grid.rows,
                "cols": memory_grid.cols,
                "current_turn": memory_grid.current_turn,
                "is_completed": memory_grid.is_completed
            },
            "cells": grid_state
        }
    
    def check_game_completion(self, memory_grid_id):
        """Check if all cells have been answered"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return False
        
        total_cells = memory_grid.rows * memory_grid.cols
        answered_cells = self.db.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid_id,
            GridCell.status == GridCellStatus.ANSWERED
        ).count()
        
        if answered_cells == total_cells:
            memory_grid.is_completed = True
            self.db.commit()
            return True
        
        return False
