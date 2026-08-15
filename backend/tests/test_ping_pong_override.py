"""
Surclassement manuel host d'une réponse ping-pong jugée incorrecte
automatiquement (BUG-505, #37) : synonyme, réponse partielle valide...
"""
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


def _start_duel(test_client, game, theme, team1, team2):
    response = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": game.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": game.host_token})
    assert response.status_code == 200
    return response.json()["duel_id"]


def _lose_duel_on_wrong_answer(test_client, duel_id, losing_team):
    """team1 commence toujours (start_duel) — on le fait perdre direct."""
    response = test_client.post("/ping-pong/duel/answer", json={
        "duel_id": duel_id,
        "team_id": losing_team.id,
        "answer": "Cette réponse n'est pas dans la liste",
    }, headers={"X-Team-Token": losing_team.team_token})
    assert response.status_code == 200
    assert response.json()["duel_continues"] is False
    return response.json()


def test_override_reverses_points_and_resumes_duel(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A", score=0)
    team2 = _make_team(db_session, sample_game_session, "Team B", score=0)
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    # team1 répond en premier (ordre fixé par start_duel) et perd — team2 gagne +2.
    _lose_duel_on_wrong_answer(test_client, duel_id, team1)

    db_session.expire_all()
    team2_after_loss = db_session.query(models.Team).filter(models.Team.id == team2.id).first()
    assert team2_after_loss.score == 2

    turn = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.duel_id == duel_id).first()
    assert turn.is_correct is False

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/turns/{turn.id}/override",
        headers=host_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_completed"] is False
    assert data["winner_team_id"] is None
    # Le tour passe à l'équipe adverse de celle qui vient d'être validée (team1).
    assert data["current_turn_team_id"] == team2.id

    db_session.expire_all()
    team2_refreshed = db_session.query(models.Team).filter(models.Team.id == team2.id).first()
    assert team2_refreshed.score == 0  # points du faux gagnant retirés

    turn_refreshed = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.id == turn.id).first()
    assert turn_refreshed.is_correct is True

    duel_refreshed = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    assert duel_refreshed.is_completed is False
    assert duel_refreshed.winner_team_id is None


def test_override_already_correct_turn_fails(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    response = test_client.post("/ping-pong/duel/answer", json={
        "duel_id": duel_id,
        "team_id": team1.id,
        "answer": "Paris",
    }, headers={"X-Team-Token": team1.team_token})
    assert response.status_code == 200
    assert response.json()["is_correct"] is True

    turn = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.duel_id == duel_id).first()

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/turns/{turn.id}/override",
        headers=host_headers,
    )
    assert response.status_code == 400


def test_override_tiebreak_duel_refused(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)
    _lose_duel_on_wrong_answer(test_client, duel_id, team1)

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_tiebreak = True
    db_session.commit()

    turn = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.duel_id == duel_id).first()

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/turns/{turn.id}/override",
        headers=host_headers,
    )
    assert response.status_code == 400


def test_override_requires_host_token(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)
    _lose_duel_on_wrong_answer(test_client, duel_id, team1)

    turn = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.duel_id == duel_id).first()

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/turns/{turn.id}/override",
    )
    assert response.status_code == 403


def test_override_from_another_game_returns_404(test_client, db_session, sample_game_session, host_headers):
    other_game = models.GameSession(
        code="OTHERGAME2", total_players=4, players_per_team=2,
        current_round=models.RoundType.MANCHE_1, is_active=True,
    )
    db_session.add(other_game)
    db_session.commit()
    db_session.refresh(other_game)

    team1 = _make_team(db_session, other_game, "Team X")
    team2 = _make_team(db_session, other_game, "Team Y")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, other_game, theme, team1, team2)
    _lose_duel_on_wrong_answer(test_client, duel_id, team1)

    turn = db_session.query(models.PingPongTurn).filter(models.PingPongTurn.duel_id == duel_id).first()

    # host_headers correspond à sample_game_session, pas other_game.
    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/turns/{turn.id}/override",
        headers=host_headers,
    )
    assert response.status_code == 404