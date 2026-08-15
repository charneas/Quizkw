"""BUG-101h : start_duel faisait un SELECT (duel actif existant ?) puis,
si rien trouvé, un INSERT séparé — deux requêtes concurrentes de démarrage
de duel impliquant la même équipe pouvaient toutes les deux passer le SELECT
avant qu'aucune n'ait commité, créant 2 duels actifs malgré la garde
(même défaut de fond que #3/#53, ici appliqué à la création de duel).
Reproduit une vraie course avec des connexions DB distinctes (comme
test_concurrent_submissions_never_duplicate_rows), pas seulement un
enchaînement séquentiel qui ne prouve rien sur la concurrence réelle."""
import os
import tempfile
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import models
from app.database import Base, get_db
from main import app as main_app


def test_concurrent_duel_starts_for_same_team_never_create_two_active_duels():
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
            code="DUELRACE", total_players=8, players_per_team=2,
            current_round=models.RoundType.MANCHE_1, is_active=True,
        )
        setup_db.add(game)
        setup_db.commit()
        setup_db.refresh(game)

        team1 = models.Team(name="Team A", game_session_id=game.id, score=0)
        team2 = models.Team(name="Team B", game_session_id=game.id, score=0)
        team3 = models.Team(name="Team C", game_session_id=game.id, score=0)
        setup_db.add_all([team1, team2, team3])
        setup_db.commit()
        setup_db.refresh(team1)
        setup_db.refresh(team2)
        setup_db.refresh(team3)

        theme = models.PingPongTheme(title="Capitales", correct_answers=["Paris"])
        setup_db.add(theme)
        setup_db.commit()
        setup_db.refresh(theme)

        game_id, host_token, team1_id, team2_id, team3_id, theme_id = (
            game.id, game.host_token, team1.id, team2.id, team3.id, theme.id
        )
        setup_db.close()

        responses = []
        start_barrier = threading.Barrier(2)

        def start_duel(team_a, team_b):
            start_barrier.wait()  # force le chevauchement réel des 2 requêtes
            resp = client.post("/ping-pong/duel/start", json={
                "game_session_id": game_id,
                "theme_id": theme_id,
                "team1_id": team_a,
                "team2_id": team_b,
            }, headers={"X-Host-Token": host_token})
            responses.append(resp)

        # team1 est commune aux deux tentatives : au plus une doit réussir.
        t1 = threading.Thread(target=start_duel, args=(team1_id, team2_id))
        t2 = threading.Thread(target=start_duel, args=(team3_id, team1_id))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        status_codes = sorted(r.status_code for r in responses)
        assert status_codes == [200, 400], (
            f"attendu exactement 1 succès et 1 refus, obtenu {status_codes}"
        )

        check_db = SessionLocal()
        active_duels = check_db.query(models.PingPongDuel).filter(
            models.PingPongDuel.game_session_id == game_id,
            models.PingPongDuel.is_completed == False,
        ).all()
        assert len(active_duels) == 1
        check_db.close()
    finally:
        main_app.dependency_overrides.clear()
        engine.dispose()
        os.remove(db_path)