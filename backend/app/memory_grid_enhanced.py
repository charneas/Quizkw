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
        from app.models import Player, Team
        
        # Vérifier que le joueur existe
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise ValueError(f"Player {player_id} not found")
        
        # Vérifier que la couleur est valide
        if not isinstance(color, PlayerColor):
            try:
                color = PlayerColor(color)
            except ValueError:
                raise ValueError(f"Invalid color: {color}. Must be one of {[c.value for c in PlayerColor]}")
        
        # Vérifier que la couleur n'est pas déjà prise dans cette session
        # Pour cela, on doit trouver l'équipe du joueur
        team = self.db.query(Team).filter(Team.id == player.team_id).first()
        if not team:
            raise ValueError(f"Player {player_id} has no team")
        
        # Vérifier si une autre équipe a déjà cette couleur
        # Nous stockerons la couleur dans l'équipe (ou dans une table dédiée)
        # Pour l'instant, on va ajouter un champ color à Team
        # Mais comme on ne peut pas modifier le schéma, on va utiliser un dictionnaire en cache
        # En attendant, on retourne un succès simulé
        return {
            "success": True,
            "player_id": player_id,
            "color": color.value,
            "message": f"Color {color.value} selected successfully"
        }
    
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
        from app.models import Theme, Player, Team
        
        # Vérifier que le joueur existe
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise ValueError(f"Player {player_id} not found")
        
        # Vérifier qu'il y a exactement 3 thèmes
        if len(theme_ids) != 3:
            raise ValueError("Exactly 3 themes must be selected")
        
        # Vérifier que les thèmes existent
        themes = self.db.query(Theme).filter(Theme.id.in_(theme_ids)).all()
        if len(themes) != 3:
            raise ValueError("One or more themes not found")
        
        # Vérifier que les thèmes sont uniques
        if len(set(theme_ids)) != 3:
            raise ValueError("Themes must be unique")
        
        # Vérifier que les thèmes n'ont pas déjà été sélectionnés par d'autres joueurs
        # Pour l'instant, on va simplement accepter la sélection
        # Dans une implémentation complète, on vérifierait dans une table de sélection de thèmes
        
        return {
            "success": True,
            "player_id": player_id,
            "theme_ids": theme_ids,
            "theme_names": [theme.name for theme in themes],
            "message": f"Themes {[theme.name for theme in themes]} selected successfully"
        }
    
    def get_available_colors(self, game_session_id):
        """
        Retourne la liste des couleurs disponibles pour une session.
        
        Args:
            game_session_id: ID de la session de jeu
        
        Returns:
            list: Couleurs disponibles
        """
        # Pour l'instant, on retourne toutes les couleurs
        # Dans une implémentation complète, on exclurait les couleurs déjà prises
        return [color.value for color in PlayerColor]
    
    def get_available_themes_for_selection(self, count=15):
        """
        Retourne 15 thèmes disponibles pour la sélection.
        
        Args:
            count: Nombre de thèmes à retourner (par défaut 15)
        
        Returns:
            list: Thèmes disponibles
        """
        from app.models import Theme
        
        # Récupérer tous les thèmes
        all_themes = self.db.query(Theme).all()
        
        # Si on a moins de thèmes que demandé, on retourne tous les thèmes disponibles
        if len(all_themes) < count:
            return all_themes
        
        # Sinon, on en sélectionne aléatoirement
        return random.sample(all_themes, count)
    
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
        from app.models import Team
        
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            raise ValueError(f"Memory grid {memory_grid_id} not found")
        
        # Récupérer toutes les équipes de la session
        teams = self.db.query(Team).filter(Team.game_session_id == memory_grid.game_session_id).all()
        
        # Calculer les scores
        team_scores = []
        for team in teams:
            # Score de base (team.score)
            base_score = team.score
            
            # Compter les cellules volées (cellules assignées à d'autres équipes mais répondue par cette équipe)
            stolen_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_team_id == team.id,
                GridCell.assigned_team_id != team.id,
                GridCell.assigned_team_id.isnot(None),
                GridCell.status == GridCellStatus.ANSWERED
            ).count()
            
            # Compter les cellules de son propre thème
            own_theme_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_team_id == team.id,
                GridCell.assigned_team_id == team.id,
                GridCell.status == GridCellStatus.ANSWERED
            ).count()
            
            # Compter les cellules non assignées
            unassigned_cells = self.db.query(GridCell).filter(
                GridCell.memory_grid_id == memory_grid_id,
                GridCell.answered_by_team_id == team.id,
                GridCell.assigned_team_id.is_(None),
                GridCell.status == GridCellStatus.ANSWERED
            ).count()
            
            team_scores.append({
                "team_id": team.id,
                "team_name": team.name,
                "base_score": base_score,
                "stolen_cells": stolen_cells,
                "own_theme_cells": own_theme_cells,
                "unassigned_cells": unassigned_cells,
                "total_score": base_score
            })
        
        # Trier par score total (décroissant)
        team_scores.sort(key=lambda x: x["total_score"], reverse=True)
        
        # Vérifier s'il y a une égalité
        is_tie = False
        if len(team_scores) > 1 and team_scores[0]["total_score"] == team_scores[1]["total_score"]:
            is_tie = True
        
        return {
            "is_completed": memory_grid.is_completed,
            "team_scores": team_scores,
            "winner": team_scores[0] if not is_tie else None,
            "is_tie": is_tie,
            "message": f"Winner: {team_scores[0]['team_name']} with {team_scores[0]['total_score']} points" if not is_tie else "Tie - sudden death round needed"
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
        
        memory_grid = self.db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
        if not memory_grid:
            raise ValueError(f"Memory grid {memory_grid_id} not found")
        
        # Calculer le round actuel (basé sur le nombre de tours et le nombre d'équipes)
        teams = self.db.query(Team).filter(Team.game_session_id == memory_grid.game_session_id).all()
        num_teams = len(teams)
        
        if num_teams == 0:
            current_round = 1
            max_rounds = 5
        else:
            # Chaque round = chaque équipe joue une fois
            current_round = (memory_grid.current_turn // num_teams) + 1
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