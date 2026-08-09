from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLAlchemyEnum, JSON, func
from sqlalchemy.orm import relationship
from app.models import Base, Question
import enum
import random
import json
import time

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
    # AD-0 : la Manche 3 est individuelle — les cellules appartiennent à des
    # JOUEURS, pas à des équipes.
    assigned_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Finaliste propriétaire initial
    answered_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Finaliste qui a répondu
    # AD-15 : sentinelle d'idempotence. L'attribution est un update gardé sur
    # cette colonne encore à 0 ; le statut de cellule est de l'état de jeu et
    # ne sert jamais de garde.
    points_awarded = Column(Integer, default=0, nullable=False)

    memory_grid = relationship("MemoryGrid", back_populates="cells")
    question = relationship("Question")
    assigned_player = relationship("Player", foreign_keys=[assigned_player_id])
    answered_by_player = relationship("Player", foreign_keys=[answered_by_player_id])

class SuddenDeathRound(Base):
    """Manche de départage jouée quand la Manche 3 se termine sur une égalité.

    AD-1 : départage uniquement, n'écrit jamais dans PlayerRound3Stats.score.
    tied_player_ids / eliminated_player_ids sont des listes JSON d'IDs joueurs.
    """
    __tablename__ = "sudden_death_rounds"

    id = Column(Integer, primary_key=True, index=True)
    memory_grid_id = Column(Integer, ForeignKey("memory_grids.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    tied_player_ids = Column(JSON, nullable=False)
    eliminated_player_ids = Column(JSON, default=list, nullable=False)
    winner_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    is_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memory_grid = relationship("MemoryGrid")
    question = relationship("Question")
    winner_player = relationship("Player", foreign_keys=[winner_player_id])

class MemoryGridRound(Base):
    __tablename__ = "memory_grid_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    memory_grid_id = Column(Integer, ForeignKey("memory_grids.id"))
    # AD-0 : la Manche 3 est individuelle — c'est le tour d'un JOUEUR.
    current_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    game_session = relationship("GameSession")
    memory_grid = relationship("MemoryGrid")
    current_player = relationship("Player")

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
        
        # AD-0 : la Manche 3 oppose 4 FINALISTES individuels, pas des équipes.
        finalists = self.get_finalists_from_round2(game_session_id)
        if not finalists:
            raise ValueError("Aucun finaliste : la Manche 2 n'a pas désigné de qualifiés")

        # Chaque finaliste démarre à 0 (AD-1) : on matérialise sa ligne tout de
        # suite pour que le classement soit lisible dès le premier écran.
        for player_id in finalists:
            self._get_or_create_round3_stats(game_session_id, player_id)

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

        # 5 cellules par finaliste (sa couleur)
        cells_per_player = 5
        assigned_cells = []

        for player_id in finalists:
            for _ in range(cells_per_player):
                # Note: The check "if question_index >= len(questions): break" was removed
                # because line 80 ensures len(questions) >= total_cells (35)
                # and we only assign 20 cells to finalists (4 players * 5 = 20)
                
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
                    assigned_player_id=player_id
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
                        assigned_player_id=None  # Cellule neutre
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
    
    def reveal_cell(self, round_id, player_id, cell_id):
        """Révéler une cellule. AD-6 : on lève, on ne retourne pas None.
        AD-5 : pas de commit ici, l'endpoint possède la transaction."""
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        if not round_obj:
            raise LookupError(f"Manche de grille {round_id} introuvable")

        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        if not cell:
            raise LookupError(f"Cellule {cell_id} introuvable")

        if cell.status == GridCellStatus.ANSWERED:
            raise ValueError("Cette cellule a déjà reçu une réponse")

        round_obj.current_player_id = player_id
        cell.status = GridCellStatus.REVEALED
        self.db.flush()

        return {"status": "cell_revealed", "cell_id": cell.id}
    
    def answer_cell(self, round_id, player_id, cell_id, player_answer):
        """Répondre à une cellule révélée.

        AD-3 : le SERVEUR juge la correction. `player_answer` est le texte
        soumis ; le client ne transmet plus de booléen de correction.
        AD-15 : `cell.points_awarded` est la sentinelle d'idempotence — un
        rejeu n'attribue pas deux fois.
        AD-1 : le score s'écrit dans PlayerRound3Stats, jamais dans Team.score.
        AD-5 : on ne commit pas ici ; l'endpoint possède la transaction.
        """
        round_obj = self.db.query(MemoryGridRound).filter(MemoryGridRound.id == round_id).first()
        if not round_obj:
            raise LookupError(f"Manche de grille {round_id} introuvable")

        cell = self.db.query(GridCell).filter(GridCell.id == cell_id).first()
        if not cell:
            raise LookupError(f"Cellule {cell_id} introuvable")

        if cell.status != GridCellStatus.REVEALED:
            raise ValueError("La cellule doit être révélée avant d'y répondre")

        # AD-15 : sentinelle. Le statut est de l'état de jeu, pas une garde.
        if cell.points_awarded != 0:
            raise ValueError("Cette cellule a déjà été attribuée")

        # AD-3 : correction calculée côté serveur, même normalisation que les
        # manches 1 et 2 — strip + lower, rien d'autre.
        question = self.db.query(Question).filter(Question.id == cell.question_id).first()
        if not question:
            raise LookupError(f"Question {cell.question_id} introuvable pour la cellule {cell_id}")

        submitted = (player_answer or "").strip().lower()
        is_correct = submitted == question.correct_answer.strip().lower()

        cell.status = GridCellStatus.ANSWERED
        cell.answered_by_player_id = player_id

        # Barème : 2 de base, +1 si c'est sa propre cellule, +1 si elle est volée
        points = 0
        if is_correct:
            points = 2
            if cell.assigned_player_id == player_id:
                points += 1
            elif cell.assigned_player_id:
                points += 1

        cell_type = "unassigned"
        if cell.assigned_player_id:
            cell_type = "own" if cell.assigned_player_id == player_id else "stolen"

        if points > 0:
            cell.points_awarded = points  # arme la sentinelle
            stats = self._get_or_create_round3_stats(round_obj.game_session_id, player_id)
            stats.score += points
            stats.cells_claimed += 1

        self.db.flush()

        return {
            "status": "answered",
            "is_correct": is_correct,
            "correct_answer": question.correct_answer,
            "points_awarded": points,
            "cell_type": cell_type,
            "memory_grid_id": round_obj.memory_grid_id,
        }

    def _get_or_create_round3_stats(self, game_session_id, player_id):
        """Ligne de score Manche 3 du joueur, créée à la volée si absente."""
        from app.models import PlayerRound3Stats

        stats = self.db.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.game_session_id == game_session_id,
            PlayerRound3Stats.player_id == player_id,
        ).first()

        if not stats:
            stats = PlayerRound3Stats(
                game_session_id=game_session_id,
                player_id=player_id,
                score=0,
                cells_claimed=0,
            )
            self.db.add(stats)
            self.db.flush()

        return stats
    
    def get_grid_state(self, memory_grid_id):
        """Get the current state of the memory grid"""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None
        
        cells = self.db.query(GridCell).filter(
            GridCell.memory_grid_id == memory_grid_id
        ).order_by(GridCell.row, GridCell.col).all()
        
        # Map status: backend 'answered' → frontend 'matched'
        def map_status(status):
            if status == GridCellStatus.ANSWERED:
                return 'matched'
            return status.value
        
        # Convert to dict format matching frontend MemoryGridState type
        cells_data = []
        for cell in cells:
            # Load question text if cell is revealed/answered
            question_data = None
            if cell.status != GridCellStatus.HIDDEN and cell.question_id:
                q = self.db.query(Question).filter(Question.id == cell.question_id).first()
                if q:
                    question_data = {
                        'id': q.id,
                        'text': q.text,
                        'category': q.category,
                        'difficulty': q.difficulty.value,
                        'points': q.points,
                        'correct_answer': q.correct_answer,
                    }
            
            cells_data.append({
                'id': cell.id,
                'memory_grid_id': memory_grid_id,
                'row': cell.row,
                'col': cell.col,
                'status': map_status(cell.status),
                'assigned_player_id': cell.assigned_player_id,
                'matched_by_player_id': cell.answered_by_player_id,
                'points_awarded': cell.points_awarded,
                'question': question_data,
            })
        
        return {
            'memory_grid': {
                'id': memory_grid_id,
                'game_session_id': memory_grid.game_session_id,
                'rows': memory_grid.rows,
                'cols': memory_grid.cols,
                'grid_size': memory_grid.cols,  # alias for frontend
                'current_turn': memory_grid.current_turn,
                'is_completed': memory_grid.is_completed,
            },
            'cells': cells_data,
        }
    
    def advance_turn(self, memory_grid_id):
        """Advance to the next turn in the memory grid.
        AD-5 : pas de commit ici, l'endpoint possède la transaction."""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None

        memory_grid.current_turn += 1
        self.db.flush()

        return memory_grid.current_turn

    def check_completion(self, memory_grid_id):
        """Check if the memory grid is completed (all cells answered).
        AD-5 : pas de commit ici, l'endpoint possède la transaction."""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            return None

        cells = self.db.query(GridCell).filter(GridCell.memory_grid_id == memory_grid_id).all()

        # Check if all cells are answered
        all_answered = all(cell.status == GridCellStatus.ANSWERED for cell in cells)

        if all_answered:
            memory_grid.is_completed = True
            self.db.flush()

        return all_answered
    
    # Round 3 Enhanced Methods
    FINALIST_COUNT = 4

    def get_finalists_from_round2(self, game_session_id):
        """Les 4 finalistes de la Manche 3, classés par score de Manche 2.

        AD-0 : la Manche 3 est INDIVIDUELLE avec exactement 4 finalistes.
        AD-1 : la Manche 2 ne sert qu'à qualifier — son score ne suit pas le
        joueur en Manche 3, il ne sert qu'à ce classement.

        Retourne une liste d'identifiants de JOUEURS, du meilleur au moins bon.
        """
        from app.models import PlayerRound2Stats

        stats = self.db.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.game_session_id == game_session_id
        ).order_by(PlayerRound2Stats.score.desc()).all()

        if not stats:
            raise LookupError(
                f"Aucun résultat de Manche 2 pour la partie {game_session_id} : "
                "impossible de désigner les finalistes"
            )

        return [s.player_id for s in stats[:self.FINALIST_COUNT]]

    def get_current_player_turn(self, memory_grid_id, finalist_ranking):
        """Le finaliste dont c'est le tour, en tourniquet sur le classement."""
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid or not finalist_ranking:
            return None

        turn_index = memory_grid.current_turn % len(finalist_ranking)
        return finalist_ranking[turn_index]
    
    def create_memory_grid_with_themes(self, game_session_id, rows=7, cols=5):
        """
        Create memory grid for Round 3 with theme-based cell assignment.
        AD-0 : 5 cellules par FINALISTE, d'après les thèmes qu'il a choisis.
        """
        from app.models import GameSession, Difficulty, Player, PlayerRound3Stats

        # Get game session to verify player count
        game = self.db.query(GameSession).filter(GameSession.id == game_session_id).first()
        if not game:
            raise ValueError("Game session not found")

        # AD-0 : la Manche 3 se joue à exactement 4 finalistes
        finalists = self.get_finalists_from_round2(game_session_id)
        if len(finalists) != self.FINALIST_COUNT:
            raise ValueError(
                f"La Manche 3 exige exactement {self.FINALIST_COUNT} finalistes, "
                f"{len(finalists)} qualifiés trouvés"
            )

        memory_grid = MemoryGrid(
            game_session_id=game_session_id,
            rows=rows,
            cols=cols
        )
        self.db.add(memory_grid)
        self.db.flush()

        # Chaque finaliste doit avoir choisi exactement 3 thèmes
        import json
        finalist_themes = {}
        for player_id in finalists:
            stats = self.db.query(PlayerRound3Stats).filter(
                PlayerRound3Stats.game_session_id == game_session_id,
                PlayerRound3Stats.player_id == player_id,
            ).first()

            raw = stats.selected_theme_ids if stats else None
            if not raw:
                raise ValueError(f"Le finaliste {player_id} n'a pas choisi ses thèmes de Manche 3")

            theme_ids = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(theme_ids, list) or len(theme_ids) != 3:
                raise ValueError(
                    f"Le finaliste {player_id} doit choisir exactement 3 thèmes, "
                    f"{len(theme_ids) if isinstance(theme_ids, list) else 'format invalide'} trouvé(s)"
                )
            finalist_themes[player_id] = theme_ids

        # Get difficult questions (difficulty = HARD only for Round 3)
        difficult_questions = self.db.query(Question).filter(
            Question.difficulty == Difficulty.HARD
        ).all()

        total_cells = rows * cols
        if len(difficult_questions) < total_cells:
            raise ValueError(f"Not enough difficult questions for the memory grid. Need {total_cells}, have {len(difficult_questions)}")

        # Shuffle once, puis on retire les questions au fur et à mesure
        # qu'elles sont assignées à une cellule (pas de doublon possible).
        random.shuffle(difficult_questions)
        remaining_questions = list(difficult_questions)

        def pick_question(theme_ids):
            """BUG-302 : privilégie une question dont le thème fait partie de
            ceux choisis par le finaliste ; si son pool thématique est épuisé
            (thèmes peu fournis en questions HARD), on retombe sur n'importe
            quelle question HARD restante plutôt que de faire échouer la
            création de la grille.
            """
            for i, q in enumerate(remaining_questions):
                if q.theme_id in theme_ids:
                    return remaining_questions.pop(i)
            return remaining_questions.pop(0)

        # Create grid cells
        cells = []
        assigned_cells = []

        # 5 cellules par finaliste, d'après ses thèmes
        cells_per_player = 5

        for player_id in finalists:
            theme_ids = set(finalist_themes[player_id])

            for _ in range(cells_per_player):
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
                    question_id=pick_question(theme_ids).id,
                    status=GridCellStatus.HIDDEN,
                    assigned_player_id=player_id
                )
                cells.append(cell)

        # Fill remaining cells with unassigned difficult questions
        for row in range(rows):
            for col in range(cols):
                if (row, col) not in assigned_cells:
                    cell = GridCell(
                        memory_grid_id=memory_grid.id,
                        row=row,
                        col=col,
                        question_id=remaining_questions.pop(0).id,
                        status=GridCellStatus.HIDDEN,
                        assigned_player_id=None  # Cellule neutre
                    )
                    cells.append(cell)

        self.db.add_all(cells)
        self.db.commit()

        return memory_grid
    
    def get_available_colors(self, game_session_id):
        """Couleurs encore libres pour les finalistes de la Manche 3 (AD-0)."""
        from app.schemas_extended import PlayerColorEnum
        from app.models import PlayerRound3Stats

        taken = {
            s.color for s in self.db.query(PlayerRound3Stats).filter(
                PlayerRound3Stats.game_session_id == game_session_id
            ).all() if s.color
        }

        # BUG-302 : seules les couleurs exposées par le schéma API
        # (PlayerColorEnum, 12 valeurs) sont sélectionnables via
        # ColorSelectionRequest — l'enum interne PlayerColor (memory_grid_enhanced,
        # 20 valeurs) en propose davantage, mais les renvoyer ici ferait échouer
        # la validation Pydantic de ColorPaletteResponse.available_colors.
        return [c.value for c in PlayerColorEnum if c.value not in taken]

    def select_player_color(self, game_session_id, player_id, color):
        """Attribuer une couleur à un finaliste. AD-0 : par joueur, pas par équipe.
        AD-5 : pas de commit ici. AD-6 : on lève."""
        from app.memory_grid_enhanced import PlayerColor
        from app.models import PlayerRound3Stats

        if not isinstance(color, PlayerColor):
            try:
                color = PlayerColor(color)
            except ValueError:
                raise ValueError(
                    f"Couleur invalide : {color}. Attendu l'une de {[c.value for c in PlayerColor]}"
                )

        taken_by = self.db.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.game_session_id == game_session_id,
            PlayerRound3Stats.color == color.value,
            PlayerRound3Stats.player_id != player_id,
        ).first()
        if taken_by:
            raise ValueError(
                f"La couleur {color.value} est déjà prise par le joueur {taken_by.player_id}"
            )

        stats = self._get_or_create_round3_stats(game_session_id, player_id)
        stats.color = color.value
        self.db.flush()

        return {"success": True, "player_id": player_id, "color": color.value}

    def select_player_themes(self, game_session_id, player_id, theme_ids):
        """Enregistrer les 3 thèmes d'un finaliste. AD-5 : pas de commit ici.

        BUG-302 : les thèmes doivent être exclusifs entre finalistes, comme
        la couleur (select_player_color ci-dessus) — sans quoi deux finalistes
        peuvent choisir les mêmes thèmes et create_memory_grid_with_themes
        n'a plus de base cohérente pour distinguer leurs cellules.
        """
        from app.models import PlayerRound3Stats

        if not isinstance(theme_ids, list) or len(theme_ids) != 3:
            raise ValueError("Un finaliste doit choisir exactement 3 thèmes")

        others = self.db.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.game_session_id == game_session_id,
            PlayerRound3Stats.player_id != player_id,
            PlayerRound3Stats.selected_theme_ids.isnot(None),
        ).all()
        taken_theme_ids = {tid for s in others for tid in (s.selected_theme_ids or [])}
        conflict = taken_theme_ids.intersection(theme_ids)
        if conflict:
            raise ValueError(f"Thème(s) déjà choisi(s) par un autre finaliste : {sorted(conflict)}")

        stats = self._get_or_create_round3_stats(game_session_id, player_id)
        stats.selected_theme_ids = theme_ids
        self.db.flush()

        return {"success": True, "player_id": player_id, "selected_theme_ids": theme_ids}
