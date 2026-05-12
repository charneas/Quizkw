import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from main import app
from app.models import GameSession, Team, PlayerRound2Stats, Theme, ThemeCategory
from app.memory_grid import MemoryGrid, MemoryGridRound
from app.schemas import ColorSelectionRequest, ThemeSelectionRequestRound3
from datetime import datetime

class TestMemoryGridRound3API:
    """Tests API pour la Round 3 Memory Grid"""
    
    @pytest.fixture(autouse=True)
    def setup_test_data(self, test_client, db_session: Session):
        """Setup des données de test pour Round 3"""
        # Créer un jeu avec 4 joueurs pour Round 3 (Round 3 nécessite exactement 4 joueurs)
        game_session = GameSession(
            code="TESTROUND3",
            total_players=4,
            players_per_team=1,  # Round 3 est individuel, pas en équipe
            created_at=datetime.utcnow()
        )
        db_session.add(game_session)
        db_session.flush()

        # Créer 12 thèmes pour Round 3 (3 par équipe × 4 équipes)
        themes = []
        for i in range(12):
            theme = Theme(
                name=f"Theme Round3 {i+1}",
                category=ThemeCategory.SERIOUS,
                difficulty_level=5,
                description=f"Test theme for Round 3 - {i+1}"
            )
            db_session.add(theme)
            themes.append(theme)
        
        db_session.flush()
        
        # Créer 40 questions HARD (plus que les 35 nécessaires pour une grille 7x5)
        from app.models import Question, Difficulty
        import json as json_module
        
        questions = []
        for i in range(40):
            question = Question(
                text=f"Question HARD Round3 {i+1}",
                category="General",
                difficulty=Difficulty.HARD,
                points=6,
                correct_answer=f"Correct answer {i+1}",
                wrong_answers=json_module.dumps([f"Wrong {i+1}a", f"Wrong {i+1}b", f"Wrong {i+1}c"]),
                theme_id=themes[i % len(themes)].id,  # Répartir les questions parmi les thèmes
                question_number=i+1
            )
            db_session.add(question)
            questions.append(question)
        
        db_session.flush()
        
        # Créer 4 équipes avec selected_theme_ids (3 thèmes uniques par équipe)
        teams = []
        theme_index = 0
        for i in range(4):
            # Sélectionner 3 thèmes uniques pour cette équipe
            team_theme_ids = [themes[theme_index + j].id for j in range(3)]
            theme_index += 3
            
            team = Team(
                game_session_id=game_session.id,
                name=f"Team {i+1}",
                color=None,
                selected_theme_ids=json.dumps(team_theme_ids)  # JSON array of theme IDs
            )
            db_session.add(team)
            teams.append(team)
        
        db_session.flush()
        
        # Créer PlayerRound2Stats pour le classement
        # Note: PlayerRound2Stats n'a pas de champ team_id, seulement player_id
        # Pour les tests, on va créer des joueurs fictifs
        for i, team in enumerate(teams):
            for j in range(4):  # 4 joueurs par équipe
                # Dans la réalité, il faudrait créer un Player d'abord
                # Pour les tests, on simule avec player_id = j+1
                player_stat = PlayerRound2Stats(
                    game_session_id=game_session.id,
                    player_id=j + 1,  # ID fictif pour le test
                    score=(i+1) * 100 + j * 25,  # Scores différents pour classement,
                )
                db_session.add(player_stat)

        db_session.commit()

        self.client = test_client
        self.game = game_session
        self.teams = teams
        self.themes = themes
        self.db_session = db_session
        
        yield
        
        # Cleanup
        db_session.query(PlayerRound2Stats).filter(PlayerRound2Stats.game_session_id == game_session.id).delete()
        db_session.query(Team).filter(Team.game_session_id == game_session.id).delete()
        db_session.query(Theme).filter(Theme.id.in_([t.id for t in themes])).delete()
        db_session.query(GameSession).filter(GameSession.id == game_session.id).delete()
        db_session.commit()

    def test_create_memory_grid_with_themes_success(self):
        """[P0] POST /games/{code}/memory-grid/create-with-themes - Création réussie"""
        # L'endpoint attend rows et cols comme paramètres de query
        # Mais nécessite que le jeu soit en round 3 (MANCHE_3)
        # Mettre à jour le jeu pour être en round 3
        self.game.current_round = "MANCHE_3"
        self.db_session.commit()
        
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data  # memory_grid_id dans le schéma
        assert "grid_size" in data  # Le schéma retourne grid_size au lieu de rows/cols
        assert data["grid_size"] == 5  # 7x5 grid, grid_size = 5 (colonnes)
        assert "game_session_id" in data
        assert data["game_session_id"] == self.game.id
        
        # Vérifier que la grille existe en base
        memory_grid = self.db_session.query(MemoryGrid).filter(
            MemoryGrid.game_session_id == self.game.id
        ).first()
        assert memory_grid is not None
        assert memory_grid.rows == 7
        assert memory_grid.cols == 5

    def test_create_memory_grid_with_themes_insufficient_teams(self):
        """[P1] POST /games/{code}/memory-grid/create-with-themes - Équipes insuffisantes"""
        # Supprimer des équipes pour avoir moins de 4
        self.db_session.query(Team).filter(Team.id.in_([t.id for t in self.teams[2:]])).delete()
        self.db_session.commit()
        
        # Mettre à jour le jeu pour être en round 3
        self.game.current_round = "MANCHE_3"
        self.db_session.commit()
        
        # L'endpoint attend rows et cols comme paramètres de query, pas de body JSON
        response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes?rows=7&cols=5"
        )
        
        # L'endpoint devrait échouer car il y a moins de 4 équipes
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        # Le message d'erreur exact dépend de l'implémentation
        # Vérifier qu'il y a une erreur liée au nombre d'équipes
        error_detail = data["detail"].lower()
        assert any(keyword in error_detail for keyword in ["team", "équipe", "4", "quatre"])

    def test_get_team_ranking_success(self):
        """[P1] GET /games/{code}/memory-grid/team-ranking - Récupération classement"""
        response = self.client.get(f"/games/{self.game.code}/memory-grid/team-ranking")
        
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
        create_response = self.client.post(
            f"/games/{self.game.code}/memory-grid/create-with-themes",
            json={"themes": ["Histoire", "Géographie", "Science", "Sport"], "difficulty": "HARD"}
        )
        memory_grid_id = create_response.json()["memory_grid_id"]
        
        response = self.client.get(f"/memory-grid/{memory_grid_id}/current-team-turn")
        
        assert response.status_code == 200
        data = response.json()
        assert "current_team_id" in data
        assert "current_team_name" in data
        assert "turn_number" in data
        assert data["turn_number"] == 1

    def test_get_available_colors_success(self):
        """[P2] GET /games/{code}/available-colors - Couleurs disponibles"""
        response = self.client.get(f"/games/{self.game.code}/available-colors")
        
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
        
        response = self.client.post(
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
        self.client.post(f"/teams/{team1.id}/select-color", json={"color": "#FF5733"})
        
        # Team 2 essaie de prendre la même couleur
        team2 = self.teams[1]
        response = self.client.post(
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
        
        response = self.client.post(
            f"/teams/{team.id}/select-color",
            json=request_data
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_create_memory_grid_missing_game(self):
        """[P2] POST /games/{code}/memory-grid/create-with-themes - Jeu inexistant"""
        response = self.client.post(
            "/games/INVALIDCODE/memory-grid/create-with-themes",
            json={"themes": ["Histoire"], "difficulty": "HARD"}
        )
        
        assert response.status_code == 404
    
    def test_get_team_ranking_missing_game(self):
        """[P2] GET /games/{code}/memory-grid/team-ranking - Jeu inexistant"""
        response = self.client.get("/games/INVALIDCODE/memory-grid/team-ranking")
        
        assert response.status_code == 404
    
    def test_get_current_team_turn_missing_grid(self):
        """[P2] GET /memory-grid/{memory_grid_id}/current-team-turn - Grille inexistante"""
        response = self.client.get("/memory-grid/999/current-team-turn")
        
        assert response.status_code == 404
    
    def test_performance_create_memory_grid(self):
        """[P1] Performance: Création grille 7x5 < 2 secondes"""
        import time
        
        request_data = {
            "themes": ["Histoire", "Géographie", "Science", "Sport", "Art", "Musique", "Cinéma"],
            "difficulty": "HARD"
        }
        
        start_time = time.time()
        response = self.client.post(
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