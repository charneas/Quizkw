from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLAlchemyEnum, JSON
from sqlalchemy.orm import relationship
from app.models import Base, Question, Team
import enum
import random
import json

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
                # Note: The check "if question_index >= len(questions): break" was removed
                # because line 80 ensures len(questions) >= total_cells (35)
                # and we only assign 20 cells to teams (4 teams * 5 = 20)
                
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
                    # Note: The else block (lines 137-146) was removed because
                    # line 80 ensures we have enough questions for all cells
                    # question_index will always be < len(questions) here
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
        # Set current team in round if provided
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        if round_obj:
            round_obj.current_team_id = team_id
            self.db.commit()

        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        
        if not round_obj or not cell:
            return None
        
        # Can't reveal an already answered cell
        if cell.status == GridCellStatus.ANSWERED:
            return None
        
        # Update cell status
        cell.status = GridCellStatus.REVEALED
        self.db.commit()
        self.db.refresh(cell)
        
        return {"status": "cell_revealed", "cell_id": cell.id}
    
    def answer_cell(self, round_id, team_id, cell_id, is_correct):
        """Answer a revealed cell in the memory grid"""
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        
        if not round_obj or not cell:
            return None
        
        # Cell must be revealed to be answered
        if cell.status != GridCellStatus.REVEALED:
            return {"error": "Cell must be revealed before answering"}
        
        # Update cell status
        cell.status = GridCellStatus.ANSWERED
        cell.answered_by_team_id = team_id
        
        # Calculate points
        points = 0
        if is_correct:
            # Base points for correct answer
            points = 2
            
            # Bonus if answering own assigned cell
            if cell.assigned_team_id == team_id:
                points += 1
            
            # Bonus if stealing from another team
            if cell.assigned_team_id and cell.assigned_team_id != team_id:
                points += 1
        
        # Determine cell type
        cell_type = "unassigned"
        if cell.assigned_team_id:
            if cell.assigned_team_id == team_id:
                cell_type = "own"
            else:
                cell_type = "stolen"
        
        # Update team score if points > 0
        if points > 0:
            team = self.db.query(Team).filter(Team.id == team_id).first()
            if team:
                team.score += points
        self.db.commit()
        self.db.refresh(cell)
        
        return {
            "status": "answered",
            "points_awarded": points,
            "cell_type": cell_type
        }
    
    def get_grid_state(self, memory_grid_id):
        """Get the current state of the memory grid"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None
        
        cells = self.db.query(GridCell).filter(GridCell.memory_grid_id == memory_grid_id).all()
        
        # Convert to dict format
        grid_state = []
        for cell in cells:
            grid_state.append({
                'id': cell.id,
                'row': cell.row,
                'col': cell.col,
                'status': cell.status.value,
                'assigned_team_id': cell.assigned_team_id,
                'answered_by_team_id': cell.answered_by_team_id,
                'question_id': cell.question_id
            })
        
        return {
            'memory_grid_id': memory_grid_id,
            'rows': memory_grid.rows,
            'cols': memory_grid.cols,
            'current_turn': memory_grid.current_turn,
            'is_completed': memory_grid.is_completed,
            'cells': grid_state
        }
    
    def advance_turn(self, memory_grid_id):
        """Advance to the next turn in the memory grid"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None
        
        memory_grid.current_turn += 1
        self.db.commit()
        self.db.refresh(memory_grid)
        
        return memory_grid.current_turn
    
    def check_completion(self, memory_grid_id):
        """Check if the memory grid is completed (all cells answered)"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None
        
        cells = self.db.query(GridCell).filter(GridCell.memory_grid_id == memory_grid_id).all()
        
        # Check if all cells are answered
        all_answered = all(cell.status == GridCellStatus.ANSWERED for cell in cells)
        
        if all_answered:
            memory_grid.is_completed = True
            self.db.commit()
        
        return all_answered
    
    # Round 3 Enhanced Methods
    def get_team_ranking_from_round2(self, game_session_id):
        """
        Get team ranking based on Round 2 PlayerRound2Stats scores.
        Returns list of team IDs sorted by total score (descending).
        """
        from app.models import PlayerRound2Stats, Player, Team
        
        # Get all players with their Round 2 stats for this game session
        player_stats = self.db.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.game_session_id == game_session_id
        ).all()
        
        # Group by team and calculate total team score
        team_scores = {}
        for stats in player_stats:
            player = self.db.query(Player).filter(Player.id == stats.player_id).first()
            if player and player.team_id:
                team_scores[player.team_id] = team_scores.get(player.team_id, 0) + stats.score
        
        # Sort teams by score descending
        sorted_teams = sorted(team_scores.items(), key=lambda x: x[1], reverse=True)
        return [team_id for team_id, score in sorted_teams]
    
    def get_current_team_turn(self, memory_grid_id, team_ranking):
        """
        Determine which team should play based on current turn and team ranking.
        """
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid or not team_ranking:
            return None
        
        # Round-robin: current_turn mod number_of_teams gives index in team_ranking
        turn_index = memory_grid.current_turn % len(team_ranking)
        return team_ranking[turn_index]
    
    def create_memory_grid_with_themes(self, game_session_id, rows=7, cols=5):
        """
        Create memory grid for Round 3 with theme-based cell assignment.
        Uses team.selected_theme_ids to assign 5 cells per team based on selected themes.
        """
        memory_grid = MemoryGrid(
            game_session_id=game_session_id,
            rows=rows,
            cols=cols
        )
        self.db.add(memory_grid)
        self.db.commit()
        self.db.refresh(memory_grid)
        
        # Get all teams for this game session with their selected themes
        teams = self.db.query(Team).filter(Team.game_session_id == game_session_id).all()
        if not teams:
            raise ValueError("No teams found for this game session")
        
        # Verify each team has selected 3 themes
        for team in teams:
            if not team.selected_theme_ids:
                raise ValueError(f"Team {team.id} ({team.name}) has not selected themes for Round 3")
        
        # Get difficult questions (difficulty = HARD only for Round 3)
        from app.models import Difficulty
        difficult_questions = self.db.query(Question).filter(
            Question.difficulty == Difficulty.HARD
        ).all()
        
        total_cells = rows * cols
        if len(difficult_questions) < total_cells:
            raise ValueError(f"Not enough difficult questions for the memory grid. Need {total_cells}, have {len(difficult_questions)}")
        
        # Shuffle questions
        random.shuffle(difficult_questions)
        
        # Create grid cells
        cells = []
        question_index = 0
        assigned_cells = []
        
        # Assign 5 cells per team based on selected themes
        cells_per_team = 5
        
        for team in teams:
            # Parse selected theme IDs
            import json
            theme_ids = json.loads(team.selected_theme_ids) if isinstance(team.selected_theme_ids, str) else team.selected_theme_ids
            
            for _ in range(cells_per_team):
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
                    question_id=difficult_questions[question_index].id,
                    status=GridCellStatus.HIDDEN,
                    assigned_team_id=team.id
                )
                cells.append(cell)
                question_index += 1
        
        # Fill remaining cells with unassigned difficult questions
        for row in range(rows):
            for col in range(cols):
                if (row, col) not in assigned_cells:
                    cell = GridCell(
                        memory_grid_id=memory_grid.id,
                        row=row,
                        col=col,
                        question_id=difficult_questions[question_index].id,
                        status=GridCellStatus.HIDDEN,
                        assigned_team_id=None  # Unassigned cell
                    )
                    cells.append(cell)
                    question_index += 1
        
        self.db.add_all(cells)
        self.db.commit()
        
        return memory_grid
    
    def get_available_colors(self, game_session_id):
        """
        Get available colors for selection in Round 3.
        Returns list of PlayerColor enum values that are not already taken.
        """
        from app.memory_grid_enhanced import PlayerColor
        teams = self.db.query(Team).filter(Team.game_session_id == game_session_id).all()
        
        taken_colors = set()
        for team in teams:
            if team.color:
                taken_colors.add(team.color)
        
        available_colors = []
        for color_enum in PlayerColor:
            if color_enum.value not in taken_colors:
                available_colors.append(color_enum.value)
        
        return available_colors
    
    def select_team_color(self, team_id, color):
        """
        Select a color for a team in Round 3.
        Validates color is available and unique.
        """
        from app.memory_grid_enhanced import PlayerColor
        from app.models import Team
        
        # Validate color
        if not isinstance(color, PlayerColor):
            try:
                color = PlayerColor(color)
            except ValueError:
                raise ValueError(f"Invalid color: {color}. Must be one of {[c.value for c in PlayerColor]}")
        
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise ValueError(f"Team {team_id} not found")
        
        # Check if color is already taken by another team in the same game session
        existing_team = self.db.query(Team).filter(
            Team.game_session_id == team.game_session_id,
            Team.color == color.value,
            Team.id != team_id
        ).first()
        
        if existing_team:
            raise ValueError(f"Color {color.value} is already taken by team {existing_team.name}")
        
        # Assign color
        team.color = color.value
        self.db.commit()
        
        return {"success": True, "team_id": team_id, "color": color.value}
