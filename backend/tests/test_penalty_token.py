"""BUG-101b : la mise à jour du score sur PENALTY était un read-modify-write
non atomique (target_team.score = max(0, target_team.score - PENALTY_POINTS)
sur l'objet Python, écrit au commit). Deux PENALTY concurrentes visant la
même équipe cible pouvaient perdre une des deux pénalités — même défaut de
fond que BUG-101 (#3), appliqué ici à l'effet PENALTY plutôt qu'à la
consommation du jeton elle-même."""
import os
import tempfile
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import models
from app.database import Base, get_db
from main import app as main_app, PENALTY_POINTS


def test_penalty_token_reduces_target_team_score(test_client, db_session, sample_game_session):
    team = models.Team(name="Attacker", game_session_id=sample_game_session.id, score=0)
    target = models.Team(name="Victim", game_session_id=sample_game_session.id, score=5)
    db_session.add_all([team, target])
    db_session.commit()

    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.PENALTY, is_used=False))
    db_session.commit()

    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "PENALTY", "target_team_id": target.id},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 200
    assert resp.json()["penalized_teams"] == [{"team_id": target.id, "new_score": 3}]

    db_session.refresh(target)
    assert target.score == 3


def test_penalty_token_floors_score_at_zero(test_client, db_session, sample_game_session):
    team = models.Team(name="Attacker", game_session_id=sample_game_session.id, score=0)
    target = models.Team(name="Victim", game_session_id=sample_game_session.id, score=1)
    db_session.add_all([team, target])
    db_session.commit()

    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.PENALTY, is_used=False))
    db_session.commit()

    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "PENALTY", "target_team_id": target.id},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 200

    db_session.refresh(target)
    assert target.score == 0


def test_concurrent_penalties_on_same_target_both_apply():
    """Reproduit une vraie course : 2 équipes différentes pénalisent la même
    cible en simultané (threads distincts, connexions DB distinctes sur un
    fichier SQLite partagé). Les deux pénalités doivent être comptabilisées —
    avant le fix, un read-modify-write non atomique pouvait en perdre une."""
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
            code="PENALTYRACE", total_players=8, players_per_team=2,
            current_round=models.RoundType.MANCHE_1, is_active=True,
        )
        setup_db.add(game)
        setup_db.commit()
        setup_db.refresh(game)

        attacker1 = models.Team(name="Attacker 1", game_session_id=game.id, score=0)
        attacker2 = models.Team(name="Attacker 2", game_session_id=game.id, score=0)
        target = models.Team(name="Victim", game_session_id=game.id, score=10)
        setup_db.add_all([attacker1, attacker2, target])
        setup_db.commit()
        setup_db.refresh(attacker1)
        setup_db.refresh(attacker2)
        setup_db.refresh(target)

        setup_db.add(models.Token(team_id=attacker1.id, token_type=models.TokenType.PENALTY, is_used=False))
        setup_db.add(models.Token(team_id=attacker2.id, token_type=models.TokenType.PENALTY, is_used=False))
        setup_db.commit()

        attacker1_id, attacker2_id, target_id = attacker1.id, attacker2.id, target.id
        attacker1_token, attacker2_token = attacker1.team_token, attacker2.team_token
        setup_db.close()

        responses = []
        start_barrier = threading.Barrier(2)

        def fire(attacker_id, attacker_token):
            start_barrier.wait()  # force le chevauchement réel des 2 requêtes
            resp = client.post(
                "/tokens/use",
                json={"team_id": attacker_id, "token_type": "PENALTY", "target_team_id": target_id},
                headers={"X-Team-Token": attacker_token},
            )
            responses.append(resp)

        t1 = threading.Thread(target=fire, args=(attacker1_id, attacker1_token))
        t2 = threading.Thread(target=fire, args=(attacker2_id, attacker2_token))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(responses) == 2
        assert all(r.status_code == 200 for r in responses)

        check_db = SessionLocal()
        final_target = check_db.query(models.Team).filter(models.Team.id == target_id).first()
        assert final_target.score == 10 - 2 * PENALTY_POINTS
        check_db.close()
    finally:
        main_app.dependency_overrides.clear()
        engine.dispose()
        os.remove(db_path)
