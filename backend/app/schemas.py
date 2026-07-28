from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional
from datetime import datetime
from enum import Enum
import json

# Enums pour la validation des données
class DifficultyEnum(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

class TokenTypeEnum(str, Enum):
    swap = "swap"
    penalty = "penalty"
    bonus = "bonus"

class RoundTypeEnum(str, Enum):
    manche_1 = "manche_1"
    manche_2 = "manche_2"
    manche_3 = "manche_3"

class PropositionStatusEnum(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

# Schémas de base
class QuestionBase(BaseModel):
    text: str
    category: str
    difficulty: DifficultyEnum
    points: int = Field(..., ge=2, le=6)  # 2, 4, ou 6 points
    correct_answer: str
    wrong_answers: List[str]
    theme_id: Optional[int] = None
    question_number: Optional[int] = None

class QuestionCreate(QuestionBase):
    pass

class Question(QuestionBase):
    id: int
    created_at: datetime
    
    @field_validator('wrong_answers', mode='before')
    @classmethod
    def parse_wrong_answers(cls, v):
        """Parse wrong_answers from JSON string if needed"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If it's not valid JSON, try to handle it as a string representation
                if v.startswith('[') and v.endswith(']'):
                    # Try to fix common issues
                    v = v.replace("'", '"')
                    try:
                        return json.loads(v)
                    except json.JSONDecodeError:
                        pass
                # Return as single item list if parsing fails
                return [v]
        return v
    
    class Config:
        from_attributes = True

class PlayerBase(BaseModel):
    name: str

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Le pseudo ne peut pas être vide")
        return stripped

class PlayerCreate(PlayerBase):
    pass

class Player(PlayerBase):
    id: int
    team_id: Optional[int] = None
    
    class Config:
        from_attributes = True

class TeamBase(BaseModel):
    name: str

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Le nom d'équipe ne peut pas être vide")
        return stripped

class TeamCreate(TeamBase):
    pass

class Team(TeamBase):
    id: int
    game_session_id: int
    score: int
    players: List[Player] = []
    
    class Config:
        from_attributes = True

class TokenBase(BaseModel):
    token_type: TokenTypeEnum

class TokenCreate(TokenBase):
    pass

class Token(TokenBase):
    id: int
    team_id: int
    is_used: bool
    
    class Config:
        from_attributes = True

class GameSessionBase(BaseModel):
    total_players: int = Field(..., ge=1, le=16)
    players_per_team: int = Field(..., ge=1, le=3)

class GameSessionCreate(GameSessionBase):
    pass

class GameSession(GameSessionBase):
    id: int
    code: str
    current_round: RoundTypeEnum
    current_question_id: Optional[int] = None
    is_active: bool
    started: bool
    created_at: datetime
    teams: List[Team] = []
    
    class Config:
        from_attributes = True

class AnswerBase(BaseModel):
    question_id: int
    team_id: int
    player_answer: str

class AnswerCreate(AnswerBase):
    pass

class Answer(AnswerBase):
    id: int
    is_correct: bool
    points_earned: int
    answered_at: datetime
    
    class Config:
        from_attributes = True

# Schémas pour les réponses API
class GameSessionResponse(BaseModel):
    game: GameSession
    message: str

class QuestionResponse(BaseModel):
    question: Question
    options: List[str]  # Mélange des bonnes et mauvaises réponses

class AnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    points_earned: int
    team_score: int
    pending_validation: bool = True

class TokenUseRequest(BaseModel):
    token_type: TokenTypeEnum
    team_id: int
    target_team_id: Optional[int] = None

class SetCurrentQuestionRequest(BaseModel):
    question_id: int

class WheelSpinRequest(BaseModel):
    team_id: int

class WheelSpinResponse(BaseModel):
    effect_type: str
    value: Optional[int] = None
    message: str

# Memory Grid Schemas
class GridCellStatusEnum(str, Enum):
    hidden = "hidden"
    revealed = "revealed"
    matched = "matched"
    answered = "answered"

class MemoryGridBase(BaseModel):
    grid_size: int = Field(default=5, ge=2, le=8)

class MemoryGridCreate(MemoryGridBase):
    pass

class MemoryGrid(MemoryGridBase):
    id: int
    game_session_id: int
    current_turn: int
    is_completed: bool
    
    class Config:
        from_attributes = True

class GridCellBase(BaseModel):
    row: int
    col: int

class GridCell(GridCellBase):
    id: int
    memory_grid_id: int
    status: GridCellStatusEnum
    matched_by_team_id: Optional[int] = None
    question: Optional[Question] = None
    
    class Config:
        from_attributes = True

class MemoryGridRoundBase(BaseModel):
    memory_grid_id: int

class MemoryGridRoundCreate(MemoryGridRoundBase):
    pass

class MemoryGridRound(MemoryGridRoundBase):
    id: int
    game_session_id: int
    current_team_id: Optional[int] = None
    selected_cells: List[dict] = []
    is_active: bool
    
    class Config:
        from_attributes = True

class MemoryGridStateResponse(BaseModel):
    memory_grid: MemoryGrid
    cells: List[GridCell]

class SelectCellRequest(BaseModel):
    round_id: int
    player_id: int  # AD-0 : la Manche 3 est individuelle
    cell_id: int

class SelectCellResponse(BaseModel):
    status: str
    cell: Optional[GridCell] = None
    remaining_selections: Optional[int] = None
    points_awarded: Optional[int] = None
    team_score: Optional[int] = None
    matched_cells: Optional[List[int]] = None
    message: Optional[str] = None

class StartMemoryGridRoundResponse(BaseModel):
    round_id: int
    message: str

class AnswerCellRequest(BaseModel):
    round_id: int
    player_id: int  # AD-0 : la Manche 3 est individuelle
    cell_id: int
    # AD-3 : le client soumet SA RÉPONSE, jamais un verdict de correction.
    # Le serveur seul décide si elle est juste.
    player_answer: str

class AnswerCellResponse(BaseModel):
    status: str
    is_correct: bool
    points_awarded: int
    team_score: int
    cell_type: str

# Round 2 Enums
class ThemeCategoryEnum(str, Enum):
    serious = "serious"
    pop_culture = "pop_culture"
    whimsical = "whimsical"

class QualificationStatusEnum(str, Enum):
    playing = "playing"
    qualified = "qualified"
    eliminated = "eliminated"
    finalist = "finalist"

# Round 2 Schemas
class ThemeBase(BaseModel):
    name: str
    category: ThemeCategoryEnum
    difficulty_level: int = Field(..., ge=1, le=10)
    description: Optional[str] = None

class ThemeCreate(ThemeBase):
    pass

class Theme(ThemeBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Propositions (Epic F-ext, AD-18 : entité distincte de Question)
class PropositionBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    correct_answer: str = Field(..., min_length=1, max_length=200)
    wrong_answers: List[str] = Field(default_factory=list, max_length=3)
    theme_id: Optional[int] = None
    difficulty: DifficultyEnum

    @field_validator('text', 'correct_answer')
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Ce champ ne peut pas être vide ou composé uniquement d'espaces")
        return v

    @field_validator('wrong_answers')
    @classmethod
    def wrong_answers_max_length(cls, v: List[str]) -> List[str]:
        for item in v:
            if len(item) > 200:
                raise ValueError("Une mauvaise réponse ne peut pas dépasser 200 caractères")
        return v

class PropositionCreate(PropositionBase):
    pass

class Proposition(PropositionBase):
    id: int
    status: PropositionStatusEnum
    rejection_reason: Optional[str] = None
    created_at: datetime

    @field_validator('wrong_answers', mode='before')
    @classmethod
    def parse_wrong_answers(cls, v):
        """Parse wrong_answers from JSON string if needed (même pattern que Question)."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v

    class Config:
        from_attributes = True

class PlayerRound2StatsBase(BaseModel):
    player_id: int
    game_session_id: int
    theme_id: Optional[int] = None
    score: int = 0
    questions_answered: int = 0
    correct_answers: int = 0
    current_question_index: int = 0
    qualification_status: QualificationStatusEnum = QualificationStatusEnum.playing

class PlayerRound2StatsCreate(PlayerRound2StatsBase):
    pass

class PlayerRound2Stats(PlayerRound2StatsBase):
    id: int
    theme_selected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ThemeSelectionRequest(BaseModel):
    player_id: int
    theme_id: int

class ThemeSelectionResponse(BaseModel):
    theme: Theme
    player_stats: PlayerRound2Stats
    message: str

class Round2QuestionRequest(BaseModel):
    player_id: int

class Round2QuestionResponse(BaseModel):
    question: Question
    question_number: int
    difficulty: int
    options: List[str]
    time_limit: int = 30

class Round2AnswerRequest(BaseModel):
    player_id: int
    question_id: int
    player_answer: str

class Round2AnswerResponse(BaseModel):
    is_correct: bool
    points_awarded: int
    player_score: int
    correct_answer: str
    next_question_available: bool

class TournamentProgress(BaseModel):
    phase: str  # "16_players", "8_qualified", "4_finalists"
    players_total: int
    players_remaining: int
    players_eliminated: int
    top_players: List[dict]

class IntermediateLeaderboardResponse(BaseModel):
    qualified_players: List[PlayerRound2Stats]
    eliminated_players: List[PlayerRound2Stats]
    cutoff_score: int
    message: str

class Round2AdvanceRequest(BaseModel):
    game_session_id: int

class Round2AdvanceResponse(BaseModel):
    new_phase: str
    qualified_count: int
    eliminated_count: int
    message: str

# Round 3 Memory Grid Enhancement Schemas

class ColorSelectionRequest(BaseModel):
    game_session_id: int
    player_id: int  # AD-0 : les couleurs appartiennent aux finalistes
    color: str

class ColorSelectionResponse(BaseModel):
    success: bool
    player_id: int
    color: str
    message: str

class ThemeSelectionRequestRound3(BaseModel):
    team_id: int
    theme_ids: List[int] = Field(..., min_length=3, max_length=3)

class ThemeSelectionResponseRound3(BaseModel):
    success: bool
    team_id: int
    theme_ids: List[int]
    message: str

class MemoryGridRound3StateResponse(BaseModel):
    memory_grid_id: int
    rows: int
    cols: int
    current_turn: int
    current_round: int = Field(1, ge=1, le=5)
    is_completed: bool
    cells: List[dict]
    teams: List[dict]

class RoundStatusResponse(BaseModel):
    round_number: int = Field(..., ge=1, le=5)
    current_team_turn: Optional[int] = None
    teams: List[dict]
    time_remaining: Optional[int] = None
    sudden_death_mode: bool = False

class GameResultResponse(BaseModel):
    winning_team_id: Optional[int] = None
    winning_team_name: Optional[str] = None
    scores: List[dict]  # [{team_id, team_name, score, color, stolen_cells}]
    total_rounds: int
    sudden_death_rounds: int = 0
    completion_time: Optional[datetime] = None

# Ping-Pong Schemas (Duel Format)
class PingPongThemeBase(BaseModel):
    title: str
    description: Optional[str] = None
    correct_answers: List[str]
    min_answers_to_win: int = 3

class PingPongThemeCreate(PingPongThemeBase):
    pass

class PingPongTheme(PingPongThemeBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class StartPingPongDuelRequest(BaseModel):
    game_session_id: int
    theme_id: int
    team1_id: int
    team2_id: int

class PingPongDuelResponse(BaseModel):
    duel_id: int
    theme: PingPongTheme
    team1: dict  # {id, name}
    team2: dict  # {id, name}
    current_turn_team_id: int
    turn_number: int
    answers_used: List[str]
    is_completed: bool
    winner_team_id: Optional[int] = None

class SubmitPingPongAnswerRequest(BaseModel):
    duel_id: int
    team_id: int
    answer: str

class SubmitPingPongAnswerResponse(BaseModel):
    is_correct: bool
    answer: str
    turn_number: int
    duel_continues: bool
    winner_team_id: Optional[int] = None
    winner_team_name: Optional[str] = None
    next_turn_team_id: Optional[int] = None
    message: str

class PingPongDuelResultsResponse(BaseModel):
    duel_id: int
    theme: PingPongTheme
    team1: dict  # {id, name, turns, correct_answers}
    team2: dict  # {id, name, turns, correct_answers}
    winner_team_id: int
    winner_team_name: str
    total_turns: int
    answers_used: List[str]
