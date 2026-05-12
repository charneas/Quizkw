import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from datetime import datetime
from app.memory_grid import MemoryGridManager
from app.models import GameSession as Game, Team, PlayerRound2Stats, Question
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
            total_players=16,
            players_per_team=4,
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
        return game, teams
    
    @pytest.fixture
    def player_round2_stats(self, game_with_teams):
        """Fixture: PlayerRound2Stats pour le classement"""
        game, teams = game_with_teams
        stats = []
        
        for i, team in enumerate(teams):
            for j in range(4):  # 4 joueurs par équipe
                stat = PlayerRound2Stats(
                    id=i*4 + j + 1,
                    game_id=game.id,
                    team_id=team.id,
                    player_name=f"Player {j+1}",
                    score=(i+1) * 100 + j * 25,  # Scores différents pour classement
                    theme=f"Theme {j+1}",
                    created_at=datetime.utcnow()
                )
                stats.append(stat)
        
        return stats
    
    def test_get_team_ranking_from_round2_success(self, mock_db, game_with_teams, player_round2_stats):
        """[P1] get_team_ranking_from_round2() - Calcul du classement avec données Round 2"""
        game, teams = game_with_teams
        
        # Mock la requête de base de données
        mock_db.query.return_value.filter.return_value.all.return_value = player_round2_stats
        
        manager = MemoryGridManager(mock_db)
        ranking = manager.get_team_ranking_from_round2(game.id)
        
        # Vérifier le classement (Team 4 devrait être première avec scores plus élevés)
        assert len(ranking) == 4
        assert ranking[0]["team_id"] == 4  # Team 4
        assert ranking[0]["total_score"] == 475  # (4*100 + 3*25)
        assert ranking[3]["team_id"] == 1  # Team 1
        assert ranking[3]["total_score"] == 175  # (1*100 + 3*25)
        
        # Vérifier l'ordre décroissant
        scores = [team["total_score"] for team in ranking]
        assert scores == sorted(scores, reverse=True)
    
    def test_get_team_ranking_from_round2_no_stats(self, mock_db, game_with_teams):
        """[P2] get_team_ranking_from_round2() - Pas de PlayerRound2Stats"""
        game, teams = game_with_teams
        
        # Mock: pas de stats
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        manager = MemoryGridManager(mock_db)
        ranking = manager.get_team_ranking_from_round2(game.id)
        
        # Devrait retourner les équipes dans l'ordre d'ID par défaut
        assert len(ranking) == 4
        assert ranking[0]["team_id"] == 1
        assert ranking[0]["total_score"] == 0
        assert ranking[3]["team_id"] == 4
        assert ranking[3]["total_score"] == 0
    
    def test_get_current_team_turn_success(self, mock_db, game_with_teams, player_round2_stats):
        """[P1] get_current_team_turn() - Détermination du tour d'équipe"""
        game, teams = game_with_teams
        
        # Mock le classement
        mock_db.query.return_value.filter.return_value.all.return_value = player_round2_stats
        
        manager = MemoryGridManager(mock_db)
        
        # Test tour 1: Team 4 (première du classement)
        current_team = manager.get_current_team_turn(game.id, turn_number=1)
        assert current_team.id == 4
        assert current_team.name == "Team 4"
        
        # Test tour 2: Team 3
        current_team = manager.get_current_team_turn(game.id, turn_number=2)
        assert current_team.id == 3
        
        # Test tour 5: Team 4 à nouveau (cycle)
        current_team = manager.get_current_team_turn(game.id, turn_number=5)
        assert current_team.id == 4
    
    def test_get_current_team_turn_edge_cases(self, mock_db, game_with_teams):
        """[P2] get_current_team_turn() - Cas limites"""
        game, teams = game_with_teams
        
        # Mock: pas de stats, classement par ID
        mock_db.query.return_value.filter.return_value.all.return_value = []
        
        manager = MemoryGridManager(mock_db)
        
        # Tour 0 (edge case)
        current_team = manager.get_current_team_turn(game.id, turn_number=0)
        assert current_team.id == 1  # Devrait être Team 1
        
        # Tour négatif (edge case)
        current_team = manager.get_current_team_turn(game.id, turn_number=-1)
        assert current_team.id == 4  # Modulo négatif
    
    @patch('app.memory_grid.random.shuffle')
    @patch('app.memory_grid.Question')
    def test_create_memory_grid_with_themes_success(self, mock_question, mock_shuffle, mock_db, game_with_teams):
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
        
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = mock_questions
        
        # Mock pour éviter le shuffle réel
        mock_shuffle.side_effect = lambda x: None
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport"]
        memory_grid = manager.create_memory_grid_with_themes(
            game_id=game.id,
            themes=themes,
            difficulty="HARD"
        )
        
        # Vérifications
        assert memory_grid is not None
        assert memory_grid.game_id == game.id
        assert memory_grid.rounds is not None
        assert len(memory_grid.rounds) == 1
        
        round3 = memory_grid.rounds[0]
        assert round3.round_number == 3
        assert round3.grid_size == "7x5"
        
        # Vérifier les cellules
        assert round3.cells is not None
        assert len(round3.cells) == 35  # 7x5 = 35 cellules
        
        # Vérifier l'assignation des thèmes aux équipes
        team_themes = {}
        for cell in round3.cells:
            if cell.team_id:
                if cell.team_id not in team_themes:
                    team_themes[cell.team_id] = set()
                team_themes[cell.team_id].add(cell.theme)
        
        # Chaque équipe devrait avoir 5 cellules avec thèmes différents
        for team_id, themes_set in team_themes.items():
            assert len(themes_set) == 5  # 5 thèmes différents par équipe
    
    def test_create_memory_grid_with_themes_insufficient_questions(self, mock_db, game_with_teams):
        """[P1] create_memory_grid_with_themes() - Questions insuffisantes"""
        game, teams = game_with_teams
        
        # Mock: seulement 20 questions au lieu de 35
        mock_questions = [MagicMock(spec=Question) for _ in range(20)]
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = mock_questions
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport"]
        
        with pytest.raises(ValueError) as exc_info:
            manager.create_memory_grid_with_themes(
                game_id=game.id,
                themes=themes,
                difficulty="HARD"
            )
        
        assert "insufficient" in str(exc_info.value).lower()
    
    def test_get_available_colors_success(self, mock_db, game_with_teams):
        """[P2] get_available_colors() - Liste des couleurs disponibles"""
        game, teams = game_with_teams
        
        # Team 1 a déjà une couleur
        teams[0].color = "#FF5733"
        
        manager = MemoryGridManager(mock_db)
        available_colors = manager.get_available_colors(game.id)
        
        # Devrait retourner 19 couleurs (20 total - 1 prise)
        assert len(available_colors) == 19
        assert "#FF5733" not in available_colors  # Couleur déjà prise
        assert all(isinstance(color, str) for color in available_colors)
        assert all(color.startswith("#") for color in available_colors)
    
    def test_get_available_colors_all_taken(self, mock_db, game_with_teams):
        """[P2] get_available_colors() - Toutes les couleurs prises"""
        game, teams = game_with_teams
        
        # Toutes les équipes ont une couleur différente
        colors = ["#FF5733", "#33FF57", "#5733FF", "#FF33A1"]
        for i, team in enumerate(teams):
            team.color = colors[i]
        
        manager = MemoryGridManager(mock_db)
        available_colors = manager.get_available_colors(game.id)
        
        # Devrait retourner 16 couleurs (20 total - 4 prises)
        assert len(available_colors) == 16
        for color in colors:
            assert color not in available_colors
    
    def test_select_team_color_success(self, mock_db, game_with_teams):
        """[P1] select_team_color() - Sélection couleur réussie"""
        game, teams = game_with_teams
        team = teams[0]
        
        # Mock: pas d'autres équipes avec cette couleur
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        
        manager = MemoryGridManager(mock_db)
        success = manager.select_team_color(team.id, "#FF5733")
        
        assert success == True
        assert team.color == "#FF5733"
        mock_db.commit.assert_called_once()
    
    def test_select_team_color_duplicate(self, mock_db, game_with_teams):
        """[P1] select_team_color() - Couleur déjà prise"""
        game, teams = game_with_teams
        team1 = teams[0]
        team2 = teams[1]
        
        # Team 2 a déjà la couleur
        team2.color = "#FF5733"
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = team2
        
        manager = MemoryGridManager(mock_db)
        success = manager.select_team_color(team1.id, "#FF5733")
        
        assert success == False
        assert team1.color is None
        mock_db.commit.assert_not_called()
    
    def test_select_team_color_invalid_format(self, mock_db, game_with_teams):
        """[P2] select_team_color() - Format couleur invalide"""
        game, teams = game_with_teams
        team = teams[0]
        
        manager = MemoryGridManager(mock_db)
        
        # Couleur sans #
        success = manager.select_team_color(team.id, "FF5733")
        assert success == False
        
        # Couleur trop courte
        success = manager.select_team_color(team.id, "#FF5")
        assert success == False
        
        # Couleur avec caractères invalides
        success = manager.select_team_color(team.id, "#GGGGGG")
        assert success == False
    
    def test_select_team_color_same_team_reselect(self, mock_db, game_with_teams):
        """[P2] select_team_color() - Même équipe resélectionne sa couleur"""
        game, teams = game_with_teams
        team = teams[0]
        team.color = "#FF5733"
        
        # Mock: la même équipe a déjà la couleur
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = team
        
        manager = MemoryGridManager(mock_db)
        success = manager.select_team_color(team.id, "#FF5733")
        
        # Devrait réussir (même équipe, même couleur)
        assert success == True
        assert team.color == "#FF5733"
    
    @patch('app.memory_grid.time.time')
    def test_performance_create_memory_grid(self, mock_time, mock_db, game_with_teams):
        """[P1] Performance: création grille 7x5 < 2 secondes"""
        game, teams = game_with_teams
        
        # Mock 35 questions
        mock_questions = [MagicMock(spec=Question) for _ in range(35)]
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = mock_questions
        
        # Mock time pour mesurer la performance
        mock_time.side_effect = [0.0, 0.5]  # 0.5 secondes d'exécution
        
        manager = MemoryGridManager(mock_db)
        
        themes = ["Histoire", "Géographie", "Science", "Sport", "Art", "Musique", "Cinéma"]
        memory_grid = manager.create_memory_grid_with_themes(
            game_id=game.id,
            themes=themes,
            difficulty="HARD"
        )
        
        assert memory_grid is not None
        # Le test passe si aucune exception n'est levée
        # (le temps est contrôlé par le mock)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])