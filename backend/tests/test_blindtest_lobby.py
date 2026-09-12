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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blindtest.database import Base, get_db
from app.blindtest.game_connections import guess_store
from app.blindtest.game_connections import manager as connection_manager
from main import app as main_app


@pytest.fixture
def blindtest_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


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


def _add_track(engine, game_code: str, *, youtube_video_id="abc123", duration_seconds=100) -> None:
    """Insère directement une `Playlist`+`Track` scopées à `game_code`, sans
    passer par le pipeline d'import (hors scope de cette story) — juste ce
    qu'il faut pour rendre un morceau éligible (ou non) au tirage de round."""
    from app.blindtest.models import Game, Playlist, Track

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.code == game_code).first()
        playlist = Playlist(source_url="https://example.com", provider="youtube", game_id=game.id, owner_pseudo="Alice")
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

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                for msg in (msg1, msg2):
                    assert msg["type"] == "round_started"
                    assert msg["payload"]["videoId"] == "abc123"
                    assert 0 <= msg["payload"]["startSeconds"] < 100

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

    def test_duplicate_start_is_a_noop(self, blindtest_client, blindtest_engine):
        code = _create_game(blindtest_client)
        _add_track(blindtest_engine, code)

        with blindtest_client.websocket_connect(f"/blindtest/games/{code}/ws") as ws1:
            ws1.send_json({"type": "join", "payload": {"pseudo": "Alice"}})
            ws1.receive_json()

            ws1.send_json({"type": "start_game", "payload": {}})
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
                ws1.receive_json()  # round_started pour Alice
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
                ws1.receive_json()
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
                ws1.receive_json()
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
