"""BUG-102 : aucun écran ne pouvait détecter qu'un SWAP/PENALTY/BONUS venait
d'être appliqué — /tokens/use ne renvoyait le résultat qu'à l'appelant. On
journalise désormais l'effet (TokenEffect) et get_team_state l'expose via
last_token_event, sur le même modèle que last_wheel_event."""
from app import models


def test_penalty_token_exposes_last_token_event_to_target_team(test_client, db_session, sample_game_session):
    attacker = models.Team(name="Attacker", game_session_id=sample_game_session.id, score=0)
    target = models.Team(name="Victim", game_session_id=sample_game_session.id, score=5)
    db_session.add_all([attacker, target])
    db_session.commit()

    db_session.add(models.Token(team_id=attacker.id, token_type=models.TokenType.PENALTY, is_used=False))
    db_session.commit()

    resp = test_client.post(
        "/tokens/use",
        json={"team_id": attacker.id, "token_type": "PENALTY", "target_team_id": target.id},
        headers={"X-Team-Token": attacker.team_token},
    )
    assert resp.status_code == 200

    # La cible n'a rien déclenché elle-même : elle doit pourtant voir
    # l'effet en pollant son propre état, sinon elle n'a aucun retour visuel.
    state_resp = test_client.get(f"/game/{sample_game_session.code}/team/{target.id}/state")
    assert state_resp.status_code == 200
    event = state_resp.json()["last_token_event"]
    assert event is not None
    assert event["token_type"] == "PENALTY"
    assert event["using_team_id"] == attacker.id
    assert event["target_team_id"] == target.id
    assert "Victim" in event["message"]


def test_last_token_event_is_null_when_no_token_ever_used(test_client, db_session, sample_game_session, sample_team):
    resp = test_client.get(f"/game/{sample_game_session.code}/team/{sample_team.id}/state")
    assert resp.status_code == 200
    assert resp.json()["last_token_event"] is None


def test_last_token_event_reflects_most_recent_effect_only(test_client, db_session, sample_game_session):
    attacker = models.Team(name="Attacker", game_session_id=sample_game_session.id, score=0)
    db_session.add(attacker)
    db_session.commit()

    db_session.add_all([
        models.Token(team_id=attacker.id, token_type=models.TokenType.BONUS, is_used=False),
        models.Token(team_id=attacker.id, token_type=models.TokenType.SWAP, is_used=False),
    ])
    db_session.commit()

    test_client.post(
        "/tokens/use",
        json={"team_id": attacker.id, "token_type": "BONUS"},
        headers={"X-Team-Token": attacker.team_token},
    )
    resp = test_client.post(
        "/tokens/use",
        json={"team_id": attacker.id, "token_type": "SWAP"},
        headers={"X-Team-Token": attacker.team_token},
    )
    assert resp.status_code == 200

    state_resp = test_client.get(f"/game/{sample_game_session.code}/team/{attacker.id}/state")
    event = state_resp.json()["last_token_event"]
    assert event["token_type"] == "SWAP"
