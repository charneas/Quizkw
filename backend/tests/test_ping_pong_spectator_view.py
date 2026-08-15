"""BUG-104 / Story J.001 : une équipe hors duel n'avait aucune visibilité sur
un duel ping-pong en cours dans sa partie. get_team_state expose désormais
spectator_duel (distinct de active_duel, réservé aux équipes participantes)
pour permettre une vue lecture seule."""
from app import models


def _make_team(db_session, game, name, score=0):
    team = models.Team(name=name, game_session_id=game.id, score=score)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


def _make_theme(db_session, title, correct_answers):
    theme = models.PingPongTheme(title=title, correct_answers=correct_answers)
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def test_team_outside_duel_sees_spectator_duel(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    bystander = _make_team(db_session, sample_game_session, "Team C")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    start = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    assert start.status_code == 200

    resp = test_client.get(f"/game/{sample_game_session.code}/team/{bystander.id}/state", headers={"X-Team-Token": bystander.team_token})
    assert resp.status_code == 200
    data = resp.json()

    assert data["active_duel"] is None
    assert data["spectator_duel"] is not None
    assert data["spectator_duel"]["team1"]["id"] == team1.id
    assert data["spectator_duel"]["team2"]["id"] == team2.id
    assert data["spectator_duel"]["is_my_turn_in_duel"] is False


def test_participant_team_never_gets_spectator_duel(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    start = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    assert start.status_code == 200

    resp = test_client.get(f"/game/{sample_game_session.code}/team/{team1.id}/state", headers={"X-Team-Token": team1.team_token})
    data = resp.json()

    assert data["active_duel"] is not None
    assert data["spectator_duel"] is None


def test_no_active_duel_means_spectator_duel_is_null(test_client, db_session, sample_game_session, sample_team):
    resp = test_client.get(f"/game/{sample_game_session.code}/team/{sample_team.id}/state", headers={"X-Team-Token": sample_team.team_token})
    assert resp.status_code == 200
    assert resp.json()["spectator_duel"] is None


def test_spectator_duel_reflects_completion_and_winner(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    bystander = _make_team(db_session, sample_game_session, "Team C")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    start = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    duel_id = start.json()["duel_id"]

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_completed = True
    duel.winner_team_id = team1.id
    db_session.commit()

    resp = test_client.get(f"/game/{sample_game_session.code}/team/{bystander.id}/state", headers={"X-Team-Token": bystander.team_token})
    data = resp.json()
    assert data["spectator_duel"]["is_completed"] is True
    assert data["spectator_duel"]["winner_team_id"] == team1.id
