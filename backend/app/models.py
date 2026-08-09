from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import secrets
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

class PropositionStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

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
    host_token = Column(String, nullable=False, default=lambda: secrets.token_urlsafe(24))
    started = Column(Boolean, default=False, nullable=False)
    questions_played = Column(Integer, default=0, nullable=False)  # déclenche la roue tous les 5
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    current_question = relationship("Question")
    teams = relationship("Team", back_populates="game_session")
    wheel_effects = relationship("WheelEffect", back_populates="game_session")

class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("game_session_id", "name", name="uq_team_session_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    score = Column(Integer, default=0)
    color = Column(String, nullable=True)  # Round 3 color selection
    selected_theme_ids = Column(JSON, nullable=True)  # Round 3 selected theme IDs [1,2,3]
    bonus_active = Column(Boolean, default=False, nullable=False)  # Jeton BONUS consommé sur la prochaine validation
    # BUG-101d : jamais vérifié jusqu'ici (team_id brut, non authentifié) sur
    # les endpoints qui consomment les jetons de l'équipe. Généré à la
    # création de l'équipe, renvoyé une fois (create_team) puis à chaque
    # adhésion (join_team, qui reste public — voir décision produit sur #55)
    # afin que tous les coéquipiers d'une même équipe l'obtiennent.
    team_token = Column(String, nullable=False, default=lambda: secrets.token_urlsafe(24))

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
    __table_args__ = (
        # BUG-110 : une seule réponse par équipe et par question — la contrainte
        # doit vivre ici (pas seulement dans la migration) pour que les bases
        # créées via Base.metadata.create_all (tests, dev) l'appliquent aussi.
        UniqueConstraint('question_id', 'team_id', name='ix_answers_question_team_unique'),
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    player_answer = Column(String)
    is_correct = Column(Boolean)
    points_earned = Column(Integer, default=0)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True), nullable=True)

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
    propositions = relationship("Proposition", back_populates="theme")

class Proposition(Base):
    """Proposition de question soumise publiquement (AD-18) : entité distincte
    de Question, jamais interrogée par le pool de jeu. Seule l'acceptation
    (Story F-ext-2.4, hors périmètre ici) crée la Question correspondante."""
    __tablename__ = "propositions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    correct_answer = Column(String, nullable=False)
    wrong_answers = Column(String)  # Stocker les mauvaises réponses en JSON, comme Question
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=True)  # NULL = "à déterminer"
    difficulty = Column(SQLEnum(Difficulty), nullable=False)
    status = Column(SQLEnum(PropositionStatus), nullable=False, default=PropositionStatus.PENDING, server_default="PENDING")
    rejection_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relations
    theme = relationship("Theme", back_populates="propositions")

class Admin(Base):
    """Compte administrateur (AD-17) : identité minimale pour protéger `/admin/*`.
    Le cookie de session est stateless (signé, pas persisté) — cette table ne
    porte donc que l'identifiant et le mot de passe hashé, aucune session."""
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PlayerRound2Stats(Base):
    __tablename__ = "player_round2_stats"
    __table_args__ = (
        UniqueConstraint("game_session_id", "theme_id", name="uq_round2_session_theme"),
    )

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

class PlayerRound3Stats(Base):
    """Axe de score individuel de la Manche 3.

    AD-0 : la Manche 3 est individuelle, exactement 4 finalistes.
    AD-1 : trois axes de score cloisonnés, un par manche. C'est le SEUL endroit
    où un score de Manche 3 s'écrit — Team.score n'est jamais touché par la
    Manche 3, et aucun total inter-manches n'existe.
    """
    __tablename__ = "player_round3_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    score = Column(Integer, default=0, nullable=False)
    cells_claimed = Column(Integer, default=0, nullable=False)
    color = Column(String, nullable=True)  # couleur du finaliste sur la grille
    selected_theme_ids = Column(JSON, nullable=True)  # 3 thèmes choisis par le finaliste
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relations
    player = relationship("Player")
    game_session = relationship("GameSession")


class PingPongTheme(Base):
    __tablename__ = "ping_pong_themes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    correct_answers = Column(JSON, nullable=False)  # Liste des réponses valides
    min_answers_to_win = Column(Integer, default=3)  # Minimum de réponses pour gagner
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PingPongDuel(Base):
    __tablename__ = "ping_pong_duels"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"))
    theme_id = Column(Integer, ForeignKey("ping_pong_themes.id"))
    team1_id = Column(Integer, ForeignKey("teams.id"))
    team2_id = Column(Integer, ForeignKey("teams.id"))
    current_turn_team_id = Column(Integer, ForeignKey("teams.id"))  # Équipe dont c'est le tour
    winner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    is_completed = Column(Boolean, default=False)
    answers_used = Column(JSON, default=list)  # Liste des réponses déjà données (pour éviter les doublons)
    is_tiebreak = Column(Boolean, default=False, nullable=False)  # départage de qualification fin de Manche 1
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relations
    game_session = relationship("GameSession", foreign_keys=[game_session_id])
    theme = relationship("PingPongTheme")
    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
    current_turn_team = relationship("Team", foreign_keys=[current_turn_team_id])
    winner_team = relationship("Team", foreign_keys=[winner_team_id])

class PingPongTurn(Base):
    __tablename__ = "ping_pong_turns"
    
    id = Column(Integer, primary_key=True, index=True)
    duel_id = Column(Integer, ForeignKey("ping_pong_duels.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    answer_given = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    turn_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relations
    duel = relationship("PingPongDuel")
    team = relationship("Team")

# Mise à jour de GameSession pour la progression 16→8→4
# Ajout de champs pour suivre le tournoi

# Story F.2 : génération semi-automatique de contenu (Wikipedia + Claude)

class SuggestionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class ContentSuggestion(Base):
    """Contenu généré par le pipeline Wikipedia -> LLM, en attente de validation
    humaine. Rien n'est écrit dans Theme/Question avant approve (AC #2)."""
    __tablename__ = "content_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, nullable=False)
    wikipedia_extract = Column(String, nullable=False)
    generated_theme_name = Column(String, nullable=False)
    generated_category = Column(SQLEnum(ThemeCategory), nullable=False)
    generated_questions = Column(JSON, nullable=False)  # liste de dicts bruts, validés par schémas Pydantic avant écriture ici
    status = Column(SQLEnum(SuggestionStatus), nullable=False, default=SuggestionStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String, nullable=True)
    created_theme_id = Column(Integer, ForeignKey("themes.id"), nullable=True)  # rempli à l'approve

class ContentFlag(Base):
    """Signalement d'une question par un joueur (AC #4)."""
    __tablename__ = "content_flags"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    reason = Column(String, nullable=False)
    flagged_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(String, nullable=True)

    question = relationship("Question")

class ContentHistory(Base):
    """Journal d'audit des écritures de contenu (AC #5) : F.1 (thèmes/questions)
    et F.2 (génération, approve/reject, résolution de signalement)."""
    __tablename__ = "content_history"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)  # "theme" | "question" | "suggestion" | "flag"
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)  # "created" | "updated" | "deleted" | "generated" | "approved" | "rejected" | "flagged" | "resolved"
    detail = Column(String, nullable=True)
    actor = Column(String, nullable=False, default="admin")  # pas d'identité (spine différée) : valeur fixe
    created_at = Column(DateTime(timezone=True), server_default=func.now())
