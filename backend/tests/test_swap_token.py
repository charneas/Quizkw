"""Le jeton SWAP ne changeait jamais le thème d'un duel ping-pong en cours
(bug utilisateur) : use_token ne faisait que marquer le jeton comme utilisé,
sans aucun effet réel ni pour un duel, ni pour une question normale."""
import os
import tempfile
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import models
from app.database import Base, get_db
from main import app as main_app


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


def test_swap_token_rejected_once_already_used(test_client, db_session, sample_game_session, sample_questions_for_theme):
    """Un jeton déjà consommé ne peut plus redéclencher l'effet SWAP (garde
    applicative, complémentaire du test de concurrence réel ci-dessous)."""
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    sample_game_session.current_question_id = sample_questions_for_theme[0].id
    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.SWAP, is_used=False))
    db_session.commit()

    first = test_client.post("/tokens/use", json={"team_id": team.id, "token_type": "SWAP"})
    assert first.status_code == 200

    db_session.refresh(sample_game_session)
    question_after_first_swap = sample_game_session.current_question_id
    assert question_after_first_swap != sample_questions_for_theme[0].id

    again = test_client.post("/tokens/use", json={"team_id": team.id, "token_type": "SWAP"})
    assert again.status_code == 400

    db_session.refresh(sample_game_session)
    assert sample_game_session.current_question_id == question_after_first_swap


def test_token_consumption_survives_forced_concurrent_read():
    """Preuve déterministe du mécanisme qui corrige BUG-101 (indépendante du
    scheduling des threads, donc non flaky) : deux sessions DB distinctes
    lisent TOUTES LES DEUX le jeton comme disponible avant qu'aucune n'écrive
    — une vraie course, forcée explicitement plutôt qu'espérée via un thread
    barrier. Avec l'ancien code (`chosen_token.is_used = True` sur l'objet
    Python puis commit, sans condition WHERE au moment de l'écriture), les
    deux sessions auraient réussi à "consommer" le jeton et déclenché
    l'effet SWAP en cascade. Avec le fix (UPDATE ... WHERE id=... AND
    is_used=False), seule l'une des deux peut effectivement modifier la
    ligne — l'autre obtient rowcount=0."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    setup_db = SessionLocal()
    game = models.GameSession(
        code="DETERM01", total_players=8, players_per_team=2,
        current_round=models.RoundType.MANCHE_1, is_active=True,
    )
    setup_db.add(game)
    setup_db.commit()
    setup_db.refresh(game)

    team = models.Team(name="Team A", game_session_id=game.id, score=0)
    setup_db.add(team)
    setup_db.commit()
    setup_db.refresh(team)

    token = models.Token(team_id=team.id, token_type=models.TokenType.SWAP, is_used=False)
    setup_db.add(token)
    setup_db.commit()
    setup_db.refresh(token)
    token_id = token.id
    setup_db.close()

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        # Les deux sessions lisent le jeton comme disponible AVANT toute
        # écriture : c'est exactement la fenêtre de course qui causait BUG-101.
        candidate_a = session_a.query(models.Token).filter(
            models.Token.id == token_id, models.Token.is_used == False
        ).first()
        candidate_b = session_b.query(models.Token).filter(
            models.Token.id == token_id, models.Token.is_used == False
        ).first()
        assert candidate_a is not None
        assert candidate_b is not None

        rows_a = session_a.query(models.Token).filter(
            models.Token.id == token_id, models.Token.is_used == False
        ).update({"is_used": True}, synchronize_session=False)
        session_a.commit()

        rows_b = session_b.query(models.Token).filter(
            models.Token.id == token_id, models.Token.is_used == False
        ).update({"is_used": True}, synchronize_session=False)
        session_b.commit()

        # Une seule des deux écritures a effectivement modifié une ligne.
        assert {rows_a, rows_b} == {0, 1}

        check_db = SessionLocal()
        assert check_db.query(models.Token).filter(models.Token.id == token_id).first().is_used is True
        check_db.close()
    finally:
        session_a.close()
        session_b.close()
        engine.dispose()
        os.remove(db_path)


def test_concurrent_swap_requests_fire_only_once():
    """BUG-101 : "swaps infinis" en playtest — un enchaînement de swaps se
    déclenchait en boucle sans jamais se stabiliser. Cause : use_token lisait
    le jeton disponible (SELECT is_used=False) puis l'écrivait (is_used=True)
    dans deux étapes séparées ; deux requêtes concurrentes sur le même jeton
    (ex. deux coéquipiers cliquant SWAP au même moment) pouvaient toutes les
    deux le lire comme disponible avant que l'une ne commite, et donc
    déclencher l'effet du jeton en cascade. Le fix consomme le jeton via un
    UPDATE conditionnel (WHERE id=... AND is_used=False) : l'UPDATE lui-même
    sérialise les écritures concurrentes, une seule des deux requêtes peut
    modifier la ligne.

    Reproduit une vraie course : 2 requêtes HTTP simultanées (threads
    distincts, connexions DB distinctes sur un fichier SQLite partagé), sur
    le modèle de test_team_answer_convergence.test_concurrent_submissions_never_duplicate_rows
    — un simple SELECT-puis-écriture ne serait pas serialisé par SQLite ici
    (contrairement à `with_for_update()`, qui est un no-op silencieux sur
    SQLite et ne l'aurait pas détecté)."""
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
            code="SWAPRACE", total_players=8, players_per_team=2,
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

        question1 = models.Question(
            text="Capitale ?", category="Geography", difficulty=models.Difficulty.EASY,
            points=2, correct_answer="Paris", wrong_answers='["a", "b", "c"]',
            theme_id=theme.id, question_number=1,
        )
        question2 = models.Question(
            text="Fleuve ?", category="Geography", difficulty=models.Difficulty.EASY,
            points=2, correct_answer="Loire", wrong_answers='["a", "b", "c"]',
            theme_id=theme.id, question_number=2,
        )
        setup_db.add_all([question1, question2])
        setup_db.commit()
        setup_db.refresh(question1)

        game.current_question_id = question1.id
        setup_db.add(models.Token(team_id=team.id, token_type=models.TokenType.SWAP, is_used=False))
        setup_db.commit()
        team_id = team.id
        setup_db.close()

        responses = []
        start_barrier = threading.Barrier(2)

        def fire():
            start_barrier.wait()  # force le chevauchement réel des 2 requêtes
            resp = client.post("/tokens/use", json={"team_id": team_id, "token_type": "SWAP"})
            responses.append(resp)

        t1 = threading.Thread(target=fire)
        t2 = threading.Thread(target=fire)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        statuses = sorted(r.status_code for r in responses)
        assert statuses == [200, 400]

        check_db = SessionLocal()
        tokens = check_db.query(models.Token).filter(models.Token.team_id == team_id).all()
        assert len(tokens) == 1
        assert tokens[0].is_used is True
        check_db.close()
    finally:
        main_app.dependency_overrides.clear()
        engine.dispose()
        os.remove(db_path)


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
