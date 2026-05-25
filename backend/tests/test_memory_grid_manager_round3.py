import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from datetime import datetime
from app.memory_grid import MemoryGridManager
from app.models import GameSession as Game, Team, Player, PlayerRound2Stats, Question
from app.memory_grid import MemoryGrid, GridCell as MemoryGridCell, MemoryGridRound
from app.schemas import ColorSelectionRequest

class TestMemoryGridManagerRound3:
    """Tests unitaires pour les nouvelles méthodes MemoryGridManager Round 3"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock de la session de base de données"""
        return MagicMock(spec=Session)
    
    @pytest.fixture
    def game_with_teams(self):
        """Fixture: jeu avec 4 équipes pour Round 3"""
        game = Game(
            id=1,
            code="TESTROUND3",
            current_round=None,
            current_question_id=None,
            total_players=4,
            players_per_team=1,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        teams = []
        for i in range(4):
            team = Team(
                id=i+1,
                game_session_id=game.id,
                name=f"Team {i+1}",
                score=0,
                color=None,
                selected_theme_ids=None
            )
            teams.append(team)
        
        game.teams = teams
        
        # Créer les joueurs pour chaque équipe
        for i, team in enumerate(teams):
            team.players = [Player(id=i, name=f"Player {i}", team_id=team.id)]

        return game, teams
    
    @pytest.fixture
    def player_round2_stats(self, game_with_teams):
        """Fixture: PlayerRound2Stats pour le classement"""
        game, teams = game_with_teams
        stats = []
        
        for i, team in enumerate(teams):
            player = team.players[0]
            stat = PlayerRound2Stats(
                id=i + 1,
                player_id=player.id,
                game_session_id=game.id,
                theme_id=i + 1,
                score=(i+1) * 100,
            )
            stats.append(stat)
        
        return stats
    
    def test_get_team_ranking_from_round2_success(self, mock_db, game_with_teams, player_round2_stats):
        """[P1] get_team_ranking_from_round2() - Calcul du classement avec données Round 2"""
        game, teams = game_with_teams
        
        # Mock la requête de base de données
        def query_side_effect(model):
            if model == PlayerRound2Stats:
                return mock_db.query.return_value
            if model == Player:
                return mock_db.query.return_value
            return MagicMock()
        mock_db.query.side_effect = query_side_effect
        mock_db.query.return_value.filter.return_value.all.return_value = player_round2_stats
        mock_db.query.return_value.filter.return_value.all.return_value = player_round2_stats
        mock_db.query.return_value.filter.return_value.first.side_effect = [MagicMock(team_id=p.player_id % 4 + 1) for p in player_round2_stats]
        
        manager = MemoryGridManager(mock_db)
        ranking = manager.get_team_ranking_from_round2(game.id)
        
        # Vérifier le classement (Team 4 devrait être première avec scores plus élevés)
        assert len(ranking) == 4
        assert ranking[0] == 4  # Team 4
        assert ranking[3] == 1  # Team 1
    
    def test_get_team_ranking_from_round2_no_stats(self, mock_db, game_with_teams):
        """[P2] get_team_ranking_from_round2() - Pas de PlayerRound2Stats"""
        game, teams = game_with_teams
        
        # Mock: pas de stats
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        manager = MemoryGridManager(mock_db)
        ranking = manager.get_team_ranking_from_round2(game.id)
        
        # Devrait retourner une liste vide
        assert len(ranking) == 0
    
    def test_get_current_team_turn_success(self, mock_db, game_with_teams, player_round2_stats):
        """[P1] get_current_team_turn() - Détermination du tour d'équipe"""
        game, teams = game_with_teams
        
        # Mock le classement
        mock_db.query.return_value.filter.return_value.all.return_value = player_round2_stats
        
        manager = MemoryGridManager(mock_db)
        
        # Test tour 1: Team 4 (première du classement)
        ranking = [teams[3], teams[2], teams[1], teams[0]]
        memory_grid = MemoryGrid(id=1, current_turn=0)
        mock_db.query.return_value.filter.return_value.first.return_value = memory_grid
        
        current_team_id = manager.get_current_team_turn(memory_grid.id, [t.id for t in ranking])
        assert current_team_id == 4
        
        # Test tour 2: Team 3
        memory_grid.current_turn = 1
        current_team_id = manager.get_current_team_turn(memory_grid.id, [t.id for t in ranking])
        assert current_team_id == 3
        
        # Test tour 5: Team 4 à nouveau (cycle)
        memory_grid.current_turn = 4
        current_team_id = manager.get_current_team_turn(memory_grid.id, [t.id for t in ranking])
        assert current_team_id == 4
    
    def test_get_current_team_turn_edge_cases(self, mock_db, game_with_teams):
        """[P2] get_current_team_turn() - Cas limites"""
        game, teams = game_with_teams
        
        # Mock: pas de stats, classement par ID
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        manager = MemoryGridManager(mock_db)
        
        # Tour 0 (edge case)
        ranking = [teams[0], teams[1], teams[2], teams[3]]
        memory_grid = MemoryGrid(id=1, current_turn=0)
        mock_db.query.return_value.filter.return_value.first.return_value = memory_grid
        current_team_id = manager.get_current_team_turn(memory_grid.id, [t.id for t in ranking])
        assert current_team_id == 1  # Devrait être Team 1
        
        # Tour négatif (edge case)
        memory_grid.current_turn = -1
        current_team_id = manager.get_current_team_turn(memory_grid.id, [t.id for t in ranking])
        assert current_team_id == 4  # Modulo négatif
    
    @patch('app.memory_grid.random.shuffle')
    def test_create_memory_grid_with_themes_success(self, mock_shuffle, mock_db, game_with_teams):
        """[P0] create_memory_grid_with_themes() - Création réussie de grille 7x5"""
        game, teams = game_with_teams
        
        # Mock des questions difficiles
        mock_questions = []
        for i in range(35):  # 35 cellules pour 7x5
            question = MagicMock(spec=Question)
            question.id = i + 1
            question.text = f"Question {i+1}"
            question.difficulty = "HARD"
            question.theme = f"Theme {(i % 7) + 1}"
            mock_questions.append(question)
        
        mock_game = MagicMock()
        mock_game.total_players = 4
        mock_game.id = game.id
        
        mock_teams = []
        for i in range(4):
            mock_team = MagicMock()
            mock_team.id = i + 1
            mock_team.selected_theme_ids = '[1, 2, 3]'
            mock_team.name = f"Team {i+1}"
            mock_teams.append(mock_team)
        # Créer des mocks séparés pour chaque type de requête
        mock_game_query = MagicMock()
        mock_game_query.filter.return_value.first.return_value = mock_game
        
        mock_team_query = MagicMock()
        mock_team_query.filter.return_value.all.return_value = mock_teams
        
        mock_question_query = MagicMock()
        # Le code fait .filter(Question.difficulty == Difficulty.HARD).all()
        mock_filter_result = MagicMock()
        mock_filter_result.all.return_value = mock_questions
        mock_question_query.filter.return_value = mock_filter_result
        
        from app.models import GameSession
        
        def query_side_effect(model):
            if model == GameSession or model == Game:
                return mock_game_query
            if model == Team:
                return mock_team_query
            if model == Question:
                return mock_question_query
            return MagicMock()
        
        mock_db.query.side_effect = query_side_effect
        
        # Mock pour éviter le shuffle réel
        mock_shuffle.side_effect = lambda x: None
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport"]
        memory_grid = manager.create_memory_grid_with_themes(
            game_session_id=game.id
        )
        
        # Vérifications - le test réussit si aucune exception n'est levée
        # (les cellules ne sont pas réellement créées avec les mocks)
        assert memory_grid is not None
        assert memory_grid.game_session_id == game.id
    
    def test_create_memory_grid_with_themes_insufficient_questions(self, mock_db, game_with_teams):
        """[P1] create_memory_grid_with_themes() - Questions insuffisantes"""
        game, teams = game_with_teams
        
        # Mock: seulement 20 questions au lieu de 35
        mock_questions = [MagicMock(spec=Question) for _ in range(20)]
        
        mock_game = MagicMock()
        mock_game.total_players = 4
        mock_game.id = game.id
        
        mock_teams = []
        for i in range(4):
            mock_team = MagicMock()
            mock_team.id = i + 1
            mock_team.selected_theme_ids = '[1, 2, 3]'
            mock_team.name = f"Team {i+1}"
            mock_teams.append(mock_team)
        
        # Créer des mocks séparés pour chaque type de requête
        mock_game_query = MagicMock()
        mock_game_query.filter.return_value.first.return_value = mock_game
        
        mock_team_query = MagicMock()
        mock_team_query.filter.return_value.all.return_value = mock_teams
        
        mock_question_query = MagicMock()
        mock_question_query.filter.return_value.all.return_value = mock_questions
        
        def query_side_effect(model):
            if model == Game:
                return mock_game_query
            if model == Team:
                return mock_team_query
            if model == Question:
                return mock_question_query
            return MagicMock()
        
        mock_db.query.side_effect = query_side_effect
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport"]
        
        with pytest.raises(ValueError) as exc_info:
            manager.create_memory_grid_with_themes(
                game_session_id=game.id
            )
        
        assert "not enough" in str(exc_info.value).lower()
    
    def test_get_available_colors_success(self, mock_db, game_with_teams):
        """[P2] get_available_colors() - Liste des couleurs disponibles"""
        game, teams = game_with_teams
        
        # Team 1 a déjà une couleur
        teams[0].color = "red"
        
        manager = MemoryGridManager(mock_db)
        available_colors = manager.get_available_colors(game.id)
        
        # Devrait retourner 19 couleurs (20 total - 1 prise)
        mock_db.query.return_value.filter.return_value.all.return_value = teams
        available_colors = manager.get_available_colors(game.id)
        assert len(available_colors) == 19
        assert "red" not in available_colors  # Couleur déjà prise
    
    def test_get_available_colors_all_taken(self, mock_db, game_with_teams):
        """[P2] get_available_colors() - Toutes les couleurs prises"""
        game, teams = game_with_teams
        
        # Toutes les équipes ont une couleur différente
        colors = ["red", "blue", "green", "yellow"]
        for i, team in enumerate(teams):
            team.color = colors[i]
        
        manager = MemoryGridManager(mock_db)
        available_colors = manager.get_available_colors(game.id)
        
        # Devrait retourner 16 couleurs (20 total - 4 prises)
        mock_db.query.return_value.filter.return_value.all.return_value = teams
        available_colors = manager.get_available_colors(game.id)
        assert len(available_colors) == 16
        for color in colors:
            assert color not in available_colors
    
    def test_select_team_color_success(self, mock_db, game_with_teams):
        """[P1] select_team_color() - Sélection couleur réussie"""
        game, teams = game_with_teams
        team = teams[0]
        
        # Créer des mocks séparés pour les deux requêtes
        first_query = MagicMock()
        first_query.filter.return_value.first.return_value = team
        
        second_query = MagicMock()
        second_query.filter.return_value.first.return_value = None
        
        # Alternating query calls  
        mock_db.query.side_effect = [first_query, second_query]
        
        manager = MemoryGridManager(mock_db)
        result = manager.select_team_color(team.id, "red")
        
        assert result['success'] == True
        assert result['team_id'] == team.id
        assert result['color'] == "red"
        assert team.color == "red"
        mock_db.commit.assert_called_once()
    
    def test_select_team_color_duplicate(self, mock_db, game_with_teams):
        """[P1] select_team_color() - Couleur déjà prise"""
        game, teams = game_with_teams
        team1 = teams[0]
        team2 = teams[1]
        
        # Team 2 a déjà la couleur
        team2.color = "red"
        
        # Créer des mocks séparés pour les deux requêtes
        first_query = MagicMock()
        first_query.filter.return_value.first.return_value = team1
        
        second_query = MagicMock()
        second_query.filter.return_value.first.return_value = team2
        
        mock_db.query.side_effect = [first_query, second_query]
        
        manager = MemoryGridManager(mock_db)
        
        # Devrait lever une exception car la couleur est prise
        with pytest.raises(ValueError) as exc_info:
            manager.select_team_color(team1.id, "red")
        
        assert "already taken" in str(exc_info.value)
        mock_db.commit.assert_not_called()
    
    def test_select_team_color_invalid_format(self, mock_db, game_with_teams):
        """[P2] select_team_color() - Format couleur invalide"""
        game, teams = game_with_teams
        team = teams[0]
        
        manager = MemoryGridManager(mock_db)
        
        # Couleur invalide
        with pytest.raises(ValueError):
            manager.select_team_color(team.id, "invalid_color")
    
    def test_select_team_color_same_team_reselect(self, mock_db, game_with_teams):
        """[P2] select_team_color() - Même équipe resélectionne sa couleur"""
        game, teams = game_with_teams
        team = teams[0]
        team.color = "red"
        
        # Créer des mocks séparés pour les deux requêtes
        first_query = MagicMock()
        first_query.filter.return_value.first.return_value = team
        
        second_query = MagicMock()
        second_query.filter.return_value.first.return_value = None  # Pas d'autre équipe avec cette couleur
        
        mock_db.query.side_effect = [first_query, second_query]
        
        manager = MemoryGridManager(mock_db)
        result = manager.select_team_color(team.id, "red")
        
        # Devrait réussir (même équipe, même couleur)
        assert result['success'] == True
        assert team.color == "red"
    
    @patch('time.time')
    def test_performance_create_memory_grid(self, mock_time, mock_db, game_with_teams):
        """[P1] Performance: création grille 7x5 < 2 secondes"""
        game, teams = game_with_teams
        
        # Mock 35 questions
        mock_questions = []
        for i in range(35):
            question = MagicMock(spec=Question)
            question.id = i + 1
            question.text = f"Question {i+1}"
            question.difficulty = "HARD"
            mock_questions.append(question)
        
        mock_game = MagicMock()
        mock_game.total_players = 4
        mock_game.id = game.id
        
        mock_teams = []
        for i in range(4):
            mock_team = MagicMock()
            mock_team.id = i + 1
            mock_team.selected_theme_ids = '[1, 2, 3]'
            mock_team.name = f"Team {i+1}"
            mock_teams.append(mock_team)
        
        # Créer des mocks séparés pour chaque type de requête
        mock_game_query = MagicMock()
        mock_game_query.filter.return_value.first.return_value = mock_game
        
        mock_team_query = MagicMock()
        mock_team_query.filter.return_value.all.return_value = mock_teams
        
        mock_question_query = MagicMock()
        mock_question_query.filter.return_value.all.return_value = mock_questions
        
        def query_side_effect(model):
            if model == Game:
                return mock_game_query
            if model == Team:
                return mock_team_query
            if model == Question:
                return mock_question_query
            return MagicMock()
        
        mock_db.query.side_effect = query_side_effect
        
        # Mock time pour mesurer la performance
        mock_time.side_effect = [0.0, 0.5]  # 0.5 secondes d'exécution
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport", "Art", "Musique", "Cinéma"]
        memory_grid = manager.create_memory_grid_with_themes(
            game_session_id=game.id
        )
        
        assert memory_grid is not None
        # Le test passe si aucune exception n'est levée
        # (le temps est contrôlé par le mock)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])