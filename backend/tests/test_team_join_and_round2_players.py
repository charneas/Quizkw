"""Le pseudo n'était jamais réellement saisi en Manche 1 : start_game
générait des joueurs factices ("Player <équipe> <n>") et le formulaire de la
Manche 2 créait un joueur libre, jamais relié à la qualification de la
Manche 1 (bug utilisateur). /games/{code}/teams/{team_id}/players/ est le
vrai point d'entrée du pseudo dès qu'on rejoint une équipe, et
/round2/{code}/players expose les qualifiés pour une reconnexion fidèle."""
from app import models


def test_join_team_creates_named_player(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    resp = test_client.post(
        f"/games/{sample_game_session.code}/teams/{team.id}/players/",
        json={"name": "Alice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Alice"
    assert body["team_id"] == team.id


def test_join_team_rejects_blank_pseudo(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    resp = test_client.post(
        f"/games/{sample_game_session.code}/teams/{team.id}/players/",
        json={"name": "   "},
    )
    assert resp.status_code == 422


def test_join_team_rejects_duplicate_pseudo_in_same_team(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "Alice"})
    resp = test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "alice"})
    assert resp.status_code == 400


def test_join_team_rejects_when_team_full(test_client, db_session, sample_game_session):
    # sample_game_session : players_per_team = 2
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "Alice"})
    test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "Bob"})
    resp = test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "Charlie"})
    assert resp.status_code == 400


def test_join_team_rejects_after_game_started(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    sample_game_session.started = True
    db_session.commit()

    resp = test_client.post(f"/games/{sample_game_session.code}/teams/{team.id}/players/", json={"name": "Alice"})
    assert resp.status_code == 400


def test_round2_players_lists_only_qualified(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    p1 = models.Player(name="Alice", team_id=team.id)
    p2 = models.Player(name="Bob", team_id=team.id)  # pas qualifié
    db_session.add_all([p1, p2])
    db_session.commit()
    db_session.refresh(p1)

    db_session.add(models.PlayerRound2Stats(
        player_id=p1.id,
        game_session_id=sample_game_session.id,
        score=0,
    ))
    db_session.commit()

    resp = test_client.get(f"/round2/{sample_game_session.code}/players")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == ["Alice"]
