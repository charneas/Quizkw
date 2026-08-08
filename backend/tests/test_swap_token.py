"""Le jeton SWAP ne changeait jamais le thème d'un duel ping-pong en cours
(bug utilisateur) : use_token ne faisait que marquer le jeton comme utilisé,
sans aucun effet réel ni pour un duel, ni pour une question normale."""
from app import models


def test_swap_token_changes_active_duel_theme(test_client, db_session, sample_game_session):
    team1 = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    team2 = models.Team(name="Team B", game_session_id=sample_game_session.id, score=0)
    db_session.add_all([team1, team2])
    db_session.commit()

    theme1 = models.PingPongTheme(title="Capitales", correct_answers=["Paris"])
    theme2 = models.PingPongTheme(title="Fleuves", correct_answers=["Loire"])
    db_session.add_all([theme1, theme2])
    db_session.commit()

    duel = models.PingPongDuel(
        game_session_id=sample_game_session.id,
        theme_id=theme1.id,
        team1_id=team1.id,
        team2_id=team2.id,
        current_turn_team_id=team1.id,
        is_completed=False,
        answers_used=["Paris"],
    )
    db_session.add(duel)
    db_session.add(models.Token(team_id=team1.id, token_type=models.TokenType.SWAP, is_used=False))
    db_session.commit()
    db_session.refresh(duel)

    resp = test_client.post("/tokens/use", json={"team_id": team1.id, "token_type": "SWAP"})
    assert resp.status_code == 200

    db_session.refresh(duel)
    assert duel.theme_id == theme2.id
    assert duel.answers_used == []


def test_swap_token_changes_current_question_outside_duel(test_client, db_session, sample_game_session, sample_questions_for_theme):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    sample_game_session.current_question_id = sample_questions_for_theme[0].id
    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.SWAP, is_used=False))
    db_session.commit()

    resp = test_client.post("/tokens/use", json={"team_id": team.id, "token_type": "SWAP"})
    assert resp.status_code == 200

    db_session.refresh(sample_game_session)
    assert sample_game_session.current_question_id != sample_questions_for_theme[0].id


def test_other_teams_available_without_current_question(test_client, db_session, sample_game_session):
    """Nécessaire pour cibler PENALTY ou choisir un adversaire ping-pong
    entre deux questions (quand game.current_question_id est None)."""
    team1 = models.Team(name="Team A", game_session_id=sample_game_session.id, score=3)
    team2 = models.Team(name="Team B", game_session_id=sample_game_session.id, score=7)
    db_session.add_all([team1, team2])
    db_session.commit()

    assert sample_game_session.current_question_id is None

    resp = test_client.get(f"/game/{sample_game_session.code}/team/{team1.id}/state")
    assert resp.status_code == 200
    other_teams = resp.json()["other_teams"]
    assert len(other_teams) == 1
    assert other_teams[0]["team_id"] == team2.id
    assert other_teams[0]["team_score"] == 7
