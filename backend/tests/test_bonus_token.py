"""Le jeton BONUS doit doubler les points réellement crédités en base lors
de la validation de la réponse, pas seulement dans un état côté client
(bug utilisateur : le doublement affiché ne survivait pas à la validation)."""
import json

from app import models


def _use_bonus(test_client, team):
    return test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "BONUS"},
        headers={"X-Team-Token": team.team_token},
    )


def test_bonus_token_doubles_awarded_points(test_client, db_session, sample_game_session, sample_team, sample_question):
    for token_type in [models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS]:
        db_session.add(models.Token(team_id=sample_team.id, token_type=token_type, is_used=False))
    db_session.commit()

    resp = _use_bonus(test_client, sample_team)
    assert resp.status_code == 200

    db_session.refresh(sample_team)
    assert sample_team.bonus_active is True

    sample_game_session.current_question_id = sample_question.id
    db_session.commit()

    answer_resp = test_client.post("/answers/", json={
        "question_id": sample_question.id,
        "team_id": sample_team.id,
        "player_answer": sample_question.correct_answer,
    }, headers={"X-Team-Token": sample_team.team_token})
    assert answer_resp.status_code == 200

    validate_resp = test_client.post(
        f"/games/{sample_game_session.code}/validate-answers",
        headers={"X-Host-Token": sample_game_session.host_token},
    )
    assert validate_resp.status_code == 200
    body = validate_resp.json()

    team_result = next(t for t in body["teams_updated"] if t["team_id"] == sample_team.id)
    assert team_result["points_earned"] == sample_question.points * 2

    db_session.refresh(sample_team)
    assert sample_team.score == sample_question.points * 2
    assert sample_team.bonus_active is False


def test_bonus_token_consumed_even_on_wrong_answer(test_client, db_session, sample_game_session, sample_team, sample_question):
    db_session.add(models.Token(team_id=sample_team.id, token_type=models.TokenType.BONUS, is_used=False))
    db_session.commit()

    _use_bonus(test_client, sample_team)
    db_session.refresh(sample_team)
    assert sample_team.bonus_active is True

    sample_game_session.current_question_id = sample_question.id
    db_session.commit()

    test_client.post("/answers/", json={
        "question_id": sample_question.id,
        "team_id": sample_team.id,
        "player_answer": "wrong answer",
    }, headers={"X-Team-Token": sample_team.team_token})

    test_client.post(
        f"/games/{sample_game_session.code}/validate-answers",
        headers={"X-Host-Token": sample_game_session.host_token},
    )

    db_session.refresh(sample_team)
    assert sample_team.score == 0
    assert sample_team.bonus_active is False
