from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum

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

# Schémas de base
class QuestionBase(BaseModel):
    text: str
    category: str
    difficulty: DifficultyEnum
    points: int = Field(..., ge=2, le=6)  # 2, 4, ou 6 points
    correct_answer: str
    wrong_answers: List[str]

class QuestionCreate(QuestionBase):
    pass

class Question(QuestionBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class PlayerBase(BaseModel):
    name: str

class PlayerCreate(PlayerBase):
    pass

class Player(PlayerBase):
    id: int
    team_id: int
    
    class Config:
        from_attributes = True

class TeamBase(BaseModel):
    name: str

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
    total_players: int = Field(..., ge=2, le=12)
    players_per_team: int = Field(..., ge=2, le=3)

class GameSessionCreate(GameSessionBase):
    pass

class GameSession(GameSessionBase):
    id: int
    code: str
    current_round: RoundTypeEnum
    current_question_id: Optional[int] = None
    is_active: bool
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

class TokenUseRequest(BaseModel):
    token_type: TokenTypeEnum
    team_id: int

class WheelSpinRequest(BaseModel):
    team_id: int

class WheelSpinResponse(BaseModel):
    effect_type: str
    value: Optional[int] = None
    message: str