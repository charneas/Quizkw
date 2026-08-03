"""BUG-103 : le rôle host était un booléen (`has_host`) posé par un endpoint
sans authentification — n'importe quel joueur pouvait s'auto-déclarer host et
piloter la partie (lancer les questions à volonté, ignorer les autres). Le
host est désormais le créateur de la partie, identifié par un host_token
secret généré à la création et exigé sur tous les endpoints de contrôle."""


def test_create_game_returns_host_token(test_client):
    resp = test_client.post("/games/", json={"total_players": 6, "players_per_team": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["host_token"]
    assert len(body["host_token"]) >= 20


def test_start_game_without_token_is_rejected(test_client, sample_game_session):
    resp = test_client.post(f"/games/{sample_game_session.code}/start")
    assert resp.status_code == 403


def test_start_game_with_wrong_token_is_rejected(test_client, sample_game_session):
    resp = test_client.post(
        f"/games/{sample_game_session.code}/start",
        headers={"X-Host-Token": "not-the-real-token"},
    )
    assert resp.status_code == 403


def test_start_game_with_correct_token_is_allowed(test_client, db_session, sample_game_session, sample_team, host_headers):
    from app import models
    db_session.add(models.Team(name="Team 2", game_session_id=sample_game_session.id))
    db_session.commit()

    resp = test_client.post(f"/games/{sample_game_session.code}/start", headers=host_headers)
    assert resp.status_code == 200


def test_next_question_requires_host_token(test_client, sample_game_session):
    resp = test_client.post(f"/games/{sample_game_session.code}/next-question")
    assert resp.status_code == 403


def test_validate_answers_requires_host_token(test_client, sample_game_session):
    resp = test_client.post(f"/games/{sample_game_session.code}/validate-answers")
    assert resp.status_code == 403


def test_round2_advance_requires_host_token(test_client, sample_game_session):
    resp = test_client.post(f"/round2/{sample_game_session.code}/advance")
    assert resp.status_code == 403


def test_advance_to_phase3_requires_host_token(test_client, sample_game_session):
    resp = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")
    assert resp.status_code == 403


def test_host_token_unknown_game_returns_404_not_403(test_client):
    resp = test_client.post("/games/DOESNOTEXIST/start")
    assert resp.status_code == 404
