"""
Tests unitaires pour Round2Manager - le composant le plus critique avec des bugs historiques.
Ces tests doivent être reproductibles et isolés.
"""
import pytest
from datetime import datetime
from app.models import QualificationStatus
import json

class TestRound2Manager:
    """Tests pour la classe Round2Manager."""
    
    def test_get_available_themes(self, round2_manager, sample_theme):
        """Test que get_available_themes retourne des thèmes disponibles."""
        themes = round2_manager.get_available_themes(count=3)
        assert len(themes) > 0
        assert isinstance(themes, list)
        # Au moins notre thème de test devrait être présent
        theme_names = [theme.name for theme in themes]
        assert "Test Theme" in theme_names
        
    def test_get_available_themes_no_themes(self, round2_manager, db_session):
        """Test get_available_themes quand il n'y a pas de thèmes."""
        # Supprimer tous les thèmes
        db_session.query(self._get_theme_model()).delete()
        db_session.commit()
        
        with pytest.raises(ValueError, match="Aucun thème disponible"):
            round2_manager.get_available_themes(count=3)
            
    def _get_theme_model(self):
        """Helper pour obtenir le modèle Theme depuis l'import."""
        from app.models import Theme
        return Theme
    
    def test_get_player_stats_existing(self, round2_manager, sample_player_stats):
        """Test get_player_stats avec des stats existantes."""
        stats = round2_manager.get_player_stats(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id
        )
        
        assert stats.id == sample_player_stats.id
        assert stats.player_id == sample_player_stats.player_id
        assert stats.game_session_id == sample_player_stats.game_session_id
        assert stats.qualification_status == QualificationStatus.PLAYING
        
    def test_get_player_stats_new(self, round2_manager, sample_player, sample_game_session):
        """Test get_player_stats avec un nouveau joueur (création automatique)."""
        # Supprimer les stats existantes pour ce joueur
        from app.models import PlayerRound2Stats
        round2_manager.db.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.player_id == sample_player.id,
            PlayerRound2Stats.game_session_id == sample_game_session.id
        ).delete()
        round2_manager.db.commit()
        
        stats = round2_manager.get_player_stats(
            player_id=sample_player.id,
            game_session_id=sample_game_session.id
        )
        
        assert stats.player_id == sample_player.id
        assert stats.game_session_id == sample_game_session.id
        assert stats.score == 0

    def test_select_theme_success(self, round2_manager, sample_player, sample_game_session, sample_theme):
        """Test sélection de thème réussie."""
        # S'assurer qu'il n'y a pas de stats existantes pour ce joueur
        from app.models import PlayerRound2Stats
        round2_manager.db.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.player_id == sample_player.id,
            PlayerRound2Stats.game_session_id == sample_game_session.id
        ).delete()
        round2_manager.db.commit()
        
        stats = round2_manager.select_theme(
            player_id=sample_player.id,
            game_session_id=sample_game_session.id,
            theme_id=sample_theme.id
        )
        
        assert stats.player_id == sample_player.id
        assert stats.game_session_id == sample_game_session.id
        assert stats.theme_id == sample_theme.id
        assert stats.theme_selected_at is not None
        assert stats.qualification_status == QualificationStatus.PLAYING
        assert stats.current_question_index == 0
        
    def test_select_theme_already_selected(self, round2_manager, sample_player_stats, sample_theme):
        """Test sélection de thème quand un thème est déjà sélectionné."""
        # Définir un thème pour les stats existantes
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.theme_selected_at = datetime.now()
        round2_manager.db.commit()
        
        with pytest.raises(ValueError, match="Player has already selected a theme"):
            round2_manager.select_theme(
                player_id=sample_player_stats.player_id,
                game_session_id=sample_player_stats.game_session_id,
                theme_id=sample_theme.id
            )
            
    def test_select_theme_invalid_theme(self, round2_manager, sample_player, sample_game_session):
        """Test sélection de thème avec un thème inexistant."""
        with pytest.raises(ValueError, match="Theme with ID"):
            round2_manager.select_theme(
                player_id=sample_player.id,
                game_session_id=sample_game_session.id,
                theme_id=99999  # ID inexistant
            )
            
    def test_get_next_question_success(self, round2_manager, sample_player_stats, sample_theme, sample_questions_for_theme):
        """Test récupération de la prochaine question après sélection de thème."""
        # Définir le thème pour les stats
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.theme_selected_at = datetime.now()
        round2_manager.db.commit()
        
        question = round2_manager.get_next_question(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id
        )
        
        assert question is not None
        assert question.theme_id == sample_theme.id
        assert question.question_number == 1  # Premier numéro de question
        
    def test_get_next_question_no_theme(self, round2_manager, sample_player_stats):
        """Test récupération de question sans thème sélectionné."""
        # S'assurer qu'aucun thème n'est sélectionné
        sample_player_stats.theme_id = None
        round2_manager.db.commit()
        
        with pytest.raises(ValueError, match="Le joueur doit d'abord sélectionner un thème"):
            round2_manager.get_next_question(
                player_id=sample_player_stats.player_id,
                game_session_id=sample_player_stats.game_session_id
            )
            
    def test_get_next_question_completed(self, round2_manager, sample_player_stats, sample_theme):
        """Test récupération de question quand le joueur a terminé."""
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.current_question_index = 10  # Toutes les questions terminées
        round2_manager.db.commit()
        
        question = round2_manager.get_next_question(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id
        )
        
        assert question is None  # Aucune question disponible
        
    def test_submit_answer_correct(self, round2_manager, sample_player_stats, sample_theme, sample_questions_for_theme):
        """Test soumission de réponse correcte."""
        # Configurer les stats
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.theme_selected_at = datetime.now()
        round2_manager.db.commit()
        
        # Récupérer la première question
        question = sample_questions_for_theme[0]
        
        result = round2_manager.submit_answer(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id,
            question_id=question.id,
            player_answer=question.correct_answer
        )
        
        assert result["is_correct"] is True
        assert result["points_awarded"] == question.question_number  # Points = numéro de question
        assert result["player_score"] == question.question_number
        assert result["correct_answer"] == question.correct_answer
        assert result["next_question_available"] is True
        
        # Vérifier que les stats ont été mises à jour
        updated_stats = round2_manager.get_player_stats(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id
        )
        assert updated_stats.score == question.question_number
        assert updated_stats.questions_answered == 1
        assert updated_stats.correct_answers == 1
        assert updated_stats.current_question_index == 1
        
    def test_submit_answer_incorrect(self, round2_manager, sample_player_stats, sample_theme, sample_questions_for_theme):
        """Test soumission de réponse incorrecte."""
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.theme_selected_at = datetime.now()
        round2_manager.db.commit()
        
        question = sample_questions_for_theme[0]
        
        result = round2_manager.submit_answer(
            player_id=sample_player_stats.player_id,
            game_session_id=sample_player_stats.game_session_id,
            question_id=question.id,
            player_answer="Wrong answer"
        )
        
        assert result["is_correct"] is False
        assert result["points_awarded"] == 0
        assert result["player_score"] == 0
        assert result["correct_answer"] == question.correct_answer
        assert result["next_question_available"] is True
        
    def test_submit_answer_invalid_question(self, round2_manager, sample_player_stats):
        """Test soumission de réponse avec question invalide."""
        with pytest.raises(ValueError, match="Question avec ID"):
            round2_manager.submit_answer(
                player_id=sample_player_stats.player_id,
                game_session_id=sample_player_stats.game_session_id,
                question_id=99999,  # ID inexistant
                player_answer="Answer"
            )
            
    def test_submit_answer_wrong_question_number(self, round2_manager, sample_player_stats, sample_theme, sample_questions_for_theme):
        """Test soumission de réponse avec mauvais numéro de question."""
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.theme_selected_at = datetime.now()
        sample_player_stats.current_question_index = 2  # À la question 3
        round2_manager.db.commit()
        
        question = sample_questions_for_theme[0]  # Question numéro 1
        
        with pytest.raises(ValueError, match="Question non valide"):
            round2_manager.submit_answer(
                player_id=sample_player_stats.player_id,
                game_session_id=sample_player_stats.game_session_id,
                question_id=question.id,
                player_answer="Answer"
            )
            
    def test_submit_answer_player_not_playing(self, round2_manager, sample_player_stats, sample_theme, sample_questions_for_theme):
        """Test soumission de réponse quand le joueur ne participe plus."""
        sample_player_stats.theme_id = sample_theme.id
        sample_player_stats.qualification_status = QualificationStatus.ELIMINATED
        round2_manager.db.commit()
        
        question = sample_questions_for_theme[0]
        
        with pytest.raises(ValueError, match="Le joueur ne participe plus à ce round"):
            round2_manager.submit_answer(
                player_id=sample_player_stats.player_id,
                game_session_id=sample_player_stats.game_session_id,
                question_id=question.id,
                player_answer=question.correct_answer
            )
            
    def test_calculate_intermediate_leaderboard(self, round2_manager, sample_game_session):
        """Test calcul du classement intermédiaire."""
        # Créer plusieurs joueurs avec différents scores
        from app.models import Player, PlayerRound2Stats
        
        players_data = [
            ("Player1", 85),
            ("Player2", 75),
            ("Player3", 60),
            ("Player4", 55),
            ("Player5", 50),
            ("Player6", 45),
            ("Player7", 40),
            ("Player8", 35),
            ("Player9", 30),
            ("Player10", 25),
        ]
        
        created_players = []
        for name, score in players_data:
            # Créer joueur et stats
            player = Player(name=name, team_id=None)
            round2_manager.db.add(player)
            round2_manager.db.flush()
            
            stats = PlayerRound2Stats(
                player_id=player.id,
                game_session_id=sample_game_session.id,
                score=score,
                questions_answered=10,
                correct_answers=score//10,  # Approximation
                current_question_index=10,
                qualification_status=QualificationStatus.QUALIFIED
            )
            round2_manager.db.add(stats)
            created_players.append((player, stats))
        
        round2_manager.db.commit()
        
        leaderboard = round2_manager.calculate_intermediate_leaderboard(sample_game_session.id)
        
        assert len(leaderboard.qualified_players) == 8
        assert len(leaderboard.eliminated_players) == 2
        assert leaderboard.cutoff_score == 35  # Score du 8ème joueur
        
        # Vérifier que les statuts ont été mis à jour
        for player, stats in created_players[:8]:
            fresh_stats = round2_manager.db.query(PlayerRound2Stats).filter(
                PlayerRound2Stats.player_id == player.id
            ).first()
            assert fresh_stats.qualification_status == QualificationStatus.QUALIFIED
            
        for player, stats in created_players[8:]:
            fresh_stats = round2_manager.db.query(PlayerRound2Stats).filter(
                PlayerRound2Stats.player_id == player.id
            ).first()
            assert fresh_stats.qualification_status == QualificationStatus.ELIMINATED
            
    def test_advance_to_finalists(self, round2_manager, sample_game_session):
        """Test avancement vers les finalistes (8 → 4)."""
        from app.models import Player, PlayerRound2Stats
        
        # Créer 8 joueurs qualifiés
        for i in range(8):
            player = Player(name=f"QualifiedPlayer{i}", team_id=None)
            round2_manager.db.add(player)
            round2_manager.db.flush()
            
            stats = PlayerRound2Stats(
                player_id=player.id,
                game_session_id=sample_game_session.id,
                score=100 - i*10,  # Scores décroissants
                questions_answered=10,
                correct_answers=8,
                current_question_index=10,
                qualification_status=QualificationStatus.QUALIFIED
            )
            round2_manager.db.add(stats)
        
        round2_manager.db.commit()
        
        result = round2_manager.advance_to_finalists(sample_game_session.id)
        
        assert result.new_phase == "4_finalists"
        assert result.qualified_count == 4
        assert result.eliminated_count == 4
        
        # Vérifier les statuts des joueurs
        all_stats = round2_manager.db.query(PlayerRound2Stats).filter(
            PlayerRound2Stats.game_session_id == sample_game_session.id
        ).order_by(PlayerRound2Stats.score.desc()).all()
        
        # Les 4 premiers devraient être FINALIST
        for i in range(4):
            assert all_stats[i].qualification_status == QualificationStatus.FINALIST
            
        # Les 4 suivants devraient être ELIMINATED
        for i in range(4, 8):
            assert all_stats[i].qualification_status == QualificationStatus.ELIMINATED
            
    def test_get_tournament_progress(self, round2_manager, sample_game_session):
        """Test récupération de la progression du tournoi."""
        from app.models import Player, PlayerRound2Stats
        
        # Créer différents joueurs avec différents statuts
        statuses = [
            (QualificationStatus.PLAYING, 3),
            (QualificationStatus.QUALIFIED, 5),
            (QualificationStatus.FINALIST, 2),
            (QualificationStatus.ELIMINATED, 6),
        ]
        
        player_count = 0
        for status, count in statuses:
            for i in range(count):
                player = Player(name=f"Player{player_count}_{status.value}", team_id=None)
                round2_manager.db.add(player)
                round2_manager.db.flush()
                
                stats = PlayerRound2Stats(
                    player_id=player.id,
                    game_session_id=sample_game_session.id,
                    score=player_count * 10,
                    questions_answered=10,
                    correct_answers=5,
                    current_question_index=10,
                    qualification_status=status
                )
                round2_manager.db.add(stats)
                player_count += 1
        
        round2_manager.db.commit()
        
        progress = round2_manager.get_tournament_progress(sample_game_session.id)
        
        # Avec 2 FINALIST, la phase doit être "4_finalists" (FINALIST > QUALIFIED)
        assert progress.phase == "4_finalists"
        assert progress.players_total == 16
        assert progress.players_remaining == 10  # PLAYING(3) + QUALIFIED(5) + FINALIST(2)
        assert progress.players_eliminated == 6
        assert len(progress.top_players) == 10
        
    def test_fallback_question_creation(self, round2_manager, sample_theme):
        """Test création de question de secours."""
        question = round2_manager._create_fallback_question(sample_theme.id, 3)
        
        assert question is not None
        assert question.theme_id == sample_theme.id
        assert question.question_number == 3
        assert "Test Theme" in question.text
        assert question.difficulty.value in ["easy", "medium", "hard"]
        
    def test_get_game_players(self, round2_manager, sample_game_session, sample_team, sample_player):
        """Test récupération des joueurs d'une session de jeu."""
        players = round2_manager.get_game_players(sample_game_session.id)
        
        assert len(players) == 1
        assert players[0].id == sample_player.id
        assert players[0].name == "Test Player"
        
    def test_player_id_verification_bug_prevention(self, round2_manager, db_session, sample_game_session):
        """Test spécifique pour prévenir le bug de vérification d'ID de joueur."""
        from app.models import Player, PlayerRound2Stats
        
        # Créer un joueur avec des stats
        player = Player(name="BugTestPlayer", team_id=None)
        db_session.add(player)
        db_session.flush()
        
        # Créer des stats avec le bon ID
        stats = PlayerRound2Stats(
            player_id=player.id,
            game_session_id=sample_game_session.id,
            score=0,
            qualification_status=QualificationStatus.PLAYING
        )
        db_session.add(stats)
        db_session.commit()
        
        # Récupérer les stats via le manager
        retrieved_stats = round2_manager.get_player_stats(player.id, sample_game_session.id)
        
        # CRITICAL: Vérifier que l'ID du joueur est correct (ce bug a été historiquement présent)
        assert retrieved_stats.player_id == player.id, f"BUG DÉTECTÉ: ID de joueur incorrect. Attendu {player.id}, obtenu {retrieved_stats.player_id}"
        
        # Test supplémentaire: tenter de créer des stats pour un autre joueur
        player2 = Player(name="BugTestPlayer2", team_id=None)
        db_session.add(player2)
        db_session.flush()
        
        stats2 = round2_manager.get_player_stats(player2.id, sample_game_session.id)
        assert stats2.player_id == player2.id, f"BUG DÉTECTÉ: ID de joueur incorrect pour le deuxième joueur"