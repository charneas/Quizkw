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
        
        # Tolérance partagée avec advance_to_finalists (8 ou 9) : ne tronque
        # qu'au-delà de 9, jamais à 8 pile (cf. finding revue de code).
        assert len(leaderboard.qualified_players) == 9
        assert len(leaderboard.eliminated_players) == 1
        assert leaderboard.cutoff_score == 30  # Score du 9ème joueur
        
        # Vérifier que les statuts ont été mis à jour
        for player, stats in created_players[:9]:
            fresh_stats = round2_manager.db.query(PlayerRound2Stats).filter(
                PlayerRound2Stats.player_id == player.id
            ).first()
            assert fresh_stats.qualification_status == QualificationStatus.QUALIFIED

        for player, stats in created_players[9:]:
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

    def test_advance_to_finalists_accepts_nine_qualified(self, round2_manager, sample_game_session):
        """AC #4 : 9 qualifiés (équipe de 3 en surnombre) doit rester accepté."""
        from app.models import Player, PlayerRound2Stats

        for i in range(9):
            player = Player(name=f"QualifiedPlayer{i}", team_id=None)
            round2_manager.db.add(player)
            round2_manager.db.flush()

            stats = PlayerRound2Stats(
                player_id=player.id,
                game_session_id=sample_game_session.id,
                score=100 - i * 10,
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
        assert result.eliminated_count == 5

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

class TestRound1ToRound2Qualification:
    """AD-0 / AD-7 : passage de la Manche 1 collective à la Manche 2 individuelle."""

    def _make_team(self, db_session, game, name, score, player_count):
        from app import models
        team = models.Team(name=name, game_session_id=game.id, score=score)
        db_session.add(team)
        db_session.flush()
        for i in range(player_count):
            db_session.add(models.Player(name=f"{name}-J{i}", team_id=team.id))
        db_session.commit()
        return team

    def test_best_teams_qualify_whole_teams_without_truncation(self, round2_manager, db_session,
                                                           sample_game_session):
        from app import models
        # 4 équipes de 3, scores décroissants : les 3 meilleures fournissent 9
        # joueurs entiers, qualifiés sans être tronqués (AC #4 : pas de [:8]).
        self._make_team(db_session, sample_game_session, "Alpha", 90, 3)
        self._make_team(db_session, sample_game_session, "Bravo", 70, 3)
        self._make_team(db_session, sample_game_session, "Charlie", 50, 3)
        weakest = self._make_team(db_session, sample_game_session, "Delta", 10, 3)

        result = round2_manager.qualify_players_from_round1(sample_game_session.id)
        db_session.commit()

        assert result["qualified_count"] == 9
        assert result["current_round"] == "manche_2"

        weakest_player_ids = {p.id for p in weakest.players}
        assert not (set(result["qualified_player_ids"]) & weakest_player_ids), \
            "l'équipe la moins bien classée ne doit pas être qualifiée"

        # AD-1 : chaque qualifié démarre à zéro
        stats = db_session.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == sample_game_session.id
        ).all()
        assert len(stats) == 9
        assert all(s.score == 0 for s in stats)

    def test_mixed_team_sizes_are_not_split(self, round2_manager, db_session, sample_game_session):
        """AC #4 : équipes de 2 et 3 mélangées, aucune équipe n'est coupée en plein milieu."""
        from app import models
        team_a = self._make_team(db_session, sample_game_session, "Alpha", 90, 3)
        team_b = self._make_team(db_session, sample_game_session, "Bravo", 70, 2)
        team_c = self._make_team(db_session, sample_game_session, "Charlie", 50, 3)
        weakest = self._make_team(db_session, sample_game_session, "Delta", 10, 2)

        result = round2_manager.qualify_players_from_round1(sample_game_session.id)
        db_session.commit()

        # Alpha(3) + Bravo(2) + Charlie(3) = 8 : somme exacte des équipes entières retenues
        assert result["qualified_count"] == 8

        for team in (team_a, team_b, team_c):
            team_player_ids = {p.id for p in team.players}
            assert team_player_ids.issubset(set(result["qualified_player_ids"])), \
                f"l'équipe {team.name} ne doit pas être coupée"

        weakest_player_ids = {p.id for p in weakest.players}
        assert not (set(result["qualified_player_ids"]) & weakest_player_ids)

    def test_transition_sets_manche_2(self, round2_manager, db_session, sample_game_session):
        """AD-7 : la phase la plus manquante du tournoi est enfin écrite."""
        from app import models
        self._make_team(db_session, sample_game_session, "Alpha", 50, 2)

        assert sample_game_session.current_round == models.RoundType.MANCHE_1

        round2_manager.qualify_players_from_round1(sample_game_session.id)
        db_session.commit()
        db_session.refresh(sample_game_session)

        assert sample_game_session.current_round == models.RoundType.MANCHE_2

    def test_qualifying_twice_is_rejected(self, round2_manager, db_session, sample_game_session):
        """AD-7 : le compare-and-set empêche une double qualification."""
        self._make_team(db_session, sample_game_session, "Alpha", 50, 2)

        round2_manager.qualify_players_from_round1(sample_game_session.id)
        db_session.commit()

        with pytest.raises(ValueError):
            round2_manager.qualify_players_from_round1(sample_game_session.id)

    def test_no_teams_raises(self, round2_manager, sample_game_session):
        with pytest.raises(ValueError) as exc_info:
            round2_manager.qualify_players_from_round1(sample_game_session.id)
        assert "Aucune équipe" in str(exc_info.value)

    def test_full_pipeline_nine_qualified_reach_finalists_via_advance_endpoint(
        self, test_client, db_session, sample_game_session, sample_theme, sample_questions_for_theme
    ):
        """Pipeline réaliste complet (AC #3, #4) : 9 qualifiés (3 équipes de 3) qui
        terminent chacun leurs 10 questions de Manche 2 via submit_answer (le vrai
        chemin qui bascule leur statut à QUALIFIED) — sans passer par un test unitaire
        qui insère les stats QUALIFIED directement. On vérifie que le simple appel
        HTTP à /round2/{code}/advance gère les 9 qualifiés et produit 4 finalistes,
        sans jamais requérir exactement 8."""
        from app import models

        self._make_team(db_session, sample_game_session, "Alpha", 90, 3)
        self._make_team(db_session, sample_game_session, "Bravo", 70, 3)
        self._make_team(db_session, sample_game_session, "Charlie", 50, 3)

        qualify_response = test_client.post(f"/round2/{sample_game_session.code}/advance")
        assert qualify_response.status_code == 200
        assert qualify_response.json()["qualified_count"] == 9

        stats_list = db_session.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == sample_game_session.id
        ).all()
        assert len(stats_list) == 9

        # Chaque joueur choisit le thème de test puis répond à ses 10 questions
        # (le vrai chemin qui fait passer son statut PLAYING -> QUALIFIED, ligne
        # submit_answer:172-174).
        for stats in stats_list:
            round2_manager = self._round2_manager(db_session)
            round2_manager.select_theme(stats.player_id, sample_game_session.id, sample_theme.id)
            for question in sample_questions_for_theme:
                round2_manager.submit_answer(
                    stats.player_id, sample_game_session.id, question.id, question.correct_answer
                )

        db_session.commit()

        # get_tournament_progress calcule directement la phase "8_qualified" ici,
        # sans jamais passer par calculate_intermediate_leaderboard (qui coupe à 8) —
        # advance_to_finalists doit donc accepter les 9 qualifiés reçus tels quels.
        finalists_response = test_client.post(f"/round2/{sample_game_session.code}/advance")
        assert finalists_response.status_code == 200
        body = finalists_response.json()
        assert body["new_phase"] == "4_finalists"
        assert body["qualified_count"] == 4
        assert body["eliminated_count"] == 5

    def _round2_manager(self, db_session):
        from app.round2_manager import Round2Manager
        return Round2Manager(db_session)

    def test_advance_endpoint_qualifies_from_manche_1_without_manual_api_call(
        self, test_client, db_session, sample_game_session
    ):
        """H-007 : le vrai clic UI n'appelle que /round2/{code}/advance — cette
        seule requête doit qualifier les joueurs et faire passer la partie en
        Manche 2, sans appel manuel à /games/{code}/qualify-round2."""
        from app import models

        self._make_team(db_session, sample_game_session, "Alpha", 50, 2)

        response = test_client.post(f"/round2/{sample_game_session.code}/advance")

        assert response.status_code == 200
        body = response.json()
        assert body["new_phase"] == "16_players"
        assert body["qualified_count"] == 2

        db_session.refresh(sample_game_session)
        assert sample_game_session.current_round == models.RoundType.MANCHE_2

        stats = db_session.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == sample_game_session.id
        ).all()
        assert len(stats) == 2
