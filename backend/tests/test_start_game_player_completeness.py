"""BUG-201 : le nom générique "Player {équipe} {n}" apparaissait jusqu'en
Manche 2 pour de vrais joueurs. Cause : /games/{code}/start comblait
silencieusement les équipes incomplètes avec des joueurs factices dès lors
que le host cliquait "Démarrer" avant que tout le monde ait rejoint (le
bouton ne bloquait pas non plus côté frontend). Le fix retire l'auto-fill :
la validation existante ("chaque équipe doit avoir players_per_team joueurs")
redevient réellement appliquée au lieu d'être toujours trivialement
satisfaite."""

from app import models


def test_start_game_rejects_incomplete_team(test_client, db_session, sample_game_session, sample_team, host_headers):
    team2 = models.Team(name="Team 2", game_session_id=sample_game_session.id)
    db_session.add(team2)
    db_session.commit()

    # sample_team et team2 n'ont aucun joueur (players_per_team=2 attendu).
    resp = test_client.post(f"/games/{sample_game_session.code}/start", headers=host_headers)

    assert resp.status_code == 400
    assert "joueurs" in resp.json()["detail"]

    # Aucun joueur factice ne doit avoir été créé silencieusement.
    players = db_session.query(models.Player).filter(models.Player.team_id.in_([sample_team.id, team2.id])).all()
    assert players == []


def test_start_game_succeeds_once_all_teams_are_full(test_client, db_session, sample_game_session, sample_team, host_headers):
    team2 = models.Team(name="Team 2", game_session_id=sample_game_session.id)
    db_session.add(team2)
    db_session.commit()
    db_session.refresh(team2)

    db_session.add_all([
        models.Player(name="Alice", team_id=sample_team.id),
        models.Player(name="Bob", team_id=sample_team.id),
        models.Player(name="Carol", team_id=team2.id),
        models.Player(name="Dave", team_id=team2.id),
    ])
    db_session.commit()

    resp = test_client.post(f"/games/{sample_game_session.code}/start", headers=host_headers)

    assert resp.status_code == 200, resp.json()