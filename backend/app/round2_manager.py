from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError
import random
from datetime import datetime
from typing import List, Dict, Optional
from . import models, schemas
from .score_utils import apply_score_delta


class Round2Manager:
    """Manager pour gérer la logique métier de Round 2"""

    # Nombre de questions attendu par thème (difficulté progressive 1-10,
    # voir submit_answer/get_next_question). Un thème en dessous ne peut pas
    # être joué jusqu'au bout sans tomber sur des questions de secours
    # générées à la volée (BUG-209) — on l'exclut donc de la sélection.
    QUESTIONS_PER_THEME = 10

    def __init__(self, db: Session):
        self.db = db

    def get_available_themes(self, game_session_id: int, count: int = 3) -> List[models.Theme]:
        """Récupérer X thèmes aléatoires disponibles pour cette session.

        Exclut les thèmes déjà choisis par un autre joueur de la même partie
        (BUG-210 : sans cette exclusion, deux joueurs pouvaient se voir
        attribuer le même thème, et un joueur tardif pouvait n'avoir plus
        aucun thème distinct à choisir — BUG-202/BUG-208).

        Exclut aussi les thèmes n'ayant pas leurs 10 questions complètes
        (BUG-209 : un thème incomplet, ex. 5 questions seedées, ne peut pas
        être proposé aux joueurs).
        """
        taken_theme_ids = {
            row[0]
            for row in self.db.query(models.PlayerRound2Stats.theme_id)
            .filter(
                models.PlayerRound2Stats.game_session_id == game_session_id,
                models.PlayerRound2Stats.theme_id.isnot(None),
            )
            .all()
        }

        total_theme_count = self.db.query(models.Theme).count()
        if total_theme_count == 0:
            raise ValueError("Aucun thème disponible dans la base de données")

        complete_theme_ids = {
            row[0]
            for row in self.db.query(models.Question.theme_id)
            .filter(models.Question.theme_id.isnot(None))
            .group_by(models.Question.theme_id)
            .having(func.count(models.Question.id) >= self.QUESTIONS_PER_THEME)
            .all()
        }

        available_themes = (
            self.db.query(models.Theme)
            .filter(
                ~models.Theme.id.in_(taken_theme_ids),
                models.Theme.id.in_(complete_theme_ids),
            )
            .all()
        )
        if not available_themes:
            raise ValueError(
                "Tous les thèmes disponibles ont déjà été attribués à d'autres "
                "joueurs de cette partie"
            )

        # Sélectionner des thèmes aléatoires
        if len(available_themes) <= count:
            return available_themes

        return random.sample(available_themes, count)
    
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

        # Check if another player in this session already took this theme
        # (BUG-210 : la vérification précédente ne portait que sur le joueur
        # courant, jamais sur les autres joueurs de la même partie)
        already_taken = self.db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game_session_id,
            models.PlayerRound2Stats.player_id != player_id,
            models.PlayerRound2Stats.theme_id == theme_id,
        ).first()
        if already_taken:
            raise ValueError("Ce thème a déjà été choisi par un autre joueur")

        # Update player stats
        stats.theme_id = theme_id
        stats.theme_selected_at = datetime.now()
        stats.qualification_status = models.QualificationStatus.PLAYING
        stats.current_question_index = 0

        # Force flush and commit to ensure changes are persisted.
        # La contrainte unique (game_session_id, theme_id) en base est le
        # vrai garde-fou contre la race condition entre le check ci-dessus et
        # ce commit : deux joueurs peuvent passer le check en même temps,
        # seul le premier commit réussit.
        try:
            self.db.flush()
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Ce thème a déjà été choisi par un autre joueur")
        
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
        stats = apply_score_delta(self.db, models.PlayerRound2Stats, stats.id, points_awarded)
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
        
        # Le round1 qualifie déjà des équipes entières (8 ou 9 joueurs au
        # total, jamais plus) : ne jamais couper une équipe qualifiée ici non
        # plus. Cette coupe ne doit intervenir qu'au-delà de la tolérance
        # partagée avec advance_to_finalists.
        cutoff = self.ROUND2_SLOTS + 1
        qualified_players = all_players[:cutoff] if len(all_players) > cutoff else all_players
        eliminated_players = all_players[cutoff:] if len(all_players) > cutoff else []
        
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
        
        if len(qualified_players) not in (self.ROUND2_SLOTS, self.ROUND2_SLOTS + 1):
            raise ValueError(
                f"Attendu {self.ROUND2_SLOTS} ou {self.ROUND2_SLOTS + 1} joueurs qualifiés, "
                f"trouvé {len(qualified_players)}"
            )
        
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
        # BUG-203 (#19) : trier uniquement par score mélangeait les joueurs
        # éliminés (score gelé au moment de leur élimination) avec les
        # joueurs encore actifs, faisant passer des éliminés devant des
        # actifs avec un score plus frais mais momentanément plus bas. On
        # priorise donc le statut actif avant le score, à égalité de statut.
        top_players = []
        ranked_players = sorted(
            all_players,
            key=lambda p: (
                p.qualification_status == models.QualificationStatus.ELIMINATED,
                -p.score,
            ),
        )
        player_ids = [p.player_id for p in ranked_players[:10]]
        players_by_id = {
            p.id: p for p in self.db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
        }
        for player in ranked_players[:10]:
            player_record = players_by_id.get(player.player_id)
            top_players.append({
                "player_id": player.player_id,
                "player_name": player_record.name if player_record else f"Joueur {player.player_id}",
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

    # --- Qualification Manche 1 -> Manche 2 ---

    ROUND2_SLOTS = 8

    def qualify_players_from_round1(self, game_session_id: int) -> Dict:
        """Qualifier les joueurs de la Manche 1 vers la Manche 2.

        AD-0 : la Manche 1 est COLLECTIVE, la Manche 2 est INDIVIDUELLE (8 joueurs).
        On prend donc les meilleures équipes et TOUS leurs joueurs jusqu'à
        atteindre 8 — personne n'est éliminé individuellement dans une manche
        qui ne note que des équipes.

        AD-1 : la Manche 1 ne sert qu'à qualifier. Son score n'est pas reporté :
        chaque qualifié démarre la Manche 2 à zéro.

        AD-7 : c'est ici que GameSession.current_round passe à MANCHE_2 — la
        seule transition qui manquait au tournoi. Compare-and-set : un second
        appel concurrent échoue au lieu de dupliquer la qualification.

        AD-5 : pas de commit ici, l'endpoint possède la transaction.
        """
        game = self.db.query(models.GameSession).filter(
            models.GameSession.id == game_session_id
        ).first()
        if not game:
            raise LookupError(f"Session de jeu {game_session_id} non trouvée")

        if game.current_round != models.RoundType.MANCHE_1:
            raise ValueError(
                f"La qualification part de la Manche 1 ; la partie est en "
                f"{game.current_round.value}"
            )

        teams = self.db.query(models.Team).filter(
            models.Team.game_session_id == game_session_id
        ).order_by(models.Team.score.desc()).all()
        if not teams:
            raise ValueError("Aucune équipe à qualifier")

        qualified: List[models.Player] = []
        for team in teams:
            if len(qualified) >= self.ROUND2_SLOTS:
                break
            qualified.extend(team.players)

        if not qualified:
            raise ValueError("Aucun joueur à qualifier : les équipes sont vides")

        if len(qualified) > self.ROUND2_SLOTS + 1:
            raise ValueError(
                f"La qualification par équipes entières a dépassé la tolérance "
                f"({len(qualified)} joueurs, max {self.ROUND2_SLOTS + 1}) : "
                "composition d'équipes incompatible avec le nombre de places Manche 2"
            )

        # Chaque qualifié démarre la Manche 2 à zéro (AD-1)
        for player in qualified:
            existing = self.db.query(models.PlayerRound2Stats).filter(
                models.PlayerRound2Stats.game_session_id == game_session_id,
                models.PlayerRound2Stats.player_id == player.id,
            ).first()
            if not existing:
                self.db.add(models.PlayerRound2Stats(
                    game_session_id=game_session_id,
                    player_id=player.id,
                    score=0,
                    questions_answered=0,
                    correct_answers=0,
                    current_question_index=0,
                    qualification_status=models.QualificationStatus.PLAYING,
                ))

        # AD-7 : compare-and-set sur la phase
        updated = self.db.query(models.GameSession).filter(
            models.GameSession.id == game_session_id,
            models.GameSession.current_round == models.RoundType.MANCHE_1,
        ).update(
            {models.GameSession.current_round: models.RoundType.MANCHE_2},
            synchronize_session=False,
        )
        if updated == 0:
            raise ValueError("La partie a déjà quitté la Manche 1")

        self.db.flush()

        return {
            "game_session_id": game_session_id,
            "current_round": models.RoundType.MANCHE_2.value,
            "qualified_player_ids": [p.id for p in qualified],
            "qualified_count": len(qualified),
        }
