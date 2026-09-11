"""Mode "Manche 3 directe" (spec-manche-3-seule, story 1).

Réutilise les patterns de test_solo_mode.py (create_team/join_team déjà
génériques via players_per_team=1) et le pattern de seed direct
PlayerRound2Stats de test_memory_grid_round3_api.py pour vérifier que le
seed produit par `start_game` alimente bien le flow existant de sélection
de thèmes de Manche 3.
"""
from app import models


def _create_solo_finale_game(test_client):
    response = test_client.post("/games/", json={
        "total_players": 8,  # doit être ignoré/forcé à 4 par le backend
        "players_per_team": 3,  # doit être ignoré/forcé à 1 par le backend
        "is_solo_finale": True,
    })
    assert response.status_code == 200
    return response.json()


def _create_team(test_client, code, name):
    response = test_client.post(f"/games/{code}/teams/", json={"name": name})
    assert response.status_code == 200
    return response.json()


def _join_team(test_client, code, team_id, name):
    return test_client.post(f"/games/{code}/teams/{team_id}/players/", json={"name": name})


def _fill_four_solo_teams(test_client, code):
    teams = []
    joined_players = []
    for i in range(4):
        team = _create_team(test_client, code, f"Solo {i}")
        joined = _join_team(test_client, code, team["id"], f"Joueur {i}")
        assert joined.status_code == 200
        teams.append(team)
        joined_players.append(joined.json())
    return teams, joined_players


class TestSoloFinaleCreation:
    def test_backend_forces_four_players_one_per_team(self, test_client):
        game = _create_solo_finale_game(test_client)
        assert game["game"]["total_players"] == 4
        assert game["game"]["players_per_team"] == 1
        assert game["game"]["is_solo_finale"] is True

    def test_normal_game_defaults_is_solo_finale_false(self, test_client):
        response = test_client.post("/games/", json={
            "total_players": 6,
            "players_per_team": 2,
        })
        assert response.status_code == 200
        assert response.json()["game"]["is_solo_finale"] is False


class TestSoloFinaleJoin:
    def test_fifth_player_join_rejected(self, test_client):
        game = _create_solo_finale_game(test_client)
        code = game["game"]["code"]
        _fill_four_solo_teams(test_client, code)[0]

        fifth_team = test_client.post(f"/games/{code}/teams/", json={"name": "Solo 5"})
        assert fifth_team.status_code == 400


class TestSoloFinaleStart:
    def test_start_refused_with_three_of_four(self, test_client, db_session):
        game = _create_solo_finale_game(test_client)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        for i in range(3):
            team = _create_team(test_client, code, f"Solo {i}")
            _join_team(test_client, code, team["id"], f"Joueur {i}")

        response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert response.status_code == 400
        assert "4 joueurs" in response.json()["detail"]

        db_session.expire_all()
        refreshed = db_session.query(models.GameSession).filter(
            models.GameSession.code == code
        ).first()
        assert refreshed.current_round == models.RoundType.MANCHE_1
        assert refreshed.started is False

    def test_start_at_four_jumps_to_manche_3_and_seeds_finalists(self, test_client, db_session):
        game = _create_solo_finale_game(test_client)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        _fill_four_solo_teams(test_client, code)

        response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(models.GameSession).filter(
            models.GameSession.code == code
        ).first()
        assert refreshed.current_round == models.RoundType.MANCHE_3
        assert refreshed.started is True

        stats = db_session.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == refreshed.id
        ).all()
        assert len(stats) == 4
        assert all(s.qualification_status == models.QualificationStatus.FINALIST for s in stats)
        assert all(s.theme_id is None for s in stats)
        # Ordre total : pas d'égalité, sinon _setup_turn_order/get_finalists_from_round2
        # (tous deux triés par score) ne donneraient pas un ordre déterministe.
        scores = [s.score for s in stats]
        assert len(set(scores)) == len(scores)

        player_ids = {s.player_id for s in stats}
        assert len(player_ids) == 4

    def test_normal_game_start_behavior_unchanged(self, test_client, db_session):
        game = test_client.post("/games/", json={
            "total_players": 6,
            "players_per_team": 2,
        }).json()
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        # Une seule équipe -> refusé comme avant (règle générique >= 2)
        team = _create_team(test_client, code, "Equipe A")
        _join_team(test_client, code, team["id"], "Alice")
        _join_team(test_client, code, team["id"], "Bob")

        response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert response.status_code == 400
        assert "Au moins 2 équipes" in response.json()["detail"]

        db_session.expire_all()
        refreshed = db_session.query(models.GameSession).filter(
            models.GameSession.code == code
        ).first()
        assert refreshed.current_round == models.RoundType.MANCHE_1


class TestSoloFinaleThemeSelectionFlow:
    """Vérifie que le seed produit par start_game suffit à faire fonctionner
    le flow de sélection de thèmes existant de Manche 3 (get_finalists_from_round2
    lit les PlayerRound2Stats seedées, _setup_turn_order aussi)."""

    def test_theme_selection_works_after_solo_finale_start(self, test_client, db_session):
        game = _create_solo_finale_game(test_client)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        # Chaque finaliste choisit 3 thèmes distincts -- 12 thèmes au total
        # (comportement existant : un thème ne peut être choisi que par un
        # seul finaliste).
        themes = [
            models.Theme(name=f"Theme SF {i}", category=models.ThemeCategory.SERIOUS, difficulty_level=5)
            for i in range(12)
        ]
        db_session.add_all(themes)
        db_session.commit()

        teams, joined_players = _fill_four_solo_teams(test_client, code)

        start_response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert start_response.status_code == 200

        db_session.expire_all()
        refreshed_game = db_session.query(models.GameSession).filter(
            models.GameSession.code == code
        ).first()

        assert len(joined_players) == 4

        # L'ordre de sélection des thèmes suit l'ordre de passage seedé
        # (_setup_turn_order, non modifié par cette story) : trié par score
        # PlayerRound2Stats décroissant, pas par ordre d'arrivée au lobby.
        stats_by_player = {
            s.player_id: s.score
            for s in db_session.query(models.PlayerRound2Stats).filter(
                models.PlayerRound2Stats.game_session_id == refreshed_game.id
            ).all()
        }
        joined_players = sorted(
            joined_players, key=lambda p: stats_by_player[p["id"]], reverse=True
        )

        colors = ["red", "blue", "green", "yellow"]
        for index, (joined, color) in enumerate(zip(joined_players, colors)):
            headers = {"X-Player-Token": joined["player_token"]}
            # Le tour de setup (couleur + thèmes) n'avance que lorsque les
            # deux sont faits -- comportement existant de _require_setup_turn,
            # non modifié par cette story.
            color_response = test_client.post(
                "/memory-grid/color/select",
                json={
                    "game_session_id": refreshed_game.id,
                    "player_id": joined["id"],
                    "color": color,
                },
                headers=headers,
            )
            assert color_response.status_code == 200, color_response.json()

            own_themes = themes[index * 3:index * 3 + 3]
            theme_response = test_client.post(
                "/memory-grid/theme/select",
                json={
                    "game_session_id": refreshed_game.id,
                    "player_id": joined["id"],
                    "theme_ids": [t.id for t in own_themes],
                },
                headers=headers,
            )
            assert theme_response.status_code == 200, theme_response.json()
