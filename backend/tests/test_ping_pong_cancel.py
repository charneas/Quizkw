"""
Annulation host d'un duel ping-pong bloqué (story J.002, BUG-101g).

Depuis le fix de #54 (BUG-101c), un duel abandonné verrouille définitivement
les deux équipes concernées (garde anti-double-duel dans start_duel). Cette
story ajoute une échappatoire host explicite, sans timeout automatique
(décision produit confirmée le 2026-08-09).
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
    })
    assert response.status_code == 200
    return response.json()["duel_id"]


def test_cancel_duel_frees_both_teams_without_touching_score(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
    team2 = _make_team(db_session, sample_game_session, "Team B", score=3)
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_completed"] is True
    assert data["is_cancelled"] is True
    assert data["winner_team_id"] is None

    db_session.expire_all()
    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    assert duel.is_completed is True
    assert duel.is_cancelled is True
    assert duel.winner_team_id is None

    team1_refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
    team2_refreshed = db_session.query(models.Team).filter(models.Team.id == team2.id).first()
    assert team1_refreshed.score == 5
    assert team2_refreshed.score == 3


def test_teams_can_start_new_duel_after_cancellation(test_client, db_session, sample_game_session, host_headers):
    """Régression directe du bug : le garde anti-double-duel de #54 ne doit
    plus bloquer les équipes une fois le duel annulé."""
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    team3 = _make_team(db_session, sample_game_session, "Team C")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )

    response = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team3.id,
    })
    assert response.status_code == 200


def test_cancel_already_completed_duel_fails(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_completed = True
    duel.winner_team_id = team1.id
    db_session.commit()

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )
    assert response.status_code == 400


def test_cancel_tiebreak_duel_refused(test_client, db_session, sample_game_session, host_headers):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_tiebreak = True
    db_session.commit()

    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )
    assert response.status_code == 400

    db_session.expire_all()
    refreshed = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    assert refreshed.is_completed is False


def test_cancel_requires_host_token(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, sample_game_session, theme, team1, team2)

    response = test_client.post(f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel")
    assert response.status_code == 403


def test_cancel_duel_from_another_game_returns_404(test_client, db_session, sample_game_session, host_headers):
    other_game = models.GameSession(
        code="OTHERGAME", total_players=4, players_per_team=2,
        current_round=models.RoundType.MANCHE_1, is_active=True,
    )
    db_session.add(other_game)
    db_session.commit()
    db_session.refresh(other_game)

    team1 = _make_team(db_session, other_game, "Team X")
    team2 = _make_team(db_session, other_game, "Team Y")
    theme = _make_theme(db_session, "Capitales", ["Paris"])
    duel_id = _start_duel(test_client, other_game, theme, team1, team2)

    # host_headers correspond à sample_game_session, pas other_game.
    response = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )
    assert response.status_code == 404