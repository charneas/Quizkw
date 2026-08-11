"""
Nombre de questions et fréquence de la roue configurables en Manche 1.

Avant ce changement, `MANCHE_1_MAX_QUESTIONS = 20` et la cadence de la roue
(`% 5`) étaient des constantes en dur, identiques pour toutes les parties.
Ces deux valeurs deviennent des champs par partie (`GameSession.manche1_question_count`,
`GameSession.wheel_frequency`), choisis par l'hôte à la création.
"""
from unittest.mock import patch

from app import models


def _create_game(test_client, **overrides):
    payload = {
        "total_players": 8,
        "players_per_team": 2,
    }
    payload.update(overrides)
    response = test_client.post("/games/", json=payload)
    assert response.status_code == 200
    return response.json()


def _create_team(test_client, code, name):
    response = test_client.post(f"/games/{code}/teams/", json={"name": name})
    assert response.status_code == 200
    return response.json()


class TestDefaults:
    def test_defaults_to_twenty_questions_and_frequency_five(self, test_client):
        game = _create_game(test_client)
        assert game["game"]["manche1_question_count"] == 20
        assert game["game"]["wheel_frequency"] == 5


class TestQuestionCountValidation:
    def test_accepts_any_multiple_of_five_between_20_and_50(self, test_client):
        for value in (20, 25, 30, 35, 40, 45, 50):
            game = _create_game(test_client, manche1_question_count=value)
            assert game["game"]["manche1_question_count"] == value

    def test_rejects_a_value_not_a_multiple_of_five(self, test_client):
        response = test_client.post("/games/", json={
            "total_players": 8, "players_per_team": 2, "manche1_question_count": 22,
        })
        assert response.status_code == 422

    def test_rejects_below_the_floor(self, test_client):
        response = test_client.post("/games/", json={
            "total_players": 8, "players_per_team": 2, "manche1_question_count": 15,
        })
        assert response.status_code == 422

    def test_rejects_above_the_ceiling(self, test_client):
        response = test_client.post("/games/", json={
            "total_players": 8, "players_per_team": 2, "manche1_question_count": 55,
        })
        assert response.status_code == 422


class TestWheelFrequencyValidation:
    def test_accepts_five_and_ten(self, test_client):
        for value in (5, 10):
            game = _create_game(test_client, wheel_frequency=value)
            assert game["game"]["wheel_frequency"] == value

    def test_rejects_any_other_value(self, test_client):
        response = test_client.post("/games/", json={
            "total_players": 8, "players_per_team": 2, "wheel_frequency": 7,
        })
        assert response.status_code == 422


class TestManche1EndsAtConfiguredQuestionCount:
    def test_manche1_ends_at_25_not_20_when_configured(self, test_client, db_session):
        game = _create_game(test_client, manche1_question_count=25, wheel_frequency=10)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}
        team_a = _create_team(test_client, code, "Team A")
        team_b = _create_team(test_client, code, "Team B")
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P1"})
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P2"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P3"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P4"})
        test_client.post(f"/games/{code}/start", headers=host_headers)

        db_obj = db_session.query(models.GameSession).filter(models.GameSession.code == code).first()
        db_obj.questions_played = 24
        db_session.commit()

        response = test_client.post(f"/games/{code}/next-question", headers=host_headers)
        assert response.status_code == 200
        assert response.json().get("manche1_end") is not None


class TestWheelFrequencyControlsCadence:
    def test_no_wheel_at_the_fifth_question_when_frequency_is_ten(self, test_client, db_session, sample_question):
        game = _create_game(test_client, wheel_frequency=10, manche1_question_count=50)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}
        team_a = _create_team(test_client, code, "Team A")
        team_b = _create_team(test_client, code, "Team B")
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P1"})
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P2"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P3"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P4"})
        test_client.post(f"/games/{code}/start", headers=host_headers)

        db_obj = db_session.query(models.GameSession).filter(models.GameSession.code == code).first()
        db_obj.questions_played = 4
        db_session.commit()

        response = test_client.post(f"/games/{code}/next-question", headers=host_headers)
        assert response.status_code == 200
        assert "wheel_event" not in response.json()

    def test_wheel_triggers_at_the_tenth_question_when_frequency_is_ten(self, test_client, db_session):
        game = _create_game(test_client, wheel_frequency=10, manche1_question_count=50)
        code = game["game"]["code"]
        host_headers = {"X-Host-Token": game["host_token"]}
        team_a = _create_team(test_client, code, "Team A")
        team_b = _create_team(test_client, code, "Team B")
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P1"})
        test_client.post(f"/games/{code}/teams/{team_a['id']}/players/", json={"name": "P2"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P3"})
        test_client.post(f"/games/{code}/teams/{team_b['id']}/players/", json={"name": "P4"})
        test_client.post(f"/games/{code}/start", headers=host_headers)

        db_obj = db_session.query(models.GameSession).filter(models.GameSession.code == code).first()
        db_obj.questions_played = 9
        db_session.commit()

        with patch("main.random.randint", return_value=19):
            response = test_client.post(f"/games/{code}/next-question", headers=host_headers)
        assert response.status_code == 200
        assert response.json().get("wheel_event") is not None
