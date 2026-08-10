"""BUG-110 : les 2 joueurs d'une équipe partagent une seule réponse. Chacun
peut la corriger tant que l'host n'a pas validé ; la dernière soumission
avant validation est celle retenue pour le score.

Note : /answers/ ne révèle plus is_correct/correct_answer tant que la
réponse n'est pas verrouillée (validée par l'host) — la soumission étant
rejouable à volonté par n'importe quel client non authentifié, les renvoyer
aurait constitué un oracle permettant de deviner la bonne réponse par essais
successifs. On vérifie donc l'état réel via la base et /validate-answers."""
import os
import tempfile
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import models
from app.database import Base, get_db
from main import app as main_app


def _submit(test_client, question_id, team_id, player_answer):
    return test_client.post("/answers/", json={
        "question_id": question_id,
        "team_id": team_id,
        "player_answer": player_answer,
    })


def test_last_answer_before_validation_wins(test_client, db_session, sample_game_session, sample_team, sample_question):
    sample_game_session.current_question_id = sample_question.id
    db_session.commit()

    # Joueur A répond faux, puis joueur B (même équipe) corrige avec la bonne réponse.
    resp_a = _submit(test_client, sample_question.id, sample_team.id, "mauvaise réponse")
    assert resp_a.status_code == 200
    assert resp_a.json()["pending_validation"] is True
    assert resp_a.json()["is_correct"] is None  # pas encore verrouillée : pas d'oracle

    resp_b = _submit(test_client, sample_question.id, sample_team.id, sample_question.correct_answer)
    assert resp_b.status_code == 200

    # Une seule ligne Answer doit exister pour ce couple (question, équipe),
    # et c'est bien la dernière réponse (celle de B) qui est retenue.
    answers = db_session.query(models.Answer).filter(
        models.Answer.question_id == sample_question.id,
        models.Answer.team_id == sample_team.id,
    ).all()
    assert len(answers) == 1
    assert answers[0].player_answer == sample_question.correct_answer
    assert answers[0].is_correct is True

    validate_resp = test_client.post(
        f"/games/{sample_game_session.code}/validate-answers",
        headers={"X-Host-Token": sample_game_session.host_token},
    )
    assert validate_resp.status_code == 200
    team_result = next(t for t in validate_resp.json()["teams_updated"] if t["team_id"] == sample_team.id)
    assert team_result["is_correct"] is True
    assert team_result["points_earned"] == sample_question.points

    db_session.refresh(sample_team)
    assert sample_team.score == sample_question.points


def test_validate_answers_exposes_player_answer_text(test_client, db_session, sample_game_session, sample_team, sample_question):
    """Item misc playtest 2026-07-31 : voir les réponses des autres équipes au
    reveal, pas juste correct/incorrect."""
    sample_game_session.current_question_id = sample_question.id
    db_session.commit()

    _submit(test_client, sample_question.id, sample_team.id, "Une réponse loufoque")

    validate_resp = test_client.post(
        f"/games/{sample_game_session.code}/validate-answers",
        headers={"X-Host-Token": sample_game_session.host_token},
    )
    assert validate_resp.status_code == 200
    team_result = next(t for t in validate_resp.json()["teams_updated"] if t["team_id"] == sample_team.id)
    assert team_result["player_answer"] == "Une réponse loufoque"

    # Côté équipe (TeamScreen), le même texte doit ressortir via l'état d'équipe
    # une fois la question courante effacée par validate-answers (BUG #50).
    state_resp = test_client.get(f"/game/{sample_game_session.code}/team/{sample_team.id}/state")
    assert state_resp.status_code == 200
    validation_result = state_resp.json()["validation_result"]
    team_entry = next(t for t in validation_result["teams"] if t["team_name"] == sample_team.name)
    assert team_entry["player_answer"] == "Une réponse loufoque"


def test_empty_or_blank_answer_rejected(test_client, sample_game_session, sample_team, sample_question):
    sample_game_session.current_question_id = sample_question.id
    assert _submit(test_client, sample_question.id, sample_team.id, "").status_code == 422
    assert _submit(test_client, sample_question.id, sample_team.id, "   ").status_code == 422


def test_answer_locked_after_host_validation(test_client, db_session, sample_game_session, sample_team, sample_question):
    sample_game_session.current_question_id = sample_question.id
    db_session.commit()

    _submit(test_client, sample_question.id, sample_team.id, sample_question.correct_answer)

    test_client.post(
        f"/games/{sample_game_session.code}/validate-answers",
        headers={"X-Host-Token": sample_game_session.host_token},
    )
    db_session.refresh(sample_team)
    score_after_validation = sample_team.score

    # Un joueur retardataire ne peut plus changer la réponse une fois validée ;
    # la réponse verrouillée révèle maintenant is_correct (plus d'oracle possible
    # puisqu'elle ne peut plus changer).
    late_resp = _submit(test_client, sample_question.id, sample_team.id, "mauvaise réponse")
    assert late_resp.status_code == 200
    assert late_resp.json()["is_correct"] is True
    assert late_resp.json()["pending_validation"] is False

    answers = db_session.query(models.Answer).filter(
        models.Answer.question_id == sample_question.id,
        models.Answer.team_id == sample_team.id,
    ).all()
    assert len(answers) == 1
    assert answers[0].player_answer == sample_question.correct_answer

    db_session.refresh(sample_team)
    assert sample_team.score == score_after_validation


def test_concurrent_submissions_never_duplicate_rows():
    """Reproduit une vraie course : 2 requêtes HTTP simultanées (threads
    distincts, connexions DB distinctes sur un fichier SQLite partagé) pour
    les 2 coéquipiers. L'upsert atomique (INSERT ... ON CONFLICT DO UPDATE)
    doit garantir qu'une seule ligne Answer survit, quel que soit l'ordre
    d'arrivée réel — contrairement à un schéma SELECT-puis-INSERT qui a une
    fenêtre de course entre les 2 requêtes concurrentes."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main_app)

    try:
        setup_db = SessionLocal()
        game = models.GameSession(
            code="RACE123", total_players=8, players_per_team=2,
            current_round=models.RoundType.MANCHE_1, is_active=True,
        )
        setup_db.add(game)
        setup_db.commit()
        setup_db.refresh(game)

        team = models.Team(name="Race Team", game_session_id=game.id, score=0)
        setup_db.add(team)
        setup_db.commit()
        setup_db.refresh(team)

        theme = models.Theme(name="Theme", category=models.ThemeCategory.SERIOUS, difficulty_level=1, description="d")
        setup_db.add(theme)
        setup_db.commit()
        setup_db.refresh(theme)

        question = models.Question(
            text="Capitale ?", category="Geography", difficulty=models.Difficulty.EASY,
            points=2, correct_answer="Paris", wrong_answers='["a", "b", "c"]',
            theme_id=theme.id, question_number=1,
        )
        setup_db.add(question)
        setup_db.commit()
        setup_db.refresh(question)

        game.current_question_id = question.id
        setup_db.commit()
        team_id, question_id = team.id, question.id
        setup_db.close()

        responses = []
        start_barrier = threading.Barrier(2)

        def submit(player_answer):
            start_barrier.wait()  # force le chevauchement réel des 2 requêtes
            resp = client.post("/answers/", json={
                "question_id": question_id,
                "team_id": team_id,
                "player_answer": player_answer,
            })
            responses.append(resp)

        t1 = threading.Thread(target=submit, args=("mauvaise réponse",))
        t2 = threading.Thread(target=submit, args=("Paris",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(r.status_code == 200 for r in responses)

        check_db = SessionLocal()
        answers = check_db.query(models.Answer).filter(
            models.Answer.question_id == question_id,
            models.Answer.team_id == team_id,
        ).all()
        assert len(answers) == 1
        check_db.close()
    finally:
        main_app.dependency_overrides.clear()
        engine.dispose()
        os.remove(db_path)
