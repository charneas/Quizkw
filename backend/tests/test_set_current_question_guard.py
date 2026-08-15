"""
Garde anti-question parasite pendant un duel ping-pong (story J.003, BUG-105).

Playtest 2026-07-31 : d'autres questions se lançaient alors qu'un duel
ping-pong était déjà en cours, causant de la confusion sur ce à quoi
répondre. set_current_question est le seul point d'entrée qui définit la
question courante pour toutes les équipes — il doit refuser tant qu'un duel
actif existe, peu importe les équipes impliquées.
"""
from app import models


def _make_team(db_session, game, name):
    team = models.Team(name=name, game_session_id=game.id)
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


def test_set_current_question_rejected_while_duel_active(
    test_client, db_session, sample_game_session, host_headers, sample_question
):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    duel = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers=host_headers)
    assert duel.status_code == 200

    response = test_client.post(
        f"/games/{sample_game_session.code}/set-current-question",
        json={"question_id": sample_question.id},
        headers=host_headers,
    )
    assert response.status_code == 400

    db_session.expire_all()
    refreshed = db_session.query(models.GameSession).filter(
        models.GameSession.id == sample_game_session.id
    ).first()
    assert refreshed.current_question_id is None


def test_set_current_question_allowed_after_duel_completed_normally(
    test_client, db_session, sample_game_session, host_headers, sample_question
):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    duel_response = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers=host_headers)
    duel_id = duel_response.json()["duel_id"]

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_completed = True
    duel.winner_team_id = team1.id
    db_session.commit()

    response = test_client.post(
        f"/games/{sample_game_session.code}/set-current-question",
        json={"question_id": sample_question.id},
        headers=host_headers,
    )
    assert response.status_code == 200


def test_set_current_question_allowed_after_duel_cancelled(
    test_client, db_session, sample_game_session, host_headers, sample_question
):
    """Intégration avec J.002 : un duel annulé libère aussi ce garde."""
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    duel_response = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers=host_headers)
    duel_id = duel_response.json()["duel_id"]

    cancel = test_client.post(
        f"/games/{sample_game_session.code}/ping-pong/duel/{duel_id}/cancel",
        headers=host_headers,
    )
    assert cancel.status_code == 200

    response = test_client.post(
        f"/games/{sample_game_session.code}/set-current-question",
        json={"question_id": sample_question.id},
        headers=host_headers,
    )
    assert response.status_code == 200


def test_set_current_question_works_normally_without_any_duel(
    test_client, db_session, sample_game_session, host_headers, sample_question
):
    response = test_client.post(
        f"/games/{sample_game_session.code}/set-current-question",
        json={"question_id": sample_question.id},
        headers=host_headers,
    )
    assert response.status_code == 200

    db_session.expire_all()
    refreshed = db_session.query(models.GameSession).filter(
        models.GameSession.id == sample_game_session.id
    ).first()
    assert refreshed.current_question_id == sample_question.id