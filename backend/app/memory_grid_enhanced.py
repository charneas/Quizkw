"""
Extensions pour MemoryGridManager - fonctionnalités manquantes selon la spécification BMad
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import random
import enum

class PlayerColor(enum.Enum):
    """Couleurs disponibles pour les joueurs dans la grille mémoire (20 couleurs distinctes)."""
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    PURPLE = "purple"
    ORANGE = "orange"
    PINK = "pink"
    CYAN = "cyan"
    TEAL = "teal"
    BROWN = "brown"
    GRAY = "gray"
    BLACK = "black"
    MAGENTA = "magenta"
    LIME = "lime"
    INDIGO = "indigo"
    NAVY = "navy"
    OLIVE = "olive"
    SILVER = "silver"
    GOLD = "gold"
    CORAL = "coral"

class ThemeSelectionStatus(enum.Enum):
    """Statut de sélection de thème."""
    PENDING = "pending"
    SELECTED = "selected"
    CONFIRMED = "confirmed"

class MemoryGridEnhancer:
    """Extensions pour MemoryGridManager avec fonctionnalités manquantes."""
    
    def __init__(self, db):
        self.db = db
    
    def select_player_color(self, player_id, game_session_id, color):
        """
        Permet à un joueur de sélectionner une couleur unique.
        
        Args:
            player_id: ID du joueur
            game_session_id: ID de la session de jeu
            color: Couleur choisie (enum PlayerColor)
        
        Returns:
            dict: Résultat de la sélection
        """
        from app.models import Player
        from app.memory_grid import MemoryGridManager

        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise LookupError(f"Player {player_id} not found")

        # La couleur est désormais RÉELLEMENT persistée, sur PlayerRound3Stats
        # (AD-0). Cette méthode retournait auparavant un succès simulé sans rien
        # écrire ; elle délègue maintenant à l'unique implémentation.
        result = MemoryGridManager(self.db).select_player_color(
            game_session_id, player_id, color
        )
        result["message"] = f"Couleur {result['color']} enregistrée"
        return result
    
    def select_themes_for_player(self, player_id, game_session_id, theme_ids):
        """
        Permet à un joueur de sélectionner 3 thèmes uniques.
        
        Args:
            player_id: ID du joueur
            game_session_id: ID de la session de jeu
            theme_ids: Liste de 3 IDs de thème
        
        Returns:
            dict: Résultat de la sélection
        """
        from app.models import Theme, Player
        from app.memory_grid import MemoryGridManager

        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise LookupError(f"Player {player_id} not found")

        if len(theme_ids) != 3:
            raise ValueError("Exactly 3 themes must be selected")

        if len(set(theme_ids)) != 3:
            raise ValueError("Themes must be unique")

        themes = self.db.query(Theme).filter(Theme.id.in_(theme_ids)).all()
        if len(themes) != 3:
            raise LookupError("One or more themes not found")

        # Persisté pour de bon sur PlayerRound3Stats (AD-0) au lieu du succès
        # simulé d'avant.
        MemoryGridManager(self.db).select_player_themes(
            game_session_id, player_id, theme_ids
        )

        return {
            "success": True,
            "player_id": player_id,
            "theme_ids": theme_ids,
            "theme_names": [theme.name for theme in themes],
            "message": f"Thèmes enregistrés : {[theme.name for theme in themes]}"
        }
    
    def get_available_colors(self, game_session_id):
        """
        Retourne la liste des couleurs disponibles pour une session.

        Args:
            game_session_id: ID de la session de jeu

        Returns:
            list: Couleurs disponibles (déjà prises exclues)
        """
        # BUG-302 : cette méthode retournait auparavant systématiquement les
        # 20 couleurs, sans jamais exclure celles déjà prises par un autre
        # finaliste — l'unique implémentation qui filtre réellement est
        # MemoryGridManager.get_available_colors (memory_grid.py), qui lit
        # PlayerRound3Stats. On délègue à celle-ci au lieu de dupliquer/diverger.
        from app.memory_grid import MemoryGridManager
        return MemoryGridManager(self.db).get_available_colors(game_session_id)
    
    def get_available_themes_for_selection(self, game_session_id, count=15):
        """
        Retourne jusqu'à `count` thèmes disponibles pour la sélection.

        Args:
            game_session_id: ID de la session de jeu — sert à exclure les
                thèmes déjà pris par un autre finaliste (BUG-302, cf.
                select_player_themes qui applique désormais la même exclusivité)
            count: Nombre de thèmes à retourner (par défaut 15)

        Returns:
            list: Thèmes disponibles
        """
        from app.models import Theme, PlayerRound3Stats

        taken_theme_ids = {
            tid
            for s in self.db.query(PlayerRound3Stats).filter(
                PlayerRound3Stats.game_session_id == game_session_id,
                PlayerRound3Stats.selected_theme_ids.isnot(None),
            ).all()
            for tid in (s.selected_theme_ids or [])
        }

        available_themes = (
            self.db.query(Theme).filter(~Theme.id.in_(taken_theme_ids)).all()
            if taken_theme_ids
            else self.db.query(Theme).all()
        )

        if len(available_themes) <= count:
            return available_themes

        return random.sample(available_themes, count)
    
    def advance_turn(self, memory_grid_id):
        """
        Passe au tour suivant dans la grille mémoire.
        
        Args:
            memory_grid_id: ID de la grille mémoire
        
        Returns:
            dict: État du tour
        """
        from app.memory_grid import MemoryGrid
        
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            raise ValueError(f"Memory grid {memory_grid_id} not found")
        
        # Incrémenter le tour
        memory_grid.current_turn += 1
        self.db.commit()
        
        # Déterminer quelle équipe doit jouer (round-robin)
        # Pour l'instant, on retourne simplement le numéro du tour
        return {
            "turn_number": memory_grid.current_turn,
            "message": f"Turn advanced to {memory_grid.current_turn}"
        }
    
    def calculate_winner(self, memory_grid_id):
        """
        Calcule le vainqueur de la grille mémoire.
        
        Args:
            memory_grid_id: ID de la grille mémoire
        
        Returns:
            dict: Résultats du jeu
        """
        from app.memory_grid import MemoryGrid, GridCell, GridCellStatus
        from app.models import Player, PlayerRound3Stats

        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            raise LookupError(f"Memory grid {memory_grid_id} not found")

        # AD-0 : la Manche 3 oppose des FINALISTES individuels.
        # AD-1 : le vainqueur sort du seul score de Manche 3 — aucun score des
        # manches 1 ou 2 n'entre dans ce calcul.
        stats_rows = self.db.query(PlayerRound3Stats).filter(
            PlayerRound3Stats.game_session_id == memory_grid.game_session_id
        ).all()

        player_scores = []
        for stats in stats_rows:
            player = self.db.query(Player).filter(Player.id == stats.player_id).first()

            stolen_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_player_id == stats.player_id,
                GridCell.assigned_player_id != stats.player_id,
                GridCell.assigned_player_id.isnot(None),
                GridCell.status == GridCellStatus.ANSWERED
            ).count()

            own_theme_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_player_id == stats.player_id,
                GridCell.assigned_player_id == stats.player_id,
                GridCell.status == GridCellStatus.ANSWERED
            ).count()

            unassigned_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_player_id == stats.player_id,
                GridCell.assigned_player_id.is_(None),
                GridCell.status == GridCellStatus.ANSWERED
            ).count()

            player_scores.append({
                "player_id": stats.player_id,
                "player_name": player.name if player else f"Joueur {stats.player_id}",
                "stolen_cells": stolen_cells,
                "own_theme_cells": own_theme_cells,
                "unassigned_cells": unassigned_cells,
                "total_score": stats.score,
            })

        player_scores.sort(key=lambda x: x["total_score"], reverse=True)

        is_tie = (
            len(player_scores) > 1
            and player_scores[0]["total_score"] == player_scores[1]["total_score"]
        )

        if not player_scores:
            return {
                "is_completed": memory_grid.is_completed,
                "player_scores": [],
                "winner": None,
                "is_tie": False,
                "message": "Aucun finaliste n'a encore marqué",
            }

        return {
            "is_completed": memory_grid.is_completed,
            "player_scores": player_scores,
            "winner": player_scores[0] if not is_tie else None,
            "is_tie": is_tie,
            "message": (
                f"Vainqueur : {player_scores[0]['player_name']} "
                f"avec {player_scores[0]['total_score']} points"
                if not is_tie else "Égalité — mort subite nécessaire"
            )
        }
    
    def get_current_round_info(self, memory_grid_id):
        """
        Retourne les informations sur le round actuel (1-5).
        
        Args:
            memory_grid_id: ID de la grille mémoire
        
        Returns:
            dict: Informations du round
        """
        from app.memory_grid import MemoryGrid
        
        from app.memory_grid import MemoryGridManager

        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            raise LookupError(f"Memory grid {memory_grid_id} not found")

        # AD-0 : un round = chaque FINALISTE joue une fois. Ils sont toujours 4.
        num_finalists = MemoryGridManager.FINALIST_COUNT
        current_round = (memory_grid.current_turn // num_finalists) + 1
        max_rounds = 5
        
        # Vérifier si on est en sudden death (tie breaker)
        is_sudden_death = current_round > max_rounds
        
        return {
            "current_round": current_round if not is_sudden_death else "sudden_death",
            "max_rounds": max_rounds,
            "current_turn": memory_grid.current_turn,
            "is_sudden_death": is_sudden_death,
            "sudden_death_round": current_round - max_rounds if is_sudden_death else 0
        }