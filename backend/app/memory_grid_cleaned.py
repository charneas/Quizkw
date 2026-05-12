def create_memory_grid(self, game_session_id: int, rows: int = 7, cols: int = 5) -> MemoryGrid:
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