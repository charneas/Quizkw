"""
Configuration de pytest pour les tests unitaires du backend Quizkw.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models
from app import schemas
from app.round2_manager import Round2Manager
from app.memory_grid import MemoryGridManager
from fastapi import FastAPI
from fastapi.testclient import TestClient
from main import app as main_app
import os
import sys

# Ajouter le chemin du backend au PATH Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# URL de base de données de test SQLite en mémoire
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    """Moteur de base de données pour les tests."""
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine

@pytest.fixture(scope="session")
def tables(engine):
    """Créer toutes les tables dans la base de données de test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(engine, tables):
    """Session de base de données isolée pour chaque test."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture
def test_client(db_session):
    """Client de test FastAPI avec base de données de test."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    main_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main_app)
    yield client
    main_app.dependency_overrides.clear()

@pytest.fixture
def round2_manager(db_session):
    """Fixture pour Round2Manager avec session de test."""
    return Round2Manager(db_session)

@pytest.fixture
def memory_grid_manager(db_session):
    """Fixture pour MemoryGridManager avec session de test."""
    return MemoryGridManager(db_session)

@pytest.fixture
def sample_game_session(db_session):
    """Créer une session de jeu de test."""
    game = models.GameSession(
        code="TEST123",
        total_players=8,
        players_per_team=2,
        current_round=models.RoundType.MANCHE_1,
        is_active=True
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    return game

@pytest.fixture
def sample_team(db_session, sample_game_session):
    """Créer une équipe de test."""
    team = models.Team(
        name="Test Team",
        game_session_id=sample_game_session.id,
        score=0
    )
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team

@pytest.fixture
def sample_player(db_session, sample_team):
    """Créer un joueur de test."""
    player = models.Player(
        name="Test Player",
        team_id=sample_team.id
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player

@pytest.fixture
def sample_theme(db_session):
    """Créer un thème de test."""
    theme = models.Theme(
        name="Test Theme",
        category=models.ThemeCategory.SERIOUS,
        difficulty_level=5,
        description="A test theme for unit tests"
    )
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme

@pytest.fixture
def sample_question(db_session, sample_theme):
    """Créer une question de test."""
    import json
    question = models.Question(
        text="What is the capital of France?",
        category="Geography",
        difficulty=models.Difficulty.EASY,
        points=2,
        correct_answer="Paris",
        wrong_answers=json.dumps(["London", "Berlin", "Madrid"]),
        theme_id=sample_theme.id,
        question_number=1
    )
    db_session.add(question)
    db_session.commit()
    db_session.refresh(question)
    return question

@pytest.fixture
def sample_questions_for_theme(db_session, sample_theme):
    """Créer 10 questions pour un thème (pour Round 2)."""
    import json
    import random
    
    questions = []
    for i in range(1, 11):
        question = models.Question(
            text=f"Test question {i} for theme {sample_theme.name}",
            category=sample_theme.category.value,
            difficulty=models.Difficulty.EASY if i <= 3 else models.Difficulty.MEDIUM if i <= 6 else models.Difficulty.HARD,
            points=2 if i <= 3 else 4 if i <= 6 else 6,
            correct_answer=f"Correct answer {i}",
            wrong_answers=json.dumps([f"Wrong {i}a", f"Wrong {i}b", f"Wrong {i}c"]),
            theme_id=sample_theme.id,
            question_number=i
        )
        db_session.add(question)
        questions.append(question)
    
    db_session.commit()
    for q in questions:
        db_session.refresh(q)
    return questions

@pytest.fixture
def sample_player_stats(db_session, sample_player, sample_game_session):
    """Créer des statistiques de joueur pour Round 2."""
    stats = models.PlayerRound2Stats(
        player_id=sample_player.id,
        game_session_id=sample_game_session.id,
        score=0,
        questions_answered=0,
        correct_answers=0,
        current_question_index=0,
        qualification_status=models.QualificationStatus.PLAYING
    )
    db_session.add(stats)
    db_session.commit()
    db_session.refresh(stats)
    return stats
