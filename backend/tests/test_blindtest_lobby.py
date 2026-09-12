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
