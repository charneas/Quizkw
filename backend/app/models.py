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
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=True)
    question_number = Column(Integer)  # 1-10 pour Round 2 (difficulty progressive)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    theme = relationship("Theme", back_populates="questions")

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
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    
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

# Enum pour les catégories de thèmes
class ThemeCategory(enum.Enum):
    SERIOUS = "serious"
    POP_CULTURE = "pop_culture"
    WHIMSICAL = "whimsical"

# Enum pour le statut de qualification
class QualificationStatus(enum.Enum):
    PLAYING = "playing"
    QUALIFIED = "qualified"
    ELIMINATED = "eliminated"
    FINALIST = "finalist"

class Theme(Base):
    __tablename__ = "themes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    category = Column(SQLEnum(ThemeCategory), nullable=False)
    difficulty_level = Column(Integer, nullable=False)  # 1-10 average
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    questions = relationship("Question", back_populates="theme")
    player_stats = relationship("PlayerRound2Stats", back_populates="theme")

class PlayerRound2Stats(Base):
    __tablename__ = "player_round2_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    theme_id = Column(Integer, ForeignKey("themes.id"))
    score = Column(Integer, default=0)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    current_question_index = Column(Integer, default=0)  # 0-9 (10 questions)
    qualification_status = Column(SQLEnum(QualificationStatus), default=QualificationStatus.PLAYING)
    theme_selected_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Relations
    player = relationship("Player")
    game_session = relationship("GameSession")
    theme = relationship("Theme", back_populates="player_stats")

# Mise à jour de GameSession pour la progression 16→8→4
# Ajout de champs pour suivre le tournoi
