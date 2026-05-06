from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import random
from datetime import datetime
from typing import List, Dict, Optional
from . import models, schemas


class Round2Manager:
    """Manager pour gérer la logique métier de Round 2"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_available_themes(self, count: int = 3) -> List[models.Theme]:
        """Récupérer X thèmes aléatoires disponibles"""
        # Pour MVP: retourner tous les thèmes disponibles
        all_themes = self.db.query(models.Theme).all()
        if not all_themes:
            raise ValueError("Aucun thème disponible dans la base de données")
        
        # Sélectionner des thèmes aléatoires
        if len(all_themes) <= count:
            return all_themes
        
        return random.sample(all_themes, count)
    
    def get_player_stats(self, player_id: int, game_session_id: int) -> models.PlayerRound2Stats:
        """Get or create Round 2 statistics for a player"""
        # RADICAL FIX: Clear ALL cached objects and use aggressive approach
        self.db.expire_all()
        
        # Use with_for_update to prevent race conditions and force fresh query
        stats = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.player_id == player_id,
            models.PlayerRound2Stats.game_session_id == game_session_id
        ).with_for_update().first()
        
        if not stats:
            # RADICAL FIX: Create object with explicit attribute setting
            # This avoids SQLAlchemy constructor bugs
            stats = models.PlayerRound2Stats()
            # Set attributes directly to ensure they're set correctly
            stats.player_id = player_id
            stats.game_session_id = game_session_id
            stats.qualification_status = models.QualificationStatus.PLAYING
            # Initialize other fields
            stats.score = 0
            stats.questions_answered = 0
            stats.correct_answers = 0
            stats.current_question_index = 0
            stats.theme_id = None
            stats.theme_selected_at = None
            stats.completed_at = None
            
            self.db.add(stats)
            self.db.commit()
            self.db.refresh(stats)
            
            # VERIFICATION: Immediately check the object
            if stats.player_id != player_id:
                raise ValueError(
                    f"CRITICAL BUG: Created object has wrong player_id! "
                    f"Expected {player_id}, got {stats.player_id}"
                )
        
        # FINAL VERIFICATION
        if stats.player_id != player_id:
            raise ValueError(
                f"CRITICAL BUG: Retrieved object has wrong player_id! "
                f"Expected {player_id}, got {stats.player_id}"
            )
        
        return stats
    
    def select_theme(self, player_id: int, game_session_id: int, theme_id: int) -> models.PlayerRound2Stats:
        """Allow a player to select a theme"""
        # Check if theme exists
        theme = self.db.query(models.Theme).filter(models.Theme.id == theme_id).first()
        if not theme:
            raise ValueError(f"Theme with ID {theme_id} not found")
        
        # Check if player has already selected a theme
        stats = self.get_player_stats(player_id, game_session_id)
        if stats.theme_id is not None:
            raise ValueError("Player has already selected a theme")
        
        # Update player stats
        stats.theme_id = theme_id
        stats.theme_selected_at = datetime.now()
        stats.qualification_status = models.QualificationStatus.PLAYING
        stats.current_question_index = 0
        
        # Force flush and commit to ensure changes are persisted
        self.db.flush()
        self.db.commit()
        
        # CRITICAL FIX: Clear session cache and re-query to avoid object identity issues
        self.db.expire_all()
        
        # Re-query the stats to get a fresh object
        fresh_stats = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.player_id == player_id,
            models.PlayerRound2Stats.game_session_id == game_session_id
        ).first()
        
        if not fresh_stats:
            raise ValueError(f"Failed to retrieve stats after update for player {player_id}")
        
        # Double-check that theme_id was saved
        if fresh_stats.theme_id != theme_id:
            raise ValueError(f"Failed to save theme selection: expected {theme_id}, got {fresh_stats.theme_id}")
        
        return fresh_stats
    
    def get_next_question(self, player_id: int, game_session_id: int) -> Optional[models.Question]:
        """Récupérer la prochaine question pour un joueur"""
        stats = self.get_player_stats(player_id, game_session_id)
        
        if not stats.theme_id:
            raise ValueError("Le joueur doit d'abord sélectionner un thème")
        
        # Vérifier si le joueur a terminé les 10 questions
        if stats.current_question_index >= 10:
            return None
        
        # Récupérer la question correspondant au thème et au numéro
        question = self.db.query(models.Question).filter(
            models.Question.theme_id == stats.theme_id,
            models.Question.question_number == stats.current_question_index + 1
        ).first()
        
        if not question:
            # Pour MVP: créer une question générique si pas trouvée
            question = self._create_fallback_question(stats.theme_id, stats.current_question_index + 1)
        
        return question
    
    def submit_answer(self, player_id: int, game_session_id: int, question_id: int, player_answer: str) -> Dict:
        """Soumettre une réponse et calculer le score"""
        stats = self.get_player_stats(player_id, game_session_id)
        
        # Vérifier si le joueur peut encore répondre
        if stats.qualification_status != models.QualificationStatus.PLAYING:
            raise ValueError("Le joueur ne participe plus à ce round")
        
        # Récupérer la question
        question = self.db.query(models.Question).filter(models.Question.id == question_id).first()
        if not question:
            raise ValueError(f"Question avec ID {question_id} non trouvée")
        
        # Vérifier que la question correspond au thème et au numéro attendu
        if question.theme_id != stats.theme_id or question.question_number != stats.current_question_index + 1:
            raise ValueError("Question non valide pour le joueur")
        
        # Calculer le score (difficulté 1-10 correspondant à question_number)
        difficulty = question.question_number
        is_correct = player_answer.strip().lower() == question.correct_answer.strip().lower()
        
        if is_correct:
            points_awarded = difficulty
            stats.correct_answers += 1
        else:
            points_awarded = 0
        
        # Mettre à jour les stats
        stats.score += points_awarded
        stats.questions_answered += 1
        stats.current_question_index += 1
        
        # Si le joueur a terminé les 10 questions
        if stats.current_question_index >= 10:
            stats.completed_at = datetime.now()
            stats.qualification_status = models.QualificationStatus.QUALIFIED
        
        self.db.commit()
        
        return {
            "is_correct": is_correct,
            "points_awarded": points_awarded,
            "player_score": stats.score,
            "correct_answer": question.correct_answer,
            "next_question_available": stats.current_question_index < 10
        }
    
    def calculate_intermediate_leaderboard(self, game_session_id: int) -> schemas.IntermediateLeaderboardResponse:
        """Calculer le classement intermédiaire après la première passe (top 8)"""
        # Récupérer tous les joueurs de cette session qui ont terminé
        all_players = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game_session_id,
            models.PlayerRound2Stats.qualification_status == models.QualificationStatus.QUALIFIED
        ).order_by(desc(models.PlayerRound2Stats.score)).all()
        
        # Pour MVP: top 8 qualifiés
        qualified_players = all_players[:8] if len(all_players) >= 8 else all_players
        eliminated_players = all_players[8:] if len(all_players) > 8 else []
        
        # Mettre à jour les statuts
        cutoff_score = qualified_players[-1].score if qualified_players else 0
        
        for player in qualified_players:
            player.qualification_status = models.QualificationStatus.QUALIFIED
        
        for player in eliminated_players:
            player.qualification_status = models.QualificationStatus.ELIMINATED
        
        self.db.commit()
        
        return schemas.IntermediateLeaderboardResponse(
            qualified_players=qualified_players,
            eliminated_players=eliminated_players,
            cutoff_score=cutoff_score,
            message=f"Top {len(qualified_players)} qualifiés pour la phase suivante"
        )
    
    def advance_to_finalists(self, game_session_id: int) -> schemas.Round2AdvanceResponse:
        """Déterminer les 4 finalistes parmi les 8 qualifiés"""
        # Récupérer les 8 qualifiés
        qualified_players = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game_session_id,
            models.PlayerRound2Stats.qualification_status == models.QualificationStatus.QUALIFIED
        ).order_by(desc(models.PlayerRound2Stats.score)).all()
        
        if len(qualified_players) != 8:
            raise ValueError(f"Attendu 8 joueurs qualifiés, trouvé {len(qualified_players)}")
        
        # Top 4 deviennent finalistes
        finalists = qualified_players[:4]
        eliminated = qualified_players[4:]
        
        # Mettre à jour les statuts
        for player in finalists:
            player.qualification_status = models.QualificationStatus.FINALIST
        
        for player in eliminated:
            player.qualification_status = models.QualificationStatus.ELIMINATED
        
        self.db.commit()
        
        return schemas.Round2AdvanceResponse(
            new_phase="4_finalists",
            qualified_count=len(finalists),
            eliminated_count=len(eliminated),
            message=f"{len(finalists)} finalistes déterminés pour Round 3"
        )
    
    def get_tournament_progress(self, game_session_id: int) -> schemas.TournamentProgress:
        """Obtenir l'état de progression du tournoi 16→8→4"""
        all_players = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game_session_id
        ).all()
        
        playing = [p for p in all_players if p.qualification_status == models.QualificationStatus.PLAYING]
        qualified = [p for p in all_players if p.qualification_status == models.QualificationStatus.QUALIFIED]
        finalists = [p for p in all_players if p.qualification_status == models.QualificationStatus.FINALIST]
        eliminated = [p for p in all_players if p.qualification_status == models.QualificationStatus.ELIMINATED]
        
        # Déterminer la phase actuelle
        if finalists:
            phase = "4_finalists"
        elif qualified and len(qualified) >= 8:
            phase = "8_qualified"
        else:
            phase = "16_players"
        
        # Créer la liste des meilleurs joueurs
        top_players = []
        for player in sorted(all_players, key=lambda p: p.score, reverse=True)[:10]:
            top_players.append({
                "player_id": player.player_id,
                "score": player.score,
                "status": player.qualification_status.value
            })
        
        return schemas.TournamentProgress(
            phase=phase,
            players_total=len(all_players),
            players_remaining=len(playing) + len(qualified) + len(finalists),
            players_eliminated=len(eliminated),
            top_players=top_players
        )
    
    def _create_fallback_question(self, theme_id: int, question_number: int) -> models.Question:
        """Créer une question de secours pour le MVP"""
        theme = self.db.query(models.Theme).filter(models.Theme.id == theme_id).first()
        
        # Pour MVP: questions simplifiées
        difficulty_map = {1: "easy", 5: "medium", 10: "hard"}
        difficulty_key = question_number if question_number in difficulty_map else 5
        
        import json
        question = models.Question(
            text=f"Question {question_number} sur le thème '{theme.name}' (difficulté {question_number}/10)",
            category=theme.category.value,
            difficulty=models.Difficulty(difficulty_map[difficulty_key]),
            points=2 if question_number <= 3 else 4 if question_number <= 6 else 6,
            correct_answer="Réponse correcte",
            wrong_answers=json.dumps(["Fausse réponse 1", "Fausse réponse 2", "Fausse réponse 3"]),
            theme_id=theme_id,
            question_number=question_number
        )
        
        self.db.add(question)
        self.db.commit()
        self.db.refresh(question)
        
        return question
    
    def get_game_players(self, game_session_id: int) -> List[models.Player]:
        """Récupérer tous les joueurs d'une session de jeu"""
        game = self.db.query(models.GameSession).filter(models.GameSession.id == game_session_id).first()
        if not game:
            raise ValueError(f"Session de jeu avec ID {game_session_id} non trouvée")
        
        players = []
        for team in game.teams:
            players.extend(team.players)
        
        return players