"""Manche 1 tournait indéfiniment (bug utilisateur : pas de limite de
questions). Elle est maintenant plafonnée à 20 questions ; à la 20e, elle se
termine et qualifie les équipes pour la Manche 2. Si le classement laisse une
égalité gênante sur la dernière place qualificative, un duel ping-pong de
départage tranche avant la qualification (au lieu d'un tri arbitraire)."""
import main
from app import models


def _make_team(db_session, game, name, score, n_players=2):
    team = models.Team(name=name, game_session_id=game.id, score=score)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    for i in range(n_players):
        db_session.add(models.Player(name=f"{name} P{i}", team_id=team.id))
    db_session.commit()
    return team


def _play_to_question(test_client, code, n, host_headers):
    for _ in range(n):
        test_client.post(f"/games/{code}/next-question", headers=host_headers)


def test_manche1_caps_at_20_questions_no_tie(test_client, db_session, sample_game_session, sample_question, host_headers):
    # 4 équipes de 2 joueurs = exactement 8 places (ROUND2_SLOTS) : pas d'ambiguïté.
    for i in range(4):
        _make_team(db_session, sample_game_session, f"Team {i}", score=100 - i * 10)

    for _ in range(19):
        resp = test_client.post(f"/games/{sample_game_session.code}/next-question", headers=host_headers)
        assert resp.json()["question_id"] is not None or resp.json().get("wheel_event") is not None

    resp = test_client.post(f"/games/{sample_game_session.code}/next-question", headers=host_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["question_id"] is None
    assert body["manche1_end"]["status"] == "qualified"

    db_session.refresh(sample_game_session)
    assert sample_game_session.current_round == models.RoundType.MANCHE_2


def test_manche1_end_triggers_tiebreak_duel_on_ambiguous_tie(test_client, db_session, sample_game_session, sample_question, host_headers):
    # 5 équipes de 2 joueurs = 10 places demandées pour 8 disponibles.
    # Les deux moins bien classées sont à égalité (70) pour la dernière place.
    t1 = _make_team(db_session, sample_game_session, "T1", score=100)
    t2 = _make_team(db_session, sample_game_session, "T2", score=90)
    t3 = _make_team(db_session, sample_game_session, "T3", score=80)
    t4 = _make_team(db_session, sample_game_session, "T4", score=70)
    t5 = _make_team(db_session, sample_game_session, "T5", score=70)

    theme = models.PingPongTheme(title="Capitales", correct_answers=["Paris"])
    db_session.add(theme)
    db_session.commit()

    _play_to_question(test_client, sample_game_session.code, 19, host_headers)
    resp = test_client.post(f"/games/{sample_game_session.code}/next-question", headers=host_headers)
    body = resp.json()
    assert body["manche1_end"]["status"] == "tiebreak_started"
    tied_ids = {t4.id, t5.id}
    assert body["manche1_end"]["team1_id"] in tied_ids
    assert body["manche1_end"]["team2_id"] in tied_ids

    db_session.refresh(sample_game_session)
    assert sample_game_session.current_round == models.RoundType.MANCHE_1  # pas encore qualifié

    duel = db_session.query(models.PingPongDuel).filter(
        models.PingPongDuel.id == body["manche1_end"]["duel_id"]
    ).first()
    assert duel.is_tiebreak is True

    # Un appel next-question pendant le duel de départage ne doit rien casser.
    guard_resp = test_client.post(f"/games/{sample_game_session.code}/next-question", headers=host_headers)
    assert guard_resp.json()["question_id"] is None
    db_session.refresh(sample_game_session)
    questions_played_before = sample_game_session.questions_played

    # Le vainqueur du duel remporte la place qualificative litigieuse.
    winner_team_id = duel.team1_id
    answer_resp = test_client.post("/ping-pong/duel/answer", json={
        "duel_id": duel.id,
        "team_id": winner_team_id,
        "answer": "Paris",
    })
    # Réponse correcte -> le duel continue (tour de l'autre équipe) ; on le
    # fait perdre pour terminer le duel immédiatement et connaître le gagnant.
    assert answer_resp.status_code == 200
    loser_team_id = duel.team2_id if winner_team_id == duel.team1_id else duel.team1_id
    final_resp = test_client.post("/ping-pong/duel/answer", json={
        "duel_id": duel.id,
        "team_id": loser_team_id,
        "answer": "wrong answer",
    })
    assert final_resp.status_code == 200
    assert final_resp.json()["winner_team_id"] == winner_team_id

    db_session.refresh(sample_game_session)
    # Le duel de départage a été résolu automatiquement à sa fin, sans nouvel
    # appel à /next-question.
    assert sample_game_session.questions_played == questions_played_before
    assert sample_game_session.current_round == models.RoundType.MANCHE_2

    winner_team = db_session.query(models.Team).filter(models.Team.id == winner_team_id).first()
    # 70 + 2 (victoire du duel, règle standard PingPongManager) + 1 (départage)
    assert winner_team.score == 73
