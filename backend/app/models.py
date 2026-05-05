from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .database import Base

# Enums pour les types de difficulté et de jetons
class Difficulty(enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class TokenType(enum.Enum):
    SWAP = "swap"
    PENALTY = "penalty"
    BONUS = "bonus"

class RoundType(enum.Enum):
    MANCHE_1 = "manche_1"
    MANCHE_2 = "manche_2"
    MANCHE_3 = "manche_3"

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    category = Column(String, nullable=False)
    difficulty = Column(SQLEnum(Difficulty), nullable=False)
    points = Column(Integer, nullable=False)  # 2, 4, ou 6 points selon difficulté
    correct_answer = Column(String, nullable=False)
    wrong_answers = Column(String)  # Stocker les mauvaises réponses en JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GameSession(Base):
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)  # Code pour rejoindre la partie
    current_round = Column(SQLEnum(RoundType), default=RoundType.MANCHE_1)
    current_question_id = Column(Integer, ForeignKey("questions.id"))
    total_players = Column(Integer, nullable=False)
    players_per_team = Column(Integer, nullable=False)  # 2 ou 3 selon règles
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    current_question = relationship("Question")
    teams = relationship("Team", back_populates="game_session")
    wheel_effects = relationship("WheelEffect", back_populates="game_session")

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    score = Column(Integer, default=0)
    
    # Relations
    game_session = relationship("GameSession", back_populates="teams")
    players = relationship("Player", back_populates="team")
    tokens = relationship("Token", back_populates="team")

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"))
    
    # Relations
    team = relationship("Team", back_populates="players")

class Token(Base):
    __tablename__ = "tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    token_type = Column(SQLEnum(TokenType), nullable=False)
    is_used = Column(Boolean, default=False)
    
    # Relations
    team = relationship("Team", back_populates="tokens")

class WheelEffect(Base):
    __tablename__ = "wheel_effects"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    effect_type = Column(String, nullable=False)  # "malus", "bonus", "ping_pong", etc.
    value = Column(Integer)  # Valeur numérique si applicable
    target_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    is_applied = Column(Boolean, default=False)
    
    # Relations
    game_session = relationship("GameSession", back_populates="wheel_effects")
    target_team = relationship("Team")

class Answer(Base):
    __tablename__ = "answers"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    player_answer = Column(String)
    is_correct = Column(Boolean)
    points_earned = Column(Integer, default=0)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    question = relationship("Question")
    team = relationship("Team")