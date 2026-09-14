"""Tests de la Story 2.1 (lobby et connexion à une partie de blind test) —
matrice I/O de `spec-2-1-lobby-connexion-partie.md`.

Utilise sa propre DB SQLite en mémoire (mirroir de
`test_blindtest_import.py`) pour exercer l'isolation AD-7 de bout en bout,
et remet à zéro le `ConnectionManager` en mémoire entre chaque test (state
module-level, cf. `app/blindtest/game_connections.py`).
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.blindtest.database import Base, get_db
from app.blindtest.game_connections import guess_store, played_tracks_store, score_store
from app.blindtest.game_connections import manager as connection_manager
from main import app as main_app


@pytest.fixture
def blindtest_engine(tmp_path):
    # Story 2.6 (revue de code) : un fichier SQLite réel sous `tmp_path`
    # plutôt qu'un `:memory:` partagé via `StaticPool`. Les connexions WS de
    # ce fichier de tests tournent chacune sur son propre thread OS réel
    # (chaque `websocket_connect()` de `starlette.testclient` ouvre son
    # propre portail/thread tant que le `TestClient` n'est pas utilisé en
    # `with`) ; `StaticPool` forçait plusieurs `Session` SQLAlchemy
    # indépendantes à partager UNE seule connexion DBAPI sqlite3 brute entre
    # ces threads, ce qui corrompait sporadiquement l'état de session de
    # SQLAlchemy sous écriture concurrente réelle (minuteur de round vs
    # clôture anticipée d'un autre joueur) — observé en boucle comme
    # `InvalidRequestError: Could not refresh instance`. Un fichier réel
    # donne une connexion DBAPI distincte par session/thread (pool normal),
    # avec le verrouillage natif de SQLite (+ `busy_timeout`, même rationale
    # que `app/blindtest/database.py`) pour sérialiser les écritures — ce
    # qui reflète aussi fidèlement la prod (fichier `blindtest.db`), jamais
    # un `:memory:`.
    db_path = tmp_path / "blindtest_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_busy_timeout(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def blindtest_client(blindtest_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=blindtest_engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main_app)
    yield client
    main_app.dependency_overrides.clear()
    connection_manager._games.clear()
    guess_store._guesses.clear()
    score_store._scores.clear()
    played_tracks_store._played.clear()


def _create_game(client) -> str:
    resp = client.post("/blindtest/games")
    assert resp.status_code == 201
    return resp.json()["code"]


class TestCreateGame:
    def test_create_returns_201_with_id_and_unique_code(self, blindtest_client):
        resp = blindtest_client.post("/blindtest/games")
        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data["id"], int)
        assert len(data["code"]) == 6

    def test_create_persists_game_row_with_lobby_phase(self, blindtest_client, blindtest_engine):
        blindtest_client.post("/blindtest/games")
        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text("SELECT phase FROM games")).fetchone()
        assert row[0] == "lobby"


class TestJoinValidCode:
    def test_join_accepted_and_receives_game_state(self, blindtest_client):
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws:
            ws.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            msg = ws.receive_json()
            assert msg["type"] == "game_state"
            assert msg["payload"]["players"] == ["Alice"]
            assert "ts" in msg

    def test_first_joiner_becomes_host(self, blindtest_client):
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            msg1 = ws1.receive_json()
            assert msg1["payload"]["host_pseudo"] == "Alice"
            assert msg1["payload"]["phase"] == "lobby"

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                msg2 = ws2.receive_json()
                # Le second joueur ne devient jamais l'hôte : la colonne
                # n'est assignée qu'une fois, au tout premier joueur.
                assert msg2["payload"]["host_pseudo"] == "Alice"

    def test_join_case_insensitive_code(self, blindtest_client):
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code.lower()}/ws") as ws:
            ws.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            msg = ws.receive_json()
            assert msg["payload"]["players"] == ["Alice"]

    def test_second_join_broadcasts_updated_roster_to_both(self, blindtest_client):
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()  # game_state avec juste Alice

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                msg2 = ws2.receive_json()
                assert sorted(msg2["payload"]["players"]) == ["Alice", "Bob"]

                # Alice reçoit aussi la mise à jour
                msg1 = ws1.receive_json()
                assert sorted(msg1["payload"]["players"]) == ["Alice", "Bob"]


class TestJoinUnknownCode:
    def test_unknown_code_closes_immediately(self, blindtest_client):
        from starlette.websockets import WebSocketDisconnect

        # Le handshake est désormais accepté avant la fermeture (nécessaire
        # pour que le code de fermeture survive au vrai transport ASGI
        # d'uvicorn — cf. commentaire dans `game_lobby_ws`), donc
        # `websocket_connect` réussit son `__enter__` sans lever ; c'est en
        # essayant de lire quelque chose sur le socket qu'on observe la
        # fermeture avec le code custom.
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with blindtest_client.websocket_connect("/blindtest/games/ZZZZZZ/ws") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4404


class TestJoinInvalidPseudo:
    def test_empty_pseudo_closes_with_custom_code(self, blindtest_client):
        from starlette.websockets import WebSocketDisconnect

        code = _create_game(blindtest_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws:
                ws.send_json({"type": "join", "payload": {"pseudo": ""}})
                ws.receive_json()
        assert exc_info.value.code == 4400

    def test_missing_pseudo_closes_with_custom_code(self, blindtest_client):
        from starlette.websockets import WebSocketDisconnect

        code = _create_game(blindtest_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws:
                ws.send_json({"type": "join", "payload": {}})
                ws.receive_json()
        assert exc_info.value.code == 4400

    def test_pseudo_too_long_closes_with_custom_code(self, blindtest_client):
        from starlette.websockets import WebSocketDisconnect

        code = _create_game(blindtest_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws:
                ws.send_json({"type": "join", "payload": {"pseudo": "A" * 31}})
                ws.receive_json()
        assert exc_info.value.code == 4400


class TestDuplicatePseudo:
    def test_duplicate_pseudo_closes_second_socket_first_unaffected(self, blindtest_client):
        from starlette.websockets import WebSocketDisconnect

        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with pytest.raises(WebSocketDisconnect) as exc_info:
                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                    ws2.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
                    ws2.receive_json()
            assert exc_info.value.code == 4409

            # La première Alice n'est pas affectée : peut encore recevoir/pas
            # de fermeture. On vérifie via un nouveau joueur qui déclenche un
            # broadcast et confirme que ws1 est toujours dans le roster.
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                ws3.receive_json()
                msg1 = ws1.receive_json()
                assert sorted(msg1["payload"]["players"]) == ["Alice", "Carol"]


class TestDisconnect:
    def test_disconnect_removes_from_roster_and_broadcasts(self, blindtest_client):
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()  # Alice voit Bob arriver

            # ws2 (Bob) fermé en sortant du `with` -> Alice reçoit un roster à jour
            msg1 = ws1.receive_json()
            assert msg1["payload"]["players"] == ["Alice"]

    def test_non_host_disconnect_does_not_reassign_host(self, blindtest_client):
        """Story 7 : seul le départ de l'hôte doit déclencher une
        réassignation — un non-hôte qui part ne doit rien changer."""
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

            # Bob (non-hôte) part -> Alice reste hôte.
            msg1 = ws1.receive_json()
            assert msg1["payload"]["host_pseudo"] == "Alice"

    def test_host_disconnect_reassigns_to_remaining_player(self, blindtest_client):
        """Story 7 : l'hôte qui part transfère son statut au premier joueur
        encore connecté, sans bloquer la partie.

        Bob ouvre son socket EN PREMIER (bloc `with` extérieur) mais envoie
        son `join` APRÈS Alice -- l'ordre d'imbrication des `with` contrôle
        l'ORDRE DE FERMETURE (le bloc intérieur se ferme en premier), pas
        l'ordre des messages. Ça permet de fermer le socket d'Alice (hôte)
        pendant que celui de Bob reste ouvert, sans appel `.close()` manuel
        (source du hang observé en tentant cette approche)."""
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
                ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
                ws1.receive_json()

                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

            # Sortie du bloc intérieur -> le socket d'Alice (hôte) se ferme,
            # celui de Bob reste ouvert.
            msg2 = ws2.receive_json()
            assert msg2["payload"]["host_pseudo"] == "Bob"
            assert msg2["payload"]["players"] == ["Bob"]

    def test_last_player_disconnect_leaves_stale_host_with_no_one_to_reassign(self, blindtest_client):
        """Story 7 : si l'hôte part alors que plus personne n'est connecté,
        rien à réassigner -- host_pseudo reste tel quel (partie abandonnée,
        pas de broadcast à personne)."""
        code = _create_game(blindtest_client)
        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()
        # Aucune exception à la fermeture du dernier socket -- c'est tout ce
        # que ce cas peut vérifier (aucun autre client à qui broadcaster).


def _add_track(engine, game_code: str, *, youtube_video_id="abc123", duration_seconds=100, owner_pseudo="Alice") -> None:
    """Insère directement une `Playlist`+`Track` scopées à `game_code`, sans
    passer par le pipeline d'import (hors scope de cette story) — juste ce
    qu'il faut pour rendre un morceau éligible (ou non) au tirage de round.

    `owner_pseudo` (Story 2.6) était jusqu'ici toujours "Alice" en dur —
    rendu surchargeable pour les tests de reveal/score qui ont besoin d'un
    propriétaire distinct de l'hôte."""
    from app.blindtest.models import Game, Playlist, Track

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.code == game_code).first()
        playlist = Playlist(source_url="https://example.com", provider="youtube", game_id=game.id, owner_pseudo=owner_pseudo)
        db.add(playlist)
        db.flush()
        db.add(Track(
            playlist_id=playlist.id,
            title="Titre",
            artist="Artiste",
            youtube_video_id=youtube_video_id,
            duration_seconds=duration_seconds,
        ))
        db.commit()
    finally:
        db.close()


class TestStartGame:
    def test_host_starts_with_eligible_pot_draws_and_broadcasts(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()  # game_state, Alice devient hôte

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()  # game_state pour Bob
                ws1.receive_json()  # game_state (roster à jour) pour Alice

                ws1.send_json({"type": "start_game", "payload": {}})

                # Revue de code : `start_game` diffuse désormais aussi
                # `game_state {phase: "round_started"}` (seul canal par
                # lequel le client met à jour `phase`) juste avant le
                # `round_started` lui-même.
                state1 = ws1.receive_json()
                state2 = ws2.receive_json()
                for state in (state1, state2):
                    assert state["type"] == "game_state"
                    assert state["payload"]["phase"] == "round_started"

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                for msg in (msg1, msg2):
                    assert msg["type"] == "round_started"
                    assert msg["payload"]["videoId"] == "abc123"
                    assert 0 <= msg["payload"]["startSeconds"] < 100
                    assert msg["payload"]["title"] == "Titre"
                    assert msg["payload"]["artist"] == "Artiste"

    def test_non_host_start_game_is_silently_ignored(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws2.send_json({"type": "start_game", "payload": {}})

                # Rien ne doit arriver suite à ce message : on le vérifie en
                # provoquant un nouveau broadcast (une 3e connexion) et en
                # confirmant que la partie est toujours en phase lobby.
                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    msg3 = ws3.receive_json()
                    assert msg3["payload"]["phase"] == "lobby"

    def test_empty_pot_is_silently_ignored(self, blindtest_client):
        code = _create_game(blindtest_client)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            ws1.send_json({"type": "start_game", "payload": {}})

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                msg2 = ws2.receive_json()
                assert msg2["payload"]["phase"] == "lobby"

    def test_has_unplayed_track_ignores_connection_state(self, blindtest_client, blindtest_engine):
        """Story 8 (revue de code) : `_has_unplayed_track` (utilisé par
        `_advance_round` pour distinguer pot réellement épuisé vs
        temporairement vide) doit voir Bob comme "a un morceau non-joué"
        même quand il n'est PAS connecté -- c'est tout son but, à l'inverse
        de `_draw_eligible_track`."""
        import main_blindtest
        from app.blindtest.models import Game

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Bob")

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=blindtest_engine)
        db = SessionLocal()
        try:
            game = db.query(Game).filter(Game.code == code).first()
            # Bob n'a jamais rejoint le lobby WS -- `_draw_eligible_track`
            # (avec filtre de connexion) le voit comme inéligible...
            assert main_blindtest._draw_eligible_track(db, game) is None
            # ...mais `_has_unplayed_track` (sans ce filtre) le voit quand
            # même comme un morceau non-joué existant.
            assert main_blindtest._has_unplayed_track(db, game) is True
        finally:
            db.close()

    def test_disconnected_owner_pool_shrinks_others_stay_drawable(self, blindtest_client, blindtest_engine):
        """Story 8 : Bob se déconnecte alors qu'Alice a elle aussi un morceau
        dans le pot -- le pot rétrécit (le morceau de Bob n'est plus tirable)
        mais celui d'Alice reste éligible, la partie continue normalement.
        Scénario plus représentatif que le pot à un seul propriétaire."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, youtube_video_id="alice-track", owner_pseudo="Alice")
        _add_track(blindtest_engine, code, youtube_video_id="bob-track", owner_pseudo="Bob")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws_bob:
                ws_bob.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws_bob.receive_json()
                ws1.receive_json()  # Alice voit Bob arriver
            ws1.receive_json()  # Alice voit Bob repartir (Bob déconnecté)

            ws1.send_json({"type": "start_game", "payload": {}})
            state1 = ws1.receive_json()  # game_state {phase: round_started}
            assert state1["payload"]["phase"] == "round_started"
            round1 = ws1.receive_json()
            assert round1["type"] == "round_started"
            # Seul le morceau d'Alice (toujours connectée) peut être tiré.
            assert round1["payload"]["videoId"] == "alice-track"

    def test_disconnected_owners_track_is_not_drawable(self, blindtest_client, blindtest_engine):
        """Story 8 (spec-blindtest-integration-ui, CAP-7) : le seul morceau du
        pot appartient à Bob, qui n'est jamais connecté -- le tirage doit se
        comporter comme un pot vide (aucun round ne démarre)."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Bob")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            ws1.send_json({"type": "start_game", "payload": {}})

            # Même vérification que test_empty_pot_is_silently_ignored : un
            # nouveau joignant doit voir la partie toujours en `lobby`.
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                msg2 = ws2.receive_json()
                assert msg2["payload"]["phase"] == "lobby"

    def test_reconnected_owners_track_becomes_drawable_again(self, blindtest_client, blindtest_engine):
        """Story 8 (CAP-8, nice-to-have) : le morceau de Bob redevient tirable
        dès qu'il se reconnecte, sans action explicite de "réintégration"."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Bob")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            # Bob rejoint puis repart aussitôt -- son morceau redevient
            # inéligible (couvert par le test précédent), avant de revenir.
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws_bob_gone:
                ws_bob_gone.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws_bob_gone.receive_json()
                ws1.receive_json()  # Alice voit Bob arriver
            ws1.receive_json()  # Alice voit Bob repartir

            # Bob se reconnecte -- son morceau redevient éligible.
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws_bob_back:
                ws_bob_back.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws_bob_back.receive_json()
                ws1.receive_json()  # Alice voit Bob revenir

                ws1.send_json({"type": "start_game", "payload": {}})
                state1 = ws1.receive_json()  # game_state {phase: round_started}
                assert state1["payload"]["phase"] == "round_started"
                round1 = ws1.receive_json()
                assert round1["type"] == "round_started"
                assert round1["payload"]["videoId"] == "abc123"

    def test_duplicate_start_is_a_noop(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            ws1.send_json({"type": "start_game", "payload": {}})
            first_state = ws1.receive_json()  # game_state {phase: round_started}
            assert first_state["type"] == "game_state"
            first = ws1.receive_json()
            assert first["type"] == "round_started"

            ws1.send_json({"type": "start_game", "payload": {}})

            # Aucun nouveau `round_started` : on le confirme via un nouveau
            # joignant, dont le `game_state` doit rester en `round_started`
            # (pas de second tirage qui aurait pu changer le morceau/offset).
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                msg2 = ws2.receive_json()
                assert msg2["payload"]["phase"] == "round_started"

    def test_round_started_game_state_carries_scores(self, blindtest_client, blindtest_engine):
        """Story 4 (spec-blindtest-integration-ui) : le `game_state` de
        `round_started` doit désormais porter `scores` (le scoreboard doit
        rester visible pendant tout le round, pas seulement au reveal/ended)."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            ws1.send_json({"type": "start_game", "payload": {}})
            state = ws1.receive_json()  # game_state {phase: round_started}
            assert state["type"] == "game_state"
            assert state["payload"]["phase"] == "round_started"

            gid = _game_id(blindtest_engine, code)
            assert state["payload"]["scores"] == score_store.snapshot(gid)

    def test_disconnect_after_round_started_rebroadcasts_current_phase(self, blindtest_client, blindtest_engine):
        """Régression (revue de code) : le `finally` du handler WS lisait un
        objet `Game` ORM chargé une seule fois à la connexion, jamais
        rafraîchi — si un round démarrait via une *autre* connexion pendant
        la vie de ce socket, sa déconnexion rediffusait un `phase: "lobby"`
        périmé à tous les clients restants, malgré la vraie phase déjà
        passée en `round_started`."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()  # game_state, Alice devient hôte

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()  # game_state pour Bob
                ws1.receive_json()  # game_state (roster à jour) pour Alice

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started} pour Alice
                ws1.receive_json()  # round_started pour Alice
                ws2.receive_json()  # game_state {phase: round_started} pour Bob
                ws2.receive_json()  # round_started pour Bob

                # Bob (ws2, une connexion distincte de celle qui a démarré le
                # round) se déconnecte ici, en sortant du `with`. Le `finally`
                # de son handler doit refléter la vraie phase courante, pas
                # celle vue à sa connexion (avant le `start_game`).

            # Une nouvelle connexion observe l'état après la déconnexion de
            # Bob : la phase doit toujours être `round_started`.
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                msg3 = ws3.receive_json()
                assert msg3["payload"]["phase"] == "round_started"

    def test_same_track_different_games_different_start_seconds(self, blindtest_client, blindtest_engine):
        code_x = _create_game(blindtest_client)
        code_y = _create_game(blindtest_client)
        _add_track(blindtest_engine, code_x, duration_seconds=10_000)
        _add_track(blindtest_engine, code_y, duration_seconds=10_000)

        starts = []
        for code in (code_x, code_y):
            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws:
                ws.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
                ws.receive_json()
                ws.send_json({"type": "start_game", "payload": {}})
                ws.receive_json()  # game_state {phase: round_started}
                msg = ws.receive_json()
                starts.append(msg["payload"]["startSeconds"])

        # Espace [0, 10000) : collision statistiquement négligeable, ce
        # test peut en théorie flaker mais avec une probabilité infime.
        assert starts[0] != starts[1]


def _game_id(engine, game_code: str) -> int:
    from app.blindtest.models import Game

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        return db.query(Game).filter(Game.code == game_code).first().id
    finally:
        db.close()


class TestGuessSubmitted:
    """Story 2.5 — matrice I/O de spec-2-5-devinette-selection-multiple.md.
    Aucun message n'est jamais renvoyé/diffusé par le serveur pour
    `guess_submitted` : chaque test vérifie l'état en observant directement
    `guess_store` (source de vérité en mémoire, pas de round-trip WS pour
    lire une devinette dans cette story)."""

    def test_happy_path_stores_guess(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Bob"]}})

                # Pas de réponse attendue : on déclenche un nouveau
                # broadcast (3e joueur) pour confirmer que ws1 n'a rien
                # d'autre en attente avant de lire directement guess_store.
                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()  # game_state (roster mis à jour)

                gid = _game_id(blindtest_engine, code)
                assert guess_store._guesses[gid]["Alice"] == ["Bob"]

    def test_resubmission_replaces_previous_guess(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()
            ws1.send_json({"type": "start_game", "payload": {}})
            ws1.receive_json()  # game_state {phase: round_started}
            ws1.receive_json()

            ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})
            ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice", "Bob"]}})

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                gid = _game_id(blindtest_engine, code)
                # Le second envoi ("Alice"+"Bob") a été rejeté à l'époque où
                # Bob n'était pas encore présent : seul le premier ("Alice")
                # est valide et reste stocké. On confirme l'écrasement
                # ci-dessous avec une resoumission valide après l'arrivée
                # de Bob.
                assert guess_store._guesses[gid]["Alice"] == ["Alice"]

                ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Bob"]}})
                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()
                    ws2.receive_json()

                assert guess_store._guesses[gid]["Alice"] == ["Bob"]

    def test_wrong_phase_is_silently_ignored(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            # Toujours en phase "lobby" (aucun start_game envoyé).
            ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

            gid = _game_id(blindtest_engine, code)
            assert guess_store._guesses.get(gid, {}) == {}

    def test_empty_selection_is_silently_ignored(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()
            ws1.send_json({"type": "start_game", "payload": {}})
            ws1.receive_json()  # game_state {phase: round_started}
            ws1.receive_json()

            ws1.send_json({"type": "guess_submitted", "payload": {"target_player_ids": []}})
            ws1.send_json({"type": "guess_submitted", "payload": {}})

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

            gid = _game_id(blindtest_engine, code)
            assert guess_store._guesses.get(gid, {}) == {}

    def test_unknown_pseudo_rejects_whole_submission(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()
            ws1.send_json({"type": "start_game", "payload": {}})
            ws1.receive_json()  # game_state {phase: round_started}
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                # "Ghost" n'est connecté à aucun socket de cette partie :
                # la soumission entière doit être rejetée, y compris pour
                # le nom valide ("Bob") qu'elle contient aussi.
                ws1.send_json(
                    {"type": "guess_submitted", "payload": {"target_player_ids": ["Bob", "Ghost"]}}
                )

                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()
                    ws2.receive_json()

            gid = _game_id(blindtest_engine, code)
            assert guess_store._guesses.get(gid, {}) == {}

    def test_duplicated_pseudo_is_deduplicated_on_store(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws1.send_json(
                    {"type": "guess_submitted", "payload": {"target_player_ids": ["Bob", "Bob"]}}
                )

                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()
                    ws2.receive_json()

                gid = _game_id(blindtest_engine, code)
                assert guess_store._guesses[gid]["Alice"] == ["Bob"]


@pytest.fixture
def blindtest_timer(blindtest_engine, monkeypatch):
    """Story 2.6 : pointe `main_blindtest.SessionLocal` (utilisé par
    `_round_timer`, tâche de fond qui ne peut pas réutiliser la session
    scopée-requête de `get_db`) vers le sessionmaker de la DB de test —
    mirroir de `override_get_db` de `blindtest_client` mais pour le chemin
    minuteur, seul à exercer réellement `SessionLocal` (cf. Design Notes de
    la spec : sans ce monkeypatch, la tâche de fond écrirait silencieusement
    dans le vrai `blindtest.db` de dev).

    Laisse `ROUND_GUESS_SECONDS` à une valeur volontairement courte mais
    encore confortable (1s) — assez pour ne jamais se déclencher pendant
    l'exécution normale d'un test (même un flux à 3 sockets), tout en
    gardant le coût d'un round non explicitement clôturé avant la fin du
    test raisonnable. Les tests qui veulent exercer le déclenchement réel du
    minuteur réduisent `ROUND_GUESS_SECONDS` eux-mêmes, localement (revue de
    code : un `0.05s` partagé par toute la classe créait une vraie course
    avec les tests à 3 sockets — le minuteur pouvait se déclencher avant la
    fin de leur séquence WS et désynchroniser l'ordre de réception attendu
    par le test, jusqu'au blocage).

    Note : `_close_round` annule activement le minuteur encore en vol dès
    qu'un round se clôture par avance (`_cancel_round_timer`), mais dans cet
    environnement de test (event loop porté par le thread `anyio`
    `BlockingPortal` de `TestClient`), la livraison de l'annulation à la
    tâche endormie s'est révélée retardée jusqu'à l'écoulement naturel de
    `ROUND_GUESS_SECONDS` plutôt qu'immédiate — d'où le choix d'une valeur
    courte ici plutôt que de compter sur l'annulation pour garder les tests
    rapides. `task.cancel()` reste correct et utile en production (event
    loop mono-thread standard, sans ce détail d'implémentation du portail de
    test).

    Story 2.7 (revue de code) : `REVEAL_DISPLAY_SECONDS` (par défaut 6s,
    utilisé par `_advance_round`, désormais une tâche de fond détachée au
    même titre que `_round_timer` — cf. Code Map) est réduit ici pour la
    même raison et à la même valeur que `ROUND_GUESS_SECONDS` ci-dessus :
    sans ce monkeypatch, tout `TestReveal` qui clôture un round (la classe
    entière le fait) laisserait échapper un `_advance_round` réel de 6s vers
    la moulinette async — qui touche alors `main_blindtest.SessionLocal` une
    fois ce test (et son override `blindtest_engine`) déjà démonté, pointant
    potentiellement vers le vrai `blindtest.db` de dev si ce monkeypatch a
    lui-même déjà été défait entre-temps par un test suivant."""
    import main_blindtest

    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=blindtest_engine)
    monkeypatch.setattr(main_blindtest, "SessionLocal", test_session_local)
    monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 1)
    monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 1)


@pytest.mark.usefixtures("blindtest_timer")
class TestReveal:
    """Story 2.6 — matrice I/O de spec-2-6-reveal-score-cumule.md.

    `blindtest_timer` est appliqué à toute la classe (pas seulement aux
    tests qui exercent explicitement le chemin minuteur) : même les tests
    qui clôturent via la clôture anticipée démarrent quand même un vrai
    `_round_timer` en tâche de fond (`_handle_start_game` -> `game_lobby_ws`)
    — sans ce monkeypatch, ce minuteur réel toucherait le vrai
    `SessionLocal`/`blindtest.db` de dev (même s'il n'a pas le temps de se
    déclencher avant la fin du test)."""

    def test_all_answered_closes_round_and_broadcasts_reveal(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()  # round_started
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()  # round_started

                # Alice est le propriétaire réel : le seul joueur qui doit
                # répondre pour clôturer est Bob.
                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                reveal1 = ws1.receive_json()
                reveal2 = ws2.receive_json()
                for reveal in (reveal1, reveal2):
                    assert reveal["type"] == "reveal"
                    assert reveal["payload"]["owner_pseudo"] == "Alice"
                    # Owner trouvé seul -> +2 net pour Bob ; Alice (propriétaire)
                    # marque OWNER_ROUND_BONUS (1) sur son propre round.
                    assert reveal["payload"]["scores"] == {"Bob": 2, "Alice": 1}
                    # Story 5 : `deltas` porte le différentiel de CE round,
                    # identique à `scores` ici puisque c'est le premier round.
                    assert reveal["payload"]["deltas"] == {"Bob": 2, "Alice": 1}

    def test_deltas_differ_from_cumulative_scores_when_player_already_scored(
        self, blindtest_client, blindtest_engine
    ):
        """Story 5 : `deltas` (différentiel de CE round) doit rester distinct
        de `scores` (cumul depuis le début de la partie) dès qu'un joueur a
        déjà un score non nul avant ce round — pré-seedé directement dans
        `score_store` plutôt que de rejouer un vrai round 1 complet, pour ne
        pas dépendre du timing d'enchaînement automatique (`_advance_round`,
        Story 2.7)."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                gid = _game_id(blindtest_engine, code)
                score_store.add(gid, "Bob", 5)

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()  # round_started
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()  # round_started

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                reveal1 = ws1.receive_json()
                ws2.receive_json()
                assert reveal1["payload"]["scores"]["Bob"] == 7  # 5 (pré-seedé) + 2 (ce round)
                assert reveal1["payload"]["deltas"]["Bob"] == 2  # seulement ce round
                assert reveal1["payload"]["deltas"] != reveal1["payload"]["scores"]

    def test_owner_plus_wrong_name_still_nets_full_two(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json(
                    {"type": "guess_submitted", "payload": {"target_player_ids": ["Alice", "Bob"]}}
                )

                reveal1 = ws1.receive_json()
                ws2.receive_json()
                # Retour utilisateur (2026-09-14) : trouver le propriétaire
                # rapporte +2 plein même si un nom en trop a été coché dans la
                # même sélection — le malus -1/nom incorrect ne s'applique
                # plus qu'aux devinettes qui manquent le propriétaire.
                assert reveal1["payload"]["scores"]["Bob"] == 2

    def test_owner_missed_wrong_names_nets_negative_no_floor(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()
                    ws2.receive_json()

                    ws1.send_json({"type": "start_game", "payload": {}})
                    ws1.receive_json()  # game_state {phase: round_started}
                    ws1.receive_json()
                    ws2.receive_json()  # game_state {phase: round_started}
                    ws2.receive_json()
                    ws3.receive_json()  # game_state {phase: round_started}
                    ws3.receive_json()

                    # Bob et Carol devinent tous les deux sans trouver Alice.
                    ws2.send_json(
                        {"type": "guess_submitted", "payload": {"target_player_ids": ["Bob", "Carol"]}}
                    )
                    ws3.send_json(
                        {"type": "guess_submitted", "payload": {"target_player_ids": ["Bob"]}}
                    )

                    reveal1 = ws1.receive_json()
                    ws2.receive_json()
                    ws3.receive_json()
                    # Bob : 2 noms incorrects sélectionnés (Bob, Carol) -> -2.
                    assert reveal1["payload"]["scores"]["Bob"] == -2
                    # Carol : 1 nom incorrect ("Bob") -> -1.
                    assert reveal1["payload"]["scores"]["Carol"] == -1

    def test_no_guess_scores_zero(self, blindtest_client, blindtest_engine, blindtest_timer, monkeypatch):
        """Un joueur présent non-propriétaire qui ne soumet jamais de
        devinette valide (ici : une sélection vide, rejetée en silence par
        la validation de Story 2.5, donc jamais stockée dans `guess_store`)
        ne peut donc jamais déclencher la clôture anticipée lui-même — seul
        le minuteur peut clôturer ce round, et ce joueur doit alors être
        scoré à 0 (pas de bonus, pas de malus).

        Ce test veut vraiment que le minuteur se déclenche : override local
        de `ROUND_GUESS_SECONDS` à une valeur courte (`blindtest_timer` la
        laisse à 10s par défaut pour ne jamais racer les tests qui n'en ont
        pas besoin)."""
        import time
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                # Sélection vide : no-op silencieux (Story 2.5), jamais
                # stockée -> Bob ne peut jamais déclencher la clôture
                # anticipée lui-même.
                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": []}})

                # Laisse le minuteur (0.05s, `blindtest_timer`) clôturer.
                time.sleep(0.3)

                reveal1 = ws1.receive_json()
                reveal2 = ws2.receive_json()
                for reveal in (reveal1, reveal2):
                    assert reveal["type"] == "reveal"
                    assert reveal["payload"]["scores"]["Bob"] == 0

    def test_double_close_is_a_noop(self, blindtest_client, blindtest_engine, blindtest_timer, monkeypatch):
        """Le minuteur (déclenché rapidement via un override local de
        `ROUND_GUESS_SECONDS`) se déclenche après une clôture anticipée déjà
        survenue : no-op silencieux, pas de second `reveal`."""
        import time
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                reveal1 = ws1.receive_json()
                assert reveal1["type"] == "reveal"
                ws2.receive_json()

                # Laisse le minuteur (0.05s) se déclencher : il doit trouver
                # la partie déjà hors `round_started` et ne rien rediffuser.
                time.sleep(0.3)

                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    ws3.receive_json()
                    ws1.receive_json()
                    ws2.receive_json()

                    gid = _game_id(blindtest_engine, code)
                    assert score_store.snapshot(gid) == {"Bob": 2, "Alice": 1}

    def test_timeout_closes_round_when_not_all_answered(self, blindtest_client, blindtest_engine, blindtest_timer, monkeypatch):
        import time
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                # Personne ne répond : seul le minuteur peut clôturer.
                reveal1 = ws1.receive_json()
                reveal2 = ws2.receive_json()
                for reveal in (reveal1, reveal2):
                    assert reveal["type"] == "reveal"
                    assert reveal["payload"]["owner_pseudo"] == "Alice"
                    assert reveal["payload"]["scores"] == {"Bob": 0, "Alice": 1}

    def test_guess_from_disconnected_player_is_still_scored(self, blindtest_client, blindtest_engine):
        """Revue de code : un joueur qui soumet une devinette valide puis se
        déconnecte avant la clôture du round doit tout de même être scoré —
        `_close_round` ne doit pas se limiter aux joueurs actuellement
        présents (`connection_manager.players`), sinon sa devinette stockée
        dans `guess_store` serait silencieusement ignorée.

        Simule la déconnexion en injectant directement l'état plutôt qu'en
        fermant un vrai socket WS pendant qu'un round est actif : fermer une
        connexion réelle à ce moment précis s'est révélé être une source de
        flakiness/blocage de l'infrastructure de test (ordre d'arrivée des
        diffusions asynchrones), sans rapport avec la logique de score
        elle-même testée ici (déjà vérifiée par lecture directe du code :
        `scoreable_pseudos` dans `_close_round` fait l'union des joueurs
        présents et de `guess_store.known_pseudos`)."""
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, owner_pseudo="Alice")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                ws3.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws3.receive_json()  # game_state {phase: round_started}
                ws3.receive_json()

                # Bob a répondu correctement (+2) puis s'est déconnecté avant
                # la clôture : jamais réellement connecté via WS dans ce
                # test, seule sa devinette stockée doit compter.
                gid = _game_id(blindtest_engine, code)
                guess_store.submit(gid, "Bob", ["Alice"])

                # Carol répond à son tour : Bob n'étant pas dans le roster
                # présent, la vérification "tous ont répondu" ne porte que
                # sur Carol -> clôture anticipée malgré l'absence de Bob.
                ws3.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                reveal1 = ws1.receive_json()
                reveal3 = ws3.receive_json()
                for reveal in (reveal1, reveal3):
                    assert reveal["type"] == "reveal"
                    # Bob a bien été scoré (+2) malgré sa déconnexion.
                    assert reveal["payload"]["scores"]["Bob"] == 2


@pytest.mark.usefixtures("blindtest_timer")
class TestRoundAdvancement:
    """Story 2.7 — matrice I/O de
    spec-2-7-enchainement-classement-final.md.

    `blindtest_timer` (mirroir de `TestReveal`) redirige `SessionLocal` vers
    la DB de test pour tout minuteur de round encore en vol, et garde
    `ROUND_GUESS_SECONDS` à une valeur courte-mais-sûre (1s, jamais exercée
    directement ici — la clôture se fait toujours par soumission complète).
    `REVEAL_DISPLAY_SECONDS` (6s par défaut, bien trop long pour un test) est
    en revanche systématiquement réduit localement, chaque test exerçant
    réellement la pause avant enchaînement."""

    def test_untried_track_remaining_advances_to_next_round(self, blindtest_client, blindtest_engine, monkeypatch):
        """I/O matrix : pot a plus d'un morceau non-encore-tiré, cap non
        atteint -> `game_state {phase: next_round}` puis `round_started`
        avec un morceau jamais tiré plus tôt dans cette partie (couvre aussi
        le scénario "un morceau ne se répète jamais" pour ce cas)."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, youtube_video_id="track-a")
        _add_track(blindtest_engine, code, youtube_video_id="track-b")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()  # game_state {phase: round_started}
                round1_1 = ws1.receive_json()
                round1_2 = ws2.receive_json()
                assert round1_1["payload"]["videoId"] == round1_2["payload"]["videoId"]
                first_video_id = round1_1["payload"]["videoId"]

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                reveal1 = ws1.receive_json()
                reveal2 = ws2.receive_json()
                assert reveal1["type"] == "reveal"
                assert reveal2["type"] == "reveal"

                next_state1 = ws1.receive_json()
                next_state2 = ws2.receive_json()
                for state in (next_state1, next_state2):
                    assert state["type"] == "game_state"
                    assert state["payload"]["phase"] == "next_round"

                # `_advance_round` diffuse aussi `game_state {phase:
                # round_started}` juste avant le `round_started` du round 2
                # (même correctif que pour le round 1 — sans lui, `phase`
                # restait bloqué à "next_round" côté client, rendant la
                # partie injouable au-delà du premier round).
                round_started_state1 = ws1.receive_json()
                round_started_state2 = ws2.receive_json()
                for state in (round_started_state1, round_started_state2):
                    assert state["type"] == "game_state"
                    assert state["payload"]["phase"] == "round_started"

                round2_1 = ws1.receive_json()
                round2_2 = ws2.receive_json()
                for msg in (round2_1, round2_2):
                    assert msg["type"] == "round_started"
                assert round2_1["payload"]["videoId"] == round2_2["payload"]["videoId"]
                # Ne rejoue jamais le morceau déjà tiré au round 1.
                assert round2_1["payload"]["videoId"] != first_video_id
                assert round2_1["payload"]["videoId"] in ("track-a", "track-b")
                assert round2_1["payload"]["title"] == "Titre"
                assert round2_1["payload"]["artist"] == "Artiste"

    def test_pot_exhausted_early_ends_game_with_final_scores(
        self, blindtest_client, blindtest_engine, monkeypatch
    ):
        """I/O matrix : pot exhausté avant le cap de 15 rounds -> `game_state
        {phase: ended}` avec `final_scores`, quel que soit le nombre de
        rounds réellement joués."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        # Un seul morceau éligible dans tout le pot : une fois tiré au round
        # 1, plus aucun morceau non-encore-tiré ne reste -> fin de partie dès
        # la clôture de ce round, bien avant `ROUNDS_PER_GAME`.
        _add_track(blindtest_engine, code, youtube_video_id="only-track")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                ws1.receive_json()  # reveal
                ws2.receive_json()  # reveal

                ended1 = ws1.receive_json()
                ended2 = ws2.receive_json()
                for msg in (ended1, ended2):
                    assert msg["type"] == "game_state"
                    assert msg["payload"]["phase"] == "ended"
                    assert msg["payload"]["final_scores"] == {"Bob": 2, "Alice": 1}

    def test_cap_reached_ends_game_regardless_of_remaining_pot(
        self, blindtest_client, blindtest_engine, monkeypatch
    ):
        """I/O matrix : le 15e round vient de se clôturer -> `game_state
        {phase: ended}` avec `final_scores`, même si le pot a encore des
        morceaux non-tirés.

        Pré-remplit `played_tracks_store` avec 14 ids fictifs plutôt que de
        rejouer 14 rounds réels via WS (hors scope de ce test, coûteux et
        redondant avec `test_untried_track_remaining_advances_to_next_round`
        qui exerce déjà l'enchaînement round-à-round) : ce round réel devient
        ainsi le 15e joué pour cette partie dès son propre enregistrement
        dans `played_tracks_store`."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        # Deux morceaux éligibles : le pot n'est PAS épuisé, seul le cap doit
        # déclencher la fin de partie ici.
        _add_track(blindtest_engine, code, youtube_video_id="track-a")
        _add_track(blindtest_engine, code, youtube_video_id="track-b")
        gid = _game_id(blindtest_engine, code)
        for fake_track_id in range(-14, 0):
            played_tracks_store.add(gid, fake_track_id)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                ws1.receive_json()  # reveal
                ws2.receive_json()  # reveal

                ended1 = ws1.receive_json()
                ended2 = ws2.receive_json()
                for msg in (ended1, ended2):
                    assert msg["type"] == "game_state"
                    assert msg["payload"]["phase"] == "ended"
                    assert msg["payload"]["final_scores"] == {"Bob": 2, "Alice": 1}

    def test_host_chosen_rounds_count_ends_game_early(
        self, blindtest_client, blindtest_engine, monkeypatch
    ):
        """Retour utilisateur (2026-09-14) : "pouvoir choisir le nombre de
        rounds" — `start_game {rounds: 1}` doit terminer la partie dès la
        clôture du premier round, même si le pot a encore des morceaux
        non-tirés (mirroir de `test_cap_reached_ends_game_regardless_of_remaining_pot`
        mais avec un cap personnalisé au lieu de la valeur par défaut 15)."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, youtube_video_id="track-a")
        _add_track(blindtest_engine, code, youtube_video_id="track-b")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {"rounds": 1}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                ws1.receive_json()  # reveal
                ws2.receive_json()  # reveal

                ended1 = ws1.receive_json()
                ended2 = ws2.receive_json()
                for msg in (ended1, ended2):
                    assert msg["type"] == "game_state"
                    assert msg["payload"]["phase"] == "ended"

    def test_late_joiner_after_end_sees_final_scores(self, blindtest_client, blindtest_engine, monkeypatch):
        """I/O matrix : un client qui rejoint après la fin de partie reçoit
        `final_scores` dans son propre `game_state` (push de jointure)."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, youtube_video_id="only-track")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                ws1.receive_json()  # reveal
                ws2.receive_json()  # reveal
                ws1.receive_json()  # game_state ended
                ws2.receive_json()  # game_state ended

                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    join_state = ws3.receive_json()
                    assert join_state["payload"]["phase"] == "ended"
                    assert join_state["payload"]["final_scores"] == {"Bob": 2, "Alice": 1}

    def test_ended_game_ignores_start_game(self, blindtest_client, blindtest_engine, monkeypatch):
        """Boundaries de la spec : une fois `phase == "ended"`, aucun nouveau
        round ne peut jamais redémarrer sur cette partie (mirroir du garde
        `phase == "lobby"` déjà en place pour `start_game`, satisfait ici
        sans code additionnel puisque `ended != "lobby"`)."""
        import main_blindtest

        monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.05)

        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code, youtube_video_id="only-track")

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws2:
                ws2.send_json({"type": "join", "payload": {"pseudo": "Bob"}})
                ws2.receive_json()
                ws1.receive_json()

                ws1.send_json({"type": "start_game", "payload": {}})
                ws1.receive_json()  # game_state {phase: round_started}
                ws1.receive_json()
                ws2.receive_json()  # game_state {phase: round_started}
                ws2.receive_json()

                ws2.send_json({"type": "guess_submitted", "payload": {"target_player_ids": ["Alice"]}})

                ws1.receive_json()  # reveal
                ws2.receive_json()  # reveal
                ws1.receive_json()  # game_state ended
                ws2.receive_json()  # game_state ended

                ws1.send_json({"type": "start_game", "payload": {}})

                # Aucun nouveau `round_started` : confirmé via un nouveau
                # joignant, dont le `game_state` doit rester `ended`.
                with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws3:
                    ws3.send_json({"type": "join", "payload": {"pseudo": "Carol"}})
                    join_state = ws3.receive_json()
                    assert join_state["payload"]["phase"] == "ended"


class TestTwoGamesIsolation:
    def test_players_in_different_games_dont_see_each_other(self, blindtest_client):
        code_x = _create_game(blindtest_client)
        code_y = _create_game(blindtest_client)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code_x}/ws") as ws_a:
            ws_a.send_json({"type": "join", "payload": {"pseudo": "PlayerA"}})
            msg_a = ws_a.receive_json()
            assert msg_a["payload"]["players"] == ["PlayerA"]

            with blindtest_client.websocket_connect(f"/blindtest/games/{code_y}/ws") as ws_b:
                ws_b.send_json({"type": "join", "payload": {"pseudo": "PlayerB"}})
                msg_b = ws_b.receive_json()
                assert msg_b["payload"]["players"] == ["PlayerB"]
