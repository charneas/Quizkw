#!/usr/bin/env python3
"""
Script de peuplement de la base de données pour les tests
Permet de créer des données de test réalistes pour le quiz
"""

import asyncio
import json
import random
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, Question, Difficulty, GameSession, Team, Player, Token, TokenType, RoundType

# Créer toutes les tables
Base.metadata.create_all(bind=engine)

def seed_questions(db: Session):
    """Peupler la base avec des questions de test"""
    
    questions_data = [
        # Questions faciles (2 points)
        {
            "text": "Quelle est la capitale de la France ?",
            "category": "Géographie",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "Paris",
            "wrong_answers": ["Londres", "Berlin", "Madrid"]
        },
        {
            "text": "Qui a peint la Joconde ?",
            "category": "Art",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "Léonard de Vinci",
            "wrong_answers": ["Michel-Ange", "Raphaël", "Van Gogh"]
        },
        {
            "text": "Combien de continents y a-t-il sur Terre ?",
            "category": "Géographie",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "7",
            "wrong_answers": ["5", "6", "8"]
        },
        
        # Questions moyennes (4 points)
        {
            "text": "Quel est le plus grand océan du monde ?",
            "category": "Géographie",
            "difficulty": Difficulty.MEDIUM,
            "points": 4,
            "correct_answer": "Océan Pacifique",
            "wrong_answers": ["Océan Atlantique", "Océan Indien", "Océan Arctique"]
        },
        {
            "text": "En quelle année a eu lieu la Révolution française ?",
            "category": "Histoire",
            "difficulty": Difficulty.MEDIUM,
            "points": 4,
            "correct_answer": "1789",
            "wrong_answers": ["1776", "1792", "1815"]
        },
        
        # Questions difficiles (6 points)
        {
            "text": "Quel philosophe a écrit 'Ainsi parlait Zarathoustra' ?",
            "category": "Philosophie",
            "difficulty": Difficulty.HARD,
            "points": 6,
            "correct_answer": "Friedrich Nietzsche",
            "wrong_answers": ["Platon", "Kant", "Descartes"]
        },
        {
            "text": "Quelle est la formule chimique de l'eau ?",
            "category": "Sciences",
            "difficulty": Difficulty.HARD,
            "points": 6,
            "correct_answer": "H₂O",
            "wrong_answers": ["CO₂", "NaCl", "C₆H₁₂O₆"]
        }
    ]
    
    for q_data in questions_data:
        question = Question(
            text=q_data["text"],
            category=q_data["category"],
            difficulty=q_data["difficulty"],
            points=q_data["points"],
            correct_answer=q_data["correct_answer"],
            wrong_answers=json.dumps(q_data["wrong_answers"])
        )
        db.add(question)
    
    db.commit()
    print(f"✅ {len(questions_data)} questions créées")

def seed_game_session(db: Session):
    """Créer une session de jeu de test"""
    
    # Créer la session de jeu
    game = GameSession(
        code="TEST123",
        current_round=RoundType.MANCHE_1,
        total_players=6,
        players_per_team=2
    )
    db.add(game)
    db.flush()  # Pour obtenir l'ID
    
    # Créer 3 équipes
    teams = []
    for i in range(3):
        team = Team(
            name=f"Équipe {i+1}",
            game_session_id=game.id,
            score=0
        )
        db.add(team)
        teams.append(team)
    
    db.flush()
    
    # Créer 2 joueurs par équipe
    player_names = [
        ["Alice", "Bob"],
        ["Charlie", "Diana"],
        ["Eve", "Frank"]
    ]
    
    for i, team in enumerate(teams):
        for j, name in enumerate(player_names[i]):
            player = Player(
                name=name,
                team_id=team.id
            )
            db.add(player)
    
    # Donner 3 jetons à chaque équipe
    token_types = [TokenType.SWAP, TokenType.PENALTY, TokenType.BONUS]
    for team in teams:
        for token_type in token_types:
            token = Token(
                team_id=team.id,
                token_type=token_type,
                is_used=False
            )
            db.add(token)
    
    db.commit()
    print("✅ Session de jeu de test créée avec 3 équipes et 6 joueurs")
    print(f"   Code de la partie: {game.code}")

def main():
    """Fonction principale"""
    db = SessionLocal()
    
    try:
        print("🧪 Début du peuplement de la base de données...")
        
        # Vider les tables existantes (pour les tests)
        db.query(Token).delete()
        db.query(Player).delete()
        db.query(Team).delete()
        db.query(GameSession).delete()
        db.query(Question).delete()
        db.commit()
        
        # Peupler les données
        seed_questions(db)
        seed_game_session(db)
        
        print("🎉 Base de données peuplée avec succès !")
        print("\n📊 Données créées:")
        print(f"   - Questions: {db.query(Question).count()}")
        print(f"   - Sessions de jeu: {db.query(GameSession).count()}")
        print(f"   - Équipes: {db.query(Team).count()}")
        print(f"   - Joueurs: {db.query(Player).count()}")
        print(f"   - Jetons: {db.query(Token).count()}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors du peuplement: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()