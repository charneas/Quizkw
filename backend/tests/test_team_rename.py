"""Renommage d'equipe (item misc du rapport de playtest 2026-07-31)."""
from app import models


def test_rename_team_success(test_client, db_session, sample_game_session):
    team = models.Team(name="Equipe A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    resp = test_client.patch(
        f"/games/{sample_game_session.code}/teams/{team.id}",
        json={"name": "Les Champions"},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Les Champions"

    db_session.refresh(team)
    assert team.name == "Les Champions"


def test_rename_team_rejects_wrong_token(test_client, db_session, sample_game_session):
    team = models.Team(name="Equipe A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    resp = test_client.patch(
        f"/games/{sample_game_session.code}/teams/{team.id}",
        json={"name": "Les Champions"},
        headers={"X-Team-Token": "wrong-token"},
    )
    assert resp.status_code == 403

    db_session.refresh(team)
    assert team.name == "Equipe A"


def test_rename_team_rejects_duplicate_name(test_client, db_session, sample_game_session):
    team1 = models.Team(name="Equipe A", game_session_id=sample_game_session.id, score=0)
    team2 = models.Team(name="Equipe B", game_session_id=sample_game_session.id, score=0)
    db_session.add_all([team1, team2])
    db_session.commit()
    db_session.refresh(team1)
    db_session.refresh(team2)

    resp = test_client.patch(
        f"/games/{sample_game_session.code}/teams/{team1.id}",
        json={"name": "equipe b"},
        headers={"X-Team-Token": team1.team_token},
    )
    assert resp.status_code == 400


def test_rename_team_allows_keeping_own_name(test_client, db_session, sample_game_session):
    team = models.Team(name="Equipe A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    resp = test_client.patch(
        f"/games/{sample_game_session.code}/teams/{team.id}",
        json={"name": "Equipe A"},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 200


def test_rename_team_rejects_blank_name(test_client, db_session, sample_game_session):
    team = models.Team(name="Equipe A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    resp = test_client.patch(
        f"/games/{sample_game_session.code}/teams/{team.id}",
        json={"name": "   "},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 422