"""
Extensions de schémas Pydantic pour Memory Grid - Round 3
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class PlayerColorEnum(str, Enum):
    """Couleurs disponibles pour les joueurs."""
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

class MemoryGridCellStatusEnum(str, Enum):
    """Statut des cellules de la grille mémoire."""
    HIDDEN = "hidden"
    REVEALED = "revealed"
    ANSWERED = "answered"

class RoundStatusEnum(str, Enum):
    """Statut des rounds."""
    ROUND_1 = "round_1"
    ROUND_2 = "round_2"
    ROUND_3 = "round_3"
    ROUND_4 = "round_4"
    ROUND_5 = "round_5"
    SUDDEN_DEATH = "sudden_death"
    COMPLETED = "completed"

class ColorSelectionRequest(BaseModel):
    """Requête pour sélectionner une couleur."""
    player_id: int
    game_session_id: int
    color: PlayerColorEnum

class ColorSelectionResponse(BaseModel):
    """Réponse de sélection de couleur."""
    success: bool
    player_id: int
    color: PlayerColorEnum
    message: str

class ThemeSelectionRequest(BaseModel):
    """Requête pour sélectionner 3 thèmes."""
    player_id: int
    game_session_id: int
    theme_ids: List[int] = Field(..., min_items=3, max_items=3)

class ThemeSelectionResponse(BaseModel):
    """Réponse de sélection de thème."""
    success: bool
    player_id: int
    theme_ids: List[int]
    theme_names: List[str]
    message: str

class ColorPaletteResponse(BaseModel):
    """Réponse avec la palette de couleurs disponibles."""
    available_colors: List[PlayerColorEnum]
    taken_colors: Dict[int, PlayerColorEnum]  # team_id -> color

class ThemePaletteResponse(BaseModel):
    """Réponse avec les thèmes disponibles pour sélection."""
    available_themes: List[dict]  # Liste des thèmes avec id, name, category
    count: int
    message: str

class MemoryGridCellInfo(BaseModel):
    """Information détaillée d'une cellule mémoire."""
    id: int
    row: int
    col: int
    status: MemoryGridCellStatusEnum
    assigned_team_id: Optional[int] = None
    answered_by_team_id: Optional[int] = None
    question: Optional[dict] = None  # Détails de la question si révélée/répondue

class MemoryGridDetailedStateResponse(BaseModel):
    """État détaillé de la grille mémoire."""
    memory_grid_id: int
    rows: int
    cols: int
    current_turn: int
    is_completed: bool
    cells: List[MemoryGridCellInfo]
    current_team_id: Optional[int] = None
    current_round: RoundStatusEnum

class GameResultResponse(BaseModel):
    """Résultat du jeu Memory Grid."""
    is_completed: bool
    team_scores: List[dict]
    winner: Optional[dict] = None
    is_tie: bool = False
    message: str

class RoundInfoResponse(BaseModel):
    """Information sur le round actuel."""
    current_round: str
    max_rounds: int
    current_turn: int
    is_sudden_death: bool = False
    sudden_death_round: int = 0
    teams_in_sudden_death: List[int] = []

class TurnAdvanceResponse(BaseModel):
    """Réponse d'avancement de tour."""
    turn_number: int
    current_team_id: Optional[int] = None
    next_team_id: Optional[int] = None
    message: str

class MemoryGridCreateRequest(BaseModel):
    """Requête pour créer une grille mémoire."""
    game_session_id: int
    rows: int = Field(default=7, ge=5, le=10)
    cols: int = Field(default=5, ge=5, le=10)

class MemoryGridRevealRequest(BaseModel):
    """Requête pour révéler une cellule."""
    memory_grid_id: int
    round_id: int
    team_id: int
    cell_id: int

class MemoryGridAnswerRequest(BaseModel):
    """Requête pour répondre à une cellule."""
    memory_grid_id: int
    round_id: int
    team_id: int
    cell_id: int
    answer: str
    is_correct: Optional[bool] = None  # Peut être déterminé côté serveur

class MemoryGridAnswerResponse(BaseModel):
    """Réponse après réponse à une cellule."""
    status: str
    is_correct: bool
    points_awarded: int
    team_score: int
    cell_type: str  # "own_theme", "stolen", "unassigned"
    next_team_id: Optional[int] = None
    game_completed: bool = False

class PlayerSetupStatusResponse(BaseModel):
    """Statut de setup du joueur (couleur + thèmes)."""
    player_id: int
    color_selected: bool
    themes_selected: bool
    selected_color: Optional[PlayerColorEnum] = None
    selected_themes: Optional[List[int]] = None
    setup_complete: bool