import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from main import app
from app.models import Game, Team, MemoryGrid, MemoryGridRound, PlayerRound2Stats
from app.schemas import ColorSelectionRequest, ThemeSelectionRequestRound3
from datetime import datetime

client = TestClient(app)

class TestMemoryGridRound3API:
    """Tests API pour la Round 3 Memory Grid"""
    
    @pytest.fixture(autouse=True)
    def setup_test_data(self, db_session: Session):
        """Setup des données de test pour Round 3"""
        # Créer un jeu avec 4 équipes pour Round 3
        game = Game(
            code="TESTROUND3",
            name="Test Round 3 Game",
            status="active",
            created_at=datetime.utcnow()
        )
        db_session.add(game)
        db_session.flush()
        
        # Créer 4 équipes
        teams = []
        for i in range(4):
            team = Team(
                game_id=game.id,
                name=f"Team {i+1}",
                color=None,
                created_at=datetime.utcnow()
            )
            db_session.add(team)
            teams.append(team)
        
        db_session.flush()
        
        # Créer PlayerRound2Stats pour le classement
        for i, team in enumerate(teams):
            for j in range(4):  # 4 joueurs par équipe
                player_stat = PlayerRound2Stats(
                    game_id=game.id,
                    team_id=team.id,
                    player_name=f"Player {j+1}",
                    score=(i+1) * 100 + j * 25,  # Scores différents pour classement
                    theme=f"Theme {j+1}",
                    created_at=datetime.utcnow()
                )
                db_session.add(player_stat)
        
        db_session.commit()
        
        self.game = game
        self.teams = teams
        self.db_session = db_session
        
        yield
        
        # Cleanup
        db_session.query(PlayerRound2Stats).filter(PlayerRound2Stats.game_id == game.id).delete()
        db_session.query(Team).filter(Team.game_id == game.id).delete()
        db_session.query(Game).filter(Game.id == game.id).delete()
        db_session.commit()
    
    def test_create_memory_grid_with_themes_success(self):
        """[P0] POST /games/{code}/memory-grid/create-with-themes - Création réussie"""
        request_data = {
            "themes": ["Histoire", "Géographie", "Science", "Sport"],
            "difficulty": "HARD"
        }
        
        response = client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes",
            json=request_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "memory_grid_id" in data
        assert "grid_size" in data
        assert data["grid_size"] == "7x5"
        assert "round_number" in data
        assert data["round_number"] == 3
        
        # Vérifier que la grille existe en base
        memory_grid = self.db_session.query(MemoryGrid).filter(
            MemoryGrid.game_id == self.game.id
        ).first()
        assert memory_grid is not None
        assert memory_grid.rounds[0].round_number == 3
    
    def test_create_memory_grid_with_themes_insufficient_teams(self):
        """[P1] POST /games/{code}/memory-grid/create-with-themes - Équipes insuffisantes"""
        # Supprimer des équipes pour avoir moins de 4
        self.db_session.query(Team).filter(Team.id.in_([t.id for t in self.teams[2:]])).delete()
        self.db_session.commit()
        
        request_data = {
            "themes": ["Histoire", "Géographie"],
            "difficulty": "HARD"
        }
        
        response = client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes",
            json=request_data
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "4 teams" in data["detail"]
    
    def test_get_team_ranking_success(self):
        """[P1] GET /games/{code}/memory-grid/team-ranking - Récupération classement"""
        response = client.get(f"/games/{self.game.code}/memory-grid/team-ranking")
        
        assert response.status_code == 200
        data = response.json()
        assert "ranking" in data
        assert len(data["ranking"]) == 4
        
        # Vérifier l'ordre du classement (Team 4 devrait être première avec scores plus élevés)
        assert data["ranking"][0]["team_name"] == "Team 4"
        assert data["ranking"][3]["team_name"] == "Team 1"
    
    def test_get_current_team_turn_success(self):
        """[P1] GET /memory-grid/{memory_grid_id}/current-team-turn - Tour actuel"""
        # D'abord créer une grille
        create_response = client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes",
            json={"themes": ["Histoire", "Géographie", "Science", "Sport"], "difficulty": "HARD"}
        )
        memory_grid_id = create_response.json()["memory_grid_id"]
        
        response = client.get(f"/memory-grid/{memory_grid_id}/current-team-turn")
        
        assert response.status_code == 200
        data = response.json()
        assert "current_team_id" in data
        assert "current_team_name" in data
        assert "turn_number" in data
        assert data["turn_number"] == 1
    
    def test_get_available_colors_success(self):
        """[P2] GET /games/{code}/available-colors - Couleurs disponibles"""
        response = client.get(f"/games/{self.game.code}/available-colors")
        
        assert response.status_code == 200
        data = response.json()
        assert "available_colors" in data
        assert len(data["available_colors"]) == 20  # 20 couleurs disponibles
        assert all(isinstance(color, str) for color in data["available_colors"])
    
    def test_select_team_color_success(self):
        """[P1] POST /teams/{team_id}/select-color - Sélection couleur réussie"""
        team = self.teams[0]
        request_data = {
            "color": "#FF5733"
        }
        
        response = client.post(
            f"/teams/{team.id}/select-color",
            json=request_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert data["success"] == True
        assert "team_id" in data
        assert data["team_id"] == team.id
        assert "selected_color" in data
        assert data["selected_color"] == "#FF5733"
        
        # Vérifier en base
        updated_team = self.db_session.query(Team).filter(Team.id == team.id).first()
        assert updated_team.color == "#FF5733"
    
    def test_select_team_color_duplicate(self):
        """[P1] POST /teams/{team_id}/select-color - Couleur déjà prise"""
        # Team 1 prend une couleur
        team1 = self.teams[0]
        client.post(f"/teams/{team1.id}/select-color", json={"color": "#FF5733"})
        
        # Team 2 essaie de prendre la même couleur
        team2 = self.teams[1]
        response = client.post(
            f"/teams/{team2.id}/select-color",
            json={"color": "#FF5733"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "already taken" in data["detail"].lower()
    
    def test_select_team_color_invalid_color(self):
        """[P2] POST /teams/{team_id}/select-color - Couleur invalide"""
        team = self.teams[0]
        request_data = {
            "color": "NOTACOLOR"
        }
        
        response = client.post(
            f"/teams/{team.id}/select-color",
            json=request_data
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_create_memory_grid_missing_game(self):
        """[P2] POST /games/{code}/memory-grid/create-with-themes - Jeu inexistant"""
        response = client.post(
            "/games/INVALIDCODE/memory-grid/create-with-themes",
            json={"themes": ["Histoire"], "difficulty": "HARD"}
        )
        
        assert response.status_code == 404
    
    def test_get_team_ranking_missing_game(self):
        """[P2] GET /games/{code}/memory-grid/team-ranking - Jeu inexistant"""
        response = client.get("/games/INVALIDCODE/memory-grid/team-ranking")
        
        assert response.status_code == 404
    
    def test_get_current_team_turn_missing_grid(self):
        """[P2] GET /memory-grid/{memory_grid_id}/current-team-turn - Grille inexistante"""
        response = client.get("/memory-grid/999/current-team-turn")
        
        assert response.status_code == 404
    
    def test_performance_create_memory_grid(self):
        """[P1] Performance: Création grille 7x5 < 2 secondes"""
        import time
        
        request_data = {
            "themes": ["Histoire", "Géographie", "Science", "Sport", "Art", "Musique", "Cinéma"],
            "difficulty": "HARD"
        }
        
        start_time = time.time()
        response = client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes",
            json=request_data
        )
        end_time = time.time()
        
        assert response.status_code == 200
        execution_time = end_time - start_time
        assert execution_time < 2.0, f"Création grille trop lente: {execution_time:.2f}s"
        
        print(f"Performance test: création grille 7x5 en {execution_time:.2f} secondes")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])