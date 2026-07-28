"""La roue de fortune (malus/bonus/ping-pong tous les 5 tours) n'existait
que sur l'écran mono-appareil (Game.tsx) : le flux réel multi-appareils
(TeamScreen.tsx via /next-question) ne comptait jamais les tours joués et
ne déclenchait donc jamais rien après la 5e question — bug utilisateur."""
import main
from app import models


def _make_two_teams(db_session, sample_game_session):
    team1 = models.Team(name="Team A", game_session_id=sample_game_session.id, score=10)
    team2 = models.Team(name="Team B", game_session_id=sample_game_session.id, score=5)
    db_session.add_all([team1, team2])
    db_session.commit()
    db_session.refresh(team1)
    db_session.refresh(team2)
    return team1, team2


def test_wheel_does_not_trigger_before_fifth_question(test_client, db_session, sample_game_session, sample_question):
    _make_two_teams(db_session, sample_game_session)

    for _ in range(4):
        resp = test_client.post(f"/games/{sample_game_session.code}/next-question")
        assert resp.status_code == 200
        body = resp.json()
        assert body["question_id"] is not None
        assert "wheel_event" not in body

    db_session.refresh(sample_game_session)
    assert sample_game_session.questions_played == 4


def test_wheel_triggers_malus_on_fifth_question(test_client, db_session, sample_game_session, sample_question, monkeypatch):
    team1, _team2 = _make_two_teams(db_session, sample_game_session)
    monkeypatch.setattr(main.random, "randint", lambda a, b: 3)  # 1-5 => malus

    for _ in range(4):
        test_client.post(f"/games/{sample_game_session.code}/next-question")

    resp = test_client.post(f"/games/{sample_game_session.code}/next-question")
    assert resp.status_code == 200
    body = resp.json()
    assert body["question_id"] is None
    assert body["wheel_event"]["effect_type"] == "malus"
    assert body["wheel_event"]["target_team_id"] == team1.id

    db_session.refresh(team1)
    assert team1.score == 7  # 10 - 3

    effect = db_session.query(models.WheelEffect).filter(
        models.WheelEffect.game_session_id == sample_game_session.id
    ).first()
    assert effect is not None
    assert effect.is_applied is True


def test_wheel_triggers_ping_pong_duel_on_fifth_question(test_client, db_session, sample_game_session, sample_question, monkeypatch):
    team1, team2 = _make_two_teams(db_session, sample_game_session)
    theme = models.PingPongTheme(title="Capitales", correct_answers=["Paris", "Berlin"])
    db_session.add(theme)
    db_session.commit()

    monkeypatch.setattr(main.random, "randint", lambda a, b: 12)  # 11-18 => ping_pong
    monkeypatch.setattr(main.random, "choice", lambda seq: team2)

    for _ in range(4):
        test_client.post(f"/games/{sample_game_session.code}/next-question")

    resp = test_client.post(f"/games/{sample_game_session.code}/next-question")
    body = resp.json()
    assert body["wheel_event"]["effect_type"] == "ping_pong"
    assert body["wheel_event"]["duel_id"] is not None

    duel = db_session.query(models.PingPongDuel).filter(
        models.PingPongDuel.id == body["wheel_event"]["duel_id"]
    ).first()
    assert duel is not None
    assert duel.team1_id == team1.id
    assert duel.team2_id == team2.id


def test_state_exposes_last_wheel_event_to_all_teams(test_client, db_session, sample_game_session, sample_question, monkeypatch):
    team1, team2 = _make_two_teams(db_session, sample_game_session)
    monkeypatch.setattr(main.random, "randint", lambda a, b: 20)  # 19-20 => bonus +3

    for _ in range(5):
        test_client.post(f"/games/{sample_game_session.code}/next-question")

    # L'équipe qui N'A PAS tourné la roue doit aussi voir l'événement.
    resp = test_client.get(f"/game/{sample_game_session.code}/team/{team2.id}/state")
    assert resp.status_code == 200
    event = resp.json()["last_wheel_event"]
    assert event is not None
    assert event["effect_type"] == "bonus"
    assert event["target_team_id"] == team1.id
