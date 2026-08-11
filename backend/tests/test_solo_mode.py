"""
Mode solo dès la Manche 1 (story N.001).

Le backend supportait déjà `players_per_team=1` avant cette story
(schemas.py `Field(..., ge=1, le=3)`, toute la chaîne de validation déjà
générique) — ces tests couvrent explicitement ce chemin, jamais exercé par
un vrai flux de Manche 1 jusqu'ici (seed.py l'utilisait seulement pour une
fixture Round 2 sans rapport). Voir SPEC-mode-solo-manche-1 et
n-001-mode-solo-manche-1.md pour le contexte complet.
"""
from unittest.mock import patch

from app import models


def _create_solo_game(test_client, total_players=6):
    response = test_client.post("/games/", json={
        "total_players": total_players,
        "players_per_team": 1,
    })
    assert response.status_code == 200
    return response.json()


def _create_team(test_client, code, name):
    response = test_client.post(f"/games/{code}/teams/", json={"name": name})
    assert response.status_code == 200
    return response.json()


def _join_team(test_client, code, team_id, name):
    return test_client.post(f"/games/{code}/teams/{team_id}/players/", json={"name": name})


class TestSoloTeamCreationAndTokens:
    def test_solo_team_receives_the_same_three_tokens_as_a_multi_player_team(self, test_client, db_session):
        game = _create_solo_game(test_client)
        team = _create_team(test_client, game["game"]["code"], "Solo A")

        tokens = db_session.query(models.Token).filter(models.Token.team_id == team["id"]).all()
        token_types = {t.token_type for t in tokens}
        assert token_types == {models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS}

    def test_max_teams_derives_from_total_players_over_one(self, test_client):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        for i in range(4):
            _create_team(test_client, code, f"Solo {i}")

        # Une 5e équipe dépasse total_players // players_per_team == 4
        response = test_client.post(f"/games/{code}/teams/", json={"name": "Solo 5"})
        assert response.status_code == 400


class TestSoloTeamJoinIsCappedAtOnePlayer:
    def test_second_player_rejected_on_a_solo_team(self, test_client):
        game = _create_solo_game(test_client)
        code = game["game"]["code"]
        team = _create_team(test_client, code, "Solo A")

        first = _join_team(test_client, code, team["id"], "Alice")
        assert first.status_code == 200

        second = _join_team(test_client, code, team["id"], "Bob")
        assert second.status_code == 400
        assert second.json()["detail"] == "Cette équipe est déjà complète"


class TestSoloGameStart:
    def test_game_starts_once_every_solo_team_has_its_one_player(self, test_client):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        team_a = _create_team(test_client, code, "Solo A")
        team_b = _create_team(test_client, code, "Solo B")
        _join_team(test_client, code, team_a["id"], "Alice")
        _join_team(test_client, code, team_b["id"], "Bob")

        response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert response.status_code == 200

    def test_game_refuses_to_start_if_a_solo_team_has_no_player_yet(self, test_client):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}

        team_a = _create_team(test_client, code, "Solo A")
        team_b = _create_team(test_client, code, "Solo B")
        _join_team(test_client, code, team_a["id"], "Alice")
        # team_b reste vide

        response = test_client.post(f"/games/{code}/start", headers=host_headers)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Solo B" in detail
        assert "Solo A" not in detail  # équipe déjà complète, ne doit pas apparaître dans l'erreur


class TestNoMixedTeamSizeInvariant:
    """AC #4 : players_per_team est un champ unique par GameSession (pas par
    équipe) -- il est structurellement impossible de mélanger des équipes de
    taille 1 avec des équipes de taille 2-3 dans la même partie. Ce test ne
    couvre pas une garde applicative (il n'y en a pas besoin) : il documente
    que TeamCreate n'expose aucun moyen de choisir une taille différente de
    celle de la partie."""

    def test_team_create_schema_has_no_size_field(self):
        from app import schemas
        assert set(schemas.TeamCreate.model_fields.keys()) == {"name"}

    def test_every_team_in_a_solo_game_is_capped_at_the_same_size(self, test_client):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        team_a = _create_team(test_client, code, "Solo A")
        team_b = _create_team(test_client, code, "Solo B")

        for team in (team_a, team_b):
            _join_team(test_client, code, team["id"], "P1")
            rejected = _join_team(test_client, code, team["id"], "P2")
            assert rejected.status_code == 400


class TestSoloTeamsCompatibleWithWheelAndDuels:
    """Smoke test : les mécaniques déjà génériques par team_id (roue, duels,
    tokens) fonctionnent sans changement avec des équipes solo -- vérifié
    par lecture de code en amont (SPEC-mode-solo-manche-1), couvert ici."""

    def test_wheel_malus_applies_to_a_solo_team(self, test_client, db_session):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        team = _create_team(test_client, code, "Solo A")
        _create_team(test_client, code, "Solo B")

        with patch("main.random.randint", return_value=3):
            response = test_client.post("/wheel/spin", json={"team_id": team["id"]})

        assert response.status_code == 200
        assert response.json()["effect_type"] == "malus"
        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team["id"]).first()
        assert refreshed.score == 0  # plancher à 0, score initial 0 - 3

    def test_ping_pong_duel_starts_between_two_solo_teams(self, test_client, db_session):
        game = _create_solo_game(test_client, total_players=4)
        code = game["game"]["code"]
        team_a = _create_team(test_client, code, "Solo A")
        team_b = _create_team(test_client, code, "Solo B")

        theme = models.PingPongTheme(title="Capitales", correct_answers=["Paris"])
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(theme)

        response = test_client.post("/ping-pong/duel/start", json={
            "game_session_id": game["game"]["id"],
            "theme_id": theme.id,
            "team1_id": team_a["id"],
            "team2_id": team_b["id"],
        })
        assert response.status_code == 200
        assert response.json()["duel_id"] is not None
