"""BUG-101e : Team.score est touché par plusieurs chemins indépendants
(validation de réponse, jeton PENALTY déjà atomique depuis #53, effets de
roue, victoire de duel ping-pong). Avant ce fix, seul le chemin PENALTY
utilisait une mise à jour atomique (UPDATE ... SET score = CASE ...) ; les
autres faisaient un read-modify-write Python (`team.score += x`) qui pouvait
perdre silencieusement une pénalité arrivée entre-temps sur la même équipe.
Reproduit une vraie course (2 connexions DB distinctes, threading.Barrier),
comme test_concurrent_penalties_on_same_target_both_apply, mais entre deux
chemins DIFFÉRENTS plutôt que deux fois le même."""
import os
import tempfile
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import models
from app.database import Base, get_db
from main import app as main_app


def test_concurrent_penalty_and_answer_validation_on_same_team_both_apply():
    """Une équipe répond correctement pendant qu'une équipe adverse lui
    inflige une PENALTY au même instant : les deux mouvements de score
    doivent être comptabilisés, aucun ne doit silencieusement écraser
    l'autre."""
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
            code="SCORERACE", total_players=8, players_per_team=2,
            current_round=models.RoundType.MANCHE_1, is_active=True,
            host_token="host-token-race",
        )
        setup_db.add(game)
        setup_db.commit()
        setup_db.refresh(game)

        target = models.Team(name="Target", game_session_id=game.id, score=10)
        attacker = models.Team(name="Attacker", game_session_id=game.id, score=0)
        setup_db.add_all([target, attacker])
        setup_db.commit()
        setup_db.refresh(target)
        setup_db.refresh(attacker)

        setup_db.add(models.Token(team_id=attacker.id, token_type=models.TokenType.PENALTY, is_used=False))

        theme = models.Theme(name="Theme", category=models.ThemeCategory.SERIOUS, difficulty_level=1, description="d")
        setup_db.add(theme)
        setup_db.commit()
        setup_db.refresh(theme)

        question = models.Question(
            text="Capitale ?", category="Geography", difficulty=models.Difficulty.EASY,
            points=6, correct_answer="Paris", wrong_answers='["a", "b", "c"]',
            theme_id=theme.id, question_number=1,
        )
        setup_db.add(question)
        setup_db.commit()
        setup_db.refresh(question)

        game.current_question_id = question.id
        setup_db.commit()

        # Réponse déjà soumise (correcte), il ne reste que la validation host
        # à déclencher en même temps que la PENALTY.
        answer = models.Answer(
            question_id=question.id, team_id=target.id,
            player_answer="Paris", is_correct=True, points_earned=0,
        )
        setup_db.add(answer)
        setup_db.commit()

        game_code, host_token = game.code, game.host_token
        target_id, attacker_id, attacker_token = target.id, attacker.id, attacker.team_token
        setup_db.close()

        responses = []
        start_barrier = threading.Barrier(2)

        def validate():
            start_barrier.wait()
            resp = client.post(
                f"/games/{game_code}/validate-answers",
                headers={"X-Host-Token": host_token},
            )
            responses.append(("validate", resp))

        def penalize():
            start_barrier.wait()
            resp = client.post(
                "/tokens/use",
                json={"team_id": attacker_id, "token_type": "PENALTY", "target_team_id": target_id},
                headers={"X-Team-Token": attacker_token},
            )
            responses.append(("penalty", resp))

        t1 = threading.Thread(target=validate)
        t2 = threading.Thread(target=penalize)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        for label, resp in responses:
            assert resp.status_code == 200, f"{label} a échoué : {resp.status_code} {resp.text}"

        check_db = SessionLocal()
        final_target = check_db.query(models.Team).filter(models.Team.id == target_id).first()
        # Score initial 10, +6 points de la question (question.points=6, pas
        # de bonus actif), -2 de la pénalité : 10 + 6 - 2 = 14. Si l'une des
        # deux écritures avait été perdue, on obtiendrait 16 (pénalité
        # écrasée) ou 8 (validation écrasée) au lieu de 14.
        assert final_target.score == 14
        check_db.close()
    finally:
        main_app.dependency_overrides.clear()
        engine.dispose()
        os.remove(db_path)