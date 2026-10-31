"""Partie de blind test classique de bout en bout (spec-blindtest-classique.md) :
endpoints, flux WS, et surtout aucune fuite de la réponse avant le reveal."""
import json
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from unittest.mock import patch

import main_blindtest
from app.blindtest import matching, preset_tracks, presets
from app.blindtest.database import Base, get_db
from app.blindtest.errors import ProviderUnavailableError
from app.blindtest.extraction_types import ExtractedTrack
from app.blindtest.game_connections import classic_round_store, guess_store, played_tracks_store, score_store
from app.blindtest.game_connections import manager as connection_manager
from app.blindtest.models import Game, Playlist, Track
from main import app as main_app

SECRET_TITLE = "Zebulon Rhapsodie"
SECRET_ARTIST = "Les Inconnus Du Quai"


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'classic.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _busy_timeout(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    main_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main_blindtest, "SessionLocal", session_local)
    monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 1)
    monkeypatch.setattr(main_blindtest, "REVEAL_DISPLAY_SECONDS", 0.1)
    monkeypatch.setattr(main_blindtest, "VOIDED_ROUND_DELAY_SECONDS", 0.1)
    yield TestClient(main_app)
    main_app.dependency_overrides.clear()
    connection_manager._games.clear()
    guess_store._guesses.clear()
    score_store._scores.clear()
    played_tracks_store._played.clear()
    classic_round_store._rounds.clear()
    main_blindtest._rounds_target.clear()


@pytest.fixture
def preset(tmp_path, monkeypatch):
    """Un preset figé de 12 morceaux, tous avec la même réponse à trouver : quel
    que soit le tirage, le test sait quoi répondre."""
    monkeypatch.setattr(presets, "_DIRECTORY", tmp_path)
    tracks = [
        {
            "youtube_video_id": f"video{index:06d}",
            "title": f"{SECRET_TITLE} {index}" if index else SECRET_TITLE,
            "artist": f"{SECRET_ARTIST} {index}" if index else SECRET_ARTIST,
            "duration_seconds": 200,
        }
        for index in range(12)
    ]
    chosen = presets.PRESETS[0]
    chosen.path.write_text(json.dumps({"tracks": tracks}), encoding="utf-8")
    return chosen


def _create_classic(client) -> str:
    resp = client.post("/blindtest/games", json={"mode": "classic"})
    assert resp.status_code == 201
    assert resp.json()["mode"] == "classic"
    return resp.json()["code"]


def _join(client, code, pseudo):
    ws = client.websocket_connect(f"/blindtest/games/{code}/ws")
    ws.__enter__()
    ws.send_json({"type": "join", "payload": {"pseudo": pseudo}})
    # Attendre le `game_state` du join : sinon l'ordre des joueurs, donc l'hôte,
    # dépendrait de la course entre les threads des sockets.
    _until(ws, "game_state")
    return ws


def _until(ws, msg_type, seen=None):
    """Lit jusqu'au message `msg_type`. Toujours borné : le minuteur serveur
    finit par envoyer quelque chose à chaque socket."""
    while True:
        msg = ws.receive_json()
        if seen is not None:
            seen.append(msg)
        if msg["type"] == msg_type:
            return msg


def _select_preset(client, code, preset, pseudo="Alice"):
    return client.post(f"/blindtest/games/{code}/preset", json={"slug": preset.slug, "pseudo": pseudo})


def _game(engine, code) -> tuple:
    session = sessionmaker(bind=engine)()
    try:
        game = session.query(Game).filter(Game.code == code).one()
        return game.id, game.phase, game.mode
    finally:
        session.close()


def _make_current_answer_known(engine, game_id):
    """Donne à la chanson du round la réponse `SECRET_*` dans le store."""
    from app.blindtest.classic import build_reference

    current = classic_round_store.get(game_id)
    current.reference = build_reference(SECRET_TITLE, SECRET_ARTIST)
    return current


def _seed_track(engine, code, provider, title, artist):
    session = sessionmaker(bind=engine)()
    try:
        game = session.query(Game).filter(Game.code == code).one()
        playlist = Playlist(source_url="https://x", provider=provider, game_id=game.id, owner_pseudo="Alice")
        session.add(playlist)
        session.flush()
        session.add(Track(
            playlist_id=playlist.id, title=title, artist=artist, youtube_video_id="vid00000000", duration_seconds=200,
        ))
        session.commit()
    finally:
        session.close()


def _start(ws, rounds=10, seen=None):
    ws.send_json({"type": "start_game", "payload": {"rounds": rounds}})
    return _until(ws, "round_started", seen)["payload"]


def _answer(ws, track_id, text):
    ws.send_json({"type": "answer_submitted", "payload": {"track_id": track_id, "text": text}})


class TestCreate:
    def test_default_mode_is_owner(self, client):
        assert client.post("/blindtest/games").json()["mode"] == "owner"

    def test_unknown_mode_is_rejected(self, client):
        assert client.post("/blindtest/games", json={"mode": "chaos"}).status_code == 422


class TestPresets:
    def test_list_gives_names_never_tracks(self, client, preset):
        resp = client.get("/blindtest/presets")
        assert resp.json() == [{"slug": "hits-80", "name": "Hits années 80", "track_count": 12}]

    def test_preset_without_snapshot_is_not_listed(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(presets, "_DIRECTORY", tmp_path)
        assert client.get("/blindtest/presets").json() == []

    def test_host_selects_preset_and_source_is_exposed_without_tracks(self, client, preset):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            resp = _select_preset(client, code, preset)
            assert resp.status_code == 200
            expected = {"name": "Hits années 80", "playable_count": 12, "checking": False}
            assert resp.json() == expected
            assert client.get(f"/blindtest/games/{code}/source").json() == expected
        finally:
            ws.__exit__(None, None, None)

    def _select_with_live_list(self, client, engine, preset, extracted, videos):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake"}),                  patch.object(preset_tracks.youtube, "fetch_tracks", return_value=extracted),                  patch.object(preset_tracks, "fetch_videos", return_value=videos):
                resp = client.post(
                    f"/blindtest/games/{code}/preset", json={"slug": preset.slug, "pseudo": "Alice"}
                )
            assert resp.status_code == 200
            with Session(bind=engine) as db:
                return {t.youtube_video_id: t for t in db.query(Track).all()}
        finally:
            ws.__exit__(None, None, None)

    def test_preset_is_read_live_and_keeps_reviewed_names(self, client, preset, engine):
        playable = {
            "contentDetails": {"duration": "PT3M"},
            "status": {"embeddable": True, "privacyStatus": "public"},
        }
        extracted = [
            ExtractedTrack(title="Bruit (Official Video)", artist="Chaine", youtube_video_id="video000000"),
            ExtractedTrack(title="New Band - New Song", artist="Label", youtube_video_id="videoNEW"),
            ExtractedTrack(title="Blocked - Song", artist="Label", youtube_video_id="videoBLOCKED"),
        ] + [
            ExtractedTrack(title=f"Band {i} - Song {i}", artist="Label", youtube_video_id=f"more{i}")
            for i in range(10)
        ]
        videos = {item.youtube_video_id: playable for item in extracted}
        videos["videoBLOCKED"] = {
            "contentDetails": {"duration": "PT3M"},
            "status": {"embeddable": False, "privacyStatus": "public"},
        }

        tracks = self._select_with_live_list(client, engine, preset, extracted, videos)

        assert "videoBLOCKED" not in tracks
        assert (tracks["video000000"].title, tracks["video000000"].artist) == (SECRET_TITLE, SECRET_ARTIST)
        assert (tracks["videoNEW"].title, tracks["videoNEW"].artist) == ("New Song", "New Band")
        assert tracks["videoNEW"].duration_seconds == 180

    def test_preset_falls_back_on_local_copy_when_youtube_fails(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake"}), patch.object(
                preset_tracks.youtube, "fetch_tracks", side_effect=ProviderUnavailableError("youtube", "panne")
            ):
                resp = client.post(
                    f"/blindtest/games/{code}/preset", json={"slug": preset.slug, "pseudo": "Alice"}
                )
            assert resp.status_code == 200
            assert resp.json()["playable_count"] == 12
        finally:
            ws.__exit__(None, None, None)

    def test_preset_fallback_never_logs_the_api_key(self, client, preset, caplog):
        request = httpx.Request("GET", "https://www.googleapis.com/youtube/v3/videos?key=SECRETKEY")
        error = httpx.HTTPStatusError(f"403 for {request.url}", request=request, response=httpx.Response(403))
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake"}), \
                 patch.object(preset_tracks.youtube, "fetch_tracks", return_value=[]), \
                 patch.object(preset_tracks, "fetch_videos", side_effect=error):
                resp = client.post(
                    f"/blindtest/games/{code}/preset", json={"slug": preset.slug, "pseudo": "Alice"}
                )
            assert resp.status_code == 200
            assert "SECRETKEY" not in caplog.text
        finally:
            ws.__exit__(None, None, None)

    def test_preset_falls_back_on_unexpected_response_shape(self, client, preset):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake"}), \
                 patch.object(preset_tracks.youtube, "fetch_tracks", return_value=[]), \
                 patch.object(preset_tracks, "fetch_videos", side_effect=KeyError("id")):
                resp = client.post(
                    f"/blindtest/games/{code}/preset", json={"slug": preset.slug, "pseudo": "Alice"}
                )
            assert resp.status_code == 200
            assert resp.json()["playable_count"] == 12
        finally:
            ws.__exit__(None, None, None)

    def test_live_list_counts_songs_not_videos(self, client, preset, engine):
        playable = {
            "contentDetails": {"duration": "PT3M"},
            "status": {"embeddable": True, "privacyStatus": "public"},
        }
        extracted = [
            ExtractedTrack(title="Band - Same Song", artist="Label", youtube_video_id=f"copy{i}") for i in range(12)
        ]
        tracks = self._select_with_live_list(
            client, engine, preset, extracted, {item.youtube_video_id: playable for item in extracted}
        )
        assert not any(video_id.startswith("copy") for video_id in tracks)
        assert len(tracks) == 12

    def test_preset_falls_back_when_live_list_is_too_short(self, client, preset, engine):
        playable = {
            "contentDetails": {"duration": "PT3M"},
            "status": {"embeddable": True, "privacyStatus": "public"},
        }
        extracted = [ExtractedTrack(title="A - B", artist="C", youtube_video_id="only")]
        tracks = self._select_with_live_list(client, engine, preset, extracted, {"only": playable})
        assert "only" not in tracks
        assert len(tracks) == 12

    def test_non_host_cannot_select_preset(self, client, preset):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        try:
            assert _select_preset(client, code, preset, "Bob").status_code == 403
        finally:
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_owner_game_refuses_preset(self, client, preset):
        code = client.post("/blindtest/games").json()["code"]
        assert _select_preset(client, code, preset).status_code == 400

    def test_unknown_preset_is_404(self, client, preset):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            resp = client.post(f"/blindtest/games/{code}/preset", json={"slug": "nope", "pseudo": "Alice"})
            assert resp.status_code == 404
        finally:
            ws.__exit__(None, None, None)

    def test_preset_replaces_previous_source(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            _select_preset(client, code, preset)
            session = sessionmaker(bind=engine)()
            try:
                assert session.query(Playlist).count() == 1
                assert session.query(Track).count() == 12
            finally:
                session.close()
        finally:
            ws.__exit__(None, None, None)


class TestClassicImport:
    FAKE_TRACKS = [ExtractedTrack(title=f"{SECRET_TITLE} {i}", artist=SECRET_ARTIST, youtube_video_id=f"id{i:09d}") for i in range(3)]
    URL = "https://www.youtube.com/playlist?list=PLabc"

    def _import(self, client, code, pseudo):
        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=self.FAKE_TRACKS), \
             patch("os.getenv", side_effect=lambda key, default=None: default), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            return client.post("/blindtest/playlists", json={"url": self.URL, "game_code": code, "pseudo": pseudo})

    def test_responses_never_contain_tracks(self, client):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            created = self._import(client, code, "Alice")
            assert created.status_code == 201
            assert created.json()["track_count"] == 3
            fetched = client.get(f"/blindtest/playlists/{created.json()['id']}")
            for resp in (created, fetched):
                assert "tracks" not in resp.json()
                assert SECRET_TITLE not in resp.text
                assert SECRET_ARTIST not in resp.text
                assert "id000000000" not in resp.text
        finally:
            ws.__exit__(None, None, None)

    def test_only_the_host_imports(self, client):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        try:
            assert self._import(client, code, "Bob").status_code == 403
        finally:
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_import_replaces_source_and_track_is_unplayable_until_duration_known(self, client, preset):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            created = self._import(client, code, "Alice")
            assert client.get(f"/blindtest/games/{code}/source").json() == {
                "name": "Playlist importée",
                "playable_count": 0,
                "checking": True,
            }
            matching._matching_playlist_ids.discard(created.json()["id"])
            assert client.get(f"/blindtest/games/{code}/source").json()["checking"] is False
        finally:
            ws.__exit__(None, None, None)

    def test_owner_game_still_gets_its_tracks(self, client):
        code = client.post("/blindtest/games").json()["code"]
        ws = _join(client, code, "Alice")
        try:
            resp = self._import(client, code, "Alice")
            assert len(resp.json()["tracks"]) == 3
        finally:
            ws.__exit__(None, None, None)


class TestStart:
    @pytest.mark.parametrize("rounds", [9, 51, 0, "20", True, None])
    def test_invalid_count_is_refused_with_a_reason(self, client, preset, engine, rounds):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            ws.send_json({"type": "start_game", "payload": {"rounds": rounds}})
            refused = _until(ws, "start_refused")
            assert refused["payload"]["reason"] == "invalid_rounds"
            assert _game(engine, code)[1] == "lobby"
        finally:
            ws.__exit__(None, None, None)

    def test_pool_too_small_is_refused_without_phase_change(self, client, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            ws.send_json({"type": "start_game", "payload": {"rounds": 10}})
            refused = _until(ws, "start_refused")
            assert refused["payload"]["reason"] == "pool_too_small"
            assert "0" in refused["payload"]["message"]
            assert _game(engine, code)[1] == "lobby"
        finally:
            ws.__exit__(None, None, None)

    def test_non_host_start_is_silently_ignored(self, client, preset, engine):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        try:
            _select_preset(client, code, preset)
            bob.send_json({"type": "start_game", "payload": {"rounds": 10}})
            bob.send_json({"type": "start_game", "payload": {"rounds": 5}})
            alice.send_json({"type": "start_game", "payload": {"rounds": 5}})
            assert _until(alice, "start_refused")["payload"]["reason"] == "invalid_rounds"
            assert _game(engine, code)[1] == "lobby"
        finally:
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_more_requested_than_playable_runs_what_exists(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            _start(ws, rounds=50)
            game_id = _game(engine, code)[0]
            assert main_blindtest._rounds_target[game_id] == 12
            _until(ws, "reveal")
        finally:
            ws.__exit__(None, None, None)


class TestRound:
    def test_no_payload_before_reveal_contains_the_answer(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(ws, seen=seen)
            assert set(payload) == {"videoId", "startSeconds", "trackId", "durationSeconds"}
            _answer(ws, payload["trackId"], "pas du tout ca")
            _answer(ws, payload["trackId"], SECRET_TITLE)
            reveal = _until(ws, "reveal", seen)["payload"]
            before_reveal = json.dumps(seen[:-1])
            assert SECRET_TITLE.lower() not in before_reveal.lower()
            assert SECRET_ARTIST.lower() not in before_reveal.lower()
            assert reveal["title"].startswith(SECRET_TITLE)
            assert reveal["artist"].startswith(SECRET_ARTIST)
        finally:
            ws.__exit__(None, None, None)

    def test_title_alone_at_10s_gains_60(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            current = _make_current_answer_known(engine, _game(engine, code)[0])
            current.started_at -= 10
            _answer(ws, payload["trackId"], SECRET_TITLE)
            result = _until(ws, "answer_result")["payload"]
            assert result["found"] == ["title"]
            assert result["points"] == 60
            live = _until(ws, "scores_updated")["payload"]
            assert live["scores"] == {"Alice": 60}
            reveal = _until(ws, "reveal")["payload"]
            assert reveal["deltas"] == {"Alice": 60}
            assert reveal["scores"] == {"Alice": 60}
        finally:
            ws.__exit__(None, None, None)

    def test_both_at_once_gain_close_to_200(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            _make_current_answer_known(engine, _game(engine, code)[0])
            _answer(ws, payload["trackId"], f"{SECRET_ARTIST} {SECRET_TITLE}")
            result = _until(ws, "answer_result")["payload"]
            assert result["found"] == ["artist", "title"]
            assert 190 <= result["points"] <= 200
        finally:
            ws.__exit__(None, None, None)

    def test_each_element_keeps_its_own_time_and_bonus_comes_with_the_second(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            current = _make_current_answer_known(engine, _game(engine, code)[0])
            current.started_at -= 10
            _answer(ws, payload["trackId"], SECRET_TITLE)
            assert _until(ws, "answer_result")["payload"]["points"] == 60
            current.started_at -= 10
            _answer(ws, payload["trackId"], SECRET_ARTIST)
            result = _until(ws, "answer_result")["payload"]
            assert result["found"] == ["artist", "title"]
            # (60 + 12) * 1,25 = 90, dont 60 déjà marqués.
            assert result["points"] == 30
            assert _until(ws, "reveal")["payload"]["deltas"] == {"Alice": 90}
        finally:
            ws.__exit__(None, None, None)

    def test_wrong_answer_gets_private_miss_and_can_retry(self, client, preset, engine):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        try:
            _select_preset(client, code, preset)
            payload = _start(alice)
            _make_current_answer_known(engine, _game(engine, code)[0])
            with patch.object(connection_manager, "send_to", wraps=connection_manager.send_to) as send_to:
                _answer(alice, payload["trackId"], "rien a voir")
                miss = _until(alice, "answer_result")["payload"]
                assert miss == {"track_id": payload["trackId"], "added": [], "found": [], "points": 0}
                _answer(alice, payload["trackId"], SECRET_TITLE)
                assert _until(alice, "answer_result")["payload"]["added"] == ["title"]
            assert {call.args[1] for call in send_to.call_args_list} == {"Alice"}
        finally:
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_already_found_is_a_silent_no_op(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            _make_current_answer_known(engine, _game(engine, code)[0])
            _answer(ws, payload["trackId"], SECRET_TITLE)
            first = _until(ws, "answer_result")["payload"]
            _answer(ws, payload["trackId"], SECRET_TITLE)
            reveal = _until(ws, "reveal", seen)["payload"]
            assert not [msg for msg in seen if msg["type"] == "answer_result"]
            assert reveal["deltas"]["Alice"] == first["points"]
        finally:
            ws.__exit__(None, None, None)

    @pytest.mark.parametrize("bad_payload", [
        {"track_id": 999999, "text": SECRET_TITLE},
        {"track_id": True, "text": SECRET_TITLE},
        {"text": SECRET_TITLE},
        {"track_id": "CURRENT", "text": 42},
        {"track_id": "CURRENT", "text": "x" * 201},
        {"track_id": "CURRENT", "text": SECRET_TITLE, "elapsed": 0, "verdict": True, "pseudo": "Bob"},
    ])
    def test_invalid_or_late_answers_are_ignored(self, client, preset, engine, bad_payload):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            current = _make_current_answer_known(engine, _game(engine, code)[0])
            current.started_at -= 10
            body = {k: payload["trackId"] if v == "CURRENT" else v for k, v in bad_payload.items()}
            ws.send_json({"type": "answer_submitted", "payload": body})
            reveal = _until(ws, "reveal", seen)["payload"]
            if "elapsed" in bad_payload:
                # Temps et verdict du client ignorés : c'est le serveur qui
                # chronomètre, et le pseudo reste celui du socket.
                assert reveal["deltas"] == {"Alice": 60}
            else:
                assert reveal["deltas"] == {"Alice": 0}
                assert not [msg for msg in seen if msg["type"] == "answer_result"]
        finally:
            ws.__exit__(None, None, None)

    def test_round_never_ends_early(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            _make_current_answer_known(engine, _game(engine, code)[0])
            _answer(ws, payload["trackId"], f"{SECRET_ARTIST} {SECRET_TITLE}")
            _until(ws, "answer_result")
            assert _game(engine, code)[1] == "round_started"
        finally:
            ws.__exit__(None, None, None)

    def test_joiner_mid_round_gets_the_round_without_the_answer(self, client, preset, engine):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = None
        try:
            _select_preset(client, code, preset)
            payload = _start(alice)
            bob = _join(client, code, "Bob")
            resumed = _until(bob, "round_started")["payload"]
            assert resumed["trackId"] == payload["trackId"]
            assert "elapsedSeconds" in resumed
            assert "title" not in resumed and "artist" not in resumed
        finally:
            if bob:
                bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)


    def test_reconnect_restores_position_and_finds(self, client, preset, engine, monkeypatch):
        monkeypatch.setattr(main_blindtest, "ROUND_GUESS_SECONDS", 3)
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        back = None
        try:
            _select_preset(client, code, preset)
            payload = _start(alice)
            bob = _join(client, code, "Bob")
            _until(bob, "round_started")
            current = _make_current_answer_known(engine, _game(engine, code)[0])
            _answer(bob, payload["trackId"], SECRET_TITLE)
            _until(bob, "answer_result")
            bob.__exit__(None, None, None)

            current.started_at -= 5
            back = _join(client, code, "Bob")
            resumed = _until(back, "round_started")["payload"]
            assert resumed["startSeconds"] == payload["startSeconds"] + 5
            restored = _until(back, "answer_result")["payload"]
            assert restored["found"] == ["title"]
            assert restored["restored"] is True
            assert restored["points"] == 0
        finally:
            if back:
                back.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "provider, title, artist, expected_title, expected_artist",
        [
            ("deezer", "Shallow - From A Star Is Born", "Lady Gaga", "Shallow", "Lady Gaga"),
            ("youtube", "Daft Punk - One More Time (Clip officiel)", "Best Hits", "One More Time", "Daft Punk"),
        ],
    )
    def test_reveal_reads_the_answer_from_the_source(
        self, client, engine, monkeypatch, provider, title, artist, expected_title, expected_artist
    ):
        monkeypatch.setattr(main_blindtest, "MIN_CLASSIC_ROUNDS", 1)
        code = _create_classic(client)
        _seed_track(engine, code, provider, title, artist)
        ws = _join(client, code, "Alice")
        try:
            payload = _start(ws, rounds=1)
            _answer(ws, payload["trackId"], f"{expected_artist} {expected_title}")
            assert sorted(_until(ws, "answer_result")["payload"]["found"]) == ["artist", "title"]
            reveal = _until(ws, "reveal")["payload"]
            assert reveal["title"] == expected_title
            assert reveal["artist"] == expected_artist
        finally:
            ws.__exit__(None, None, None)

    def test_track_without_findable_artist_is_not_playable(self, client, engine, monkeypatch):
        monkeypatch.setattr(main_blindtest, "MIN_CLASSIC_ROUNDS", 1)
        code = _create_classic(client)
        _seed_track(engine, code, "youtube", "Just A Title", "")
        ws = _join(client, code, "Alice")
        try:
            assert client.get(f"/blindtest/games/{code}/source").json()["playable_count"] == 0
            ws.send_json({"type": "start_game", "payload": {"rounds": 1}})
            assert _until(ws, "start_refused")["payload"]["reason"] == "pool_too_small"
        finally:
            ws.__exit__(None, None, None)


class TestVideoError:
    def test_half_of_players_void_the_round(self, client, preset, engine):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(alice)
            game_id = _game(engine, code)[0]
            target = main_blindtest._rounds_target[game_id]
            _make_current_answer_known(engine, game_id)
            _answer(alice, payload["trackId"], SECRET_TITLE)
            _until(alice, "scores_updated")
            alice.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"]}})

            voided = _until(alice, "round_voided", seen)["payload"]
            assert voided["scores"] == {"Alice": 0}
            assert not [msg for msg in seen if msg["type"] == "reveal"]
            assert main_blindtest._rounds_target[game_id] == target + 1

            following = _until(alice, "round_started")["payload"]
            assert following["trackId"] != payload["trackId"]
            assert following["videoId"] != payload["videoId"]
        finally:
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_void_logs_the_video_and_the_error_code(self, client, preset, engine, caplog):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            with caplog.at_level("WARNING", logger="main_blindtest"):
                ws.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"], "code": 150}})
                _until(ws, "round_voided")
            assert payload["videoId"] in caplog.text
            assert "150" in caplog.text
        finally:
            ws.__exit__(None, None, None)

    def test_below_half_keeps_the_round(self, client, preset, engine):
        code = _create_classic(client)
        alice = _join(client, code, "Alice")
        bob = _join(client, code, "Bob")
        carol = _join(client, code, "Carol")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(alice)
            carol.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"]}})
            carol.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"]}})
            _until(alice, "reveal", seen)
            assert not [msg for msg in seen if msg["type"] == "round_voided"]
        finally:
            carol.__exit__(None, None, None)
            bob.__exit__(None, None, None)
            alice.__exit__(None, None, None)

    def test_error_for_a_past_round_is_ignored(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        seen = []
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            ws.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"] + 1000}})
            _until(ws, "reveal", seen)
            assert not [msg for msg in seen if msg["type"] == "round_voided"]
        finally:
            ws.__exit__(None, None, None)


class TestEndAndRestart:
    def test_replay_reuses_source_and_resets_scores(self, client, preset, engine):
        code = _create_classic(client)
        ws = _join(client, code, "Alice")
        try:
            _select_preset(client, code, preset)
            payload = _start(ws)
            game_id = _game(engine, code)[0]
            main_blindtest._rounds_target[game_id] = 1
            _make_current_answer_known(engine, game_id)
            _answer(ws, payload["trackId"], SECRET_TITLE)

            while True:
                ended = _until(ws, "game_state")["payload"]
                if ended["phase"] == "ended":
                    break
            assert ended["final_scores"]["Alice"] > 0

            ws.send_json({"type": "restart_game", "payload": {}})
            lobby = _until(ws, "game_state")["payload"]
            assert lobby["phase"] == "lobby"
            assert lobby["scores"] == {}
            assert lobby["mode"] == "classic"
            assert client.get(f"/blindtest/games/{code}/source").json()["playable_count"] == 12

            again = _start(ws)
            assert again["videoId"]
            _until(ws, "reveal")
        finally:
            ws.__exit__(None, None, None)


class TestOwnerModeUnchanged:
    def _seed_owner_game(self, client, engine):
        code = client.post("/blindtest/games").json()["code"]
        ws = _join(client, code, "Alice")
        session = sessionmaker(bind=engine)()
        try:
            game = session.query(Game).filter(Game.code == code).one()
            playlist = Playlist(source_url="https://x", provider="deezer", game_id=game.id, owner_pseudo="Alice")
            session.add(playlist)
            session.flush()
            session.add(Track(
                playlist_id=playlist.id, title=SECRET_TITLE, artist=SECRET_ARTIST,
                youtube_video_id="vid00000000", duration_seconds=200,
            ))
            session.commit()
        finally:
            session.close()
        return code, ws

    def test_round_started_keeps_title_and_owner_scoring(self, client, engine):
        code, ws = self._seed_owner_game(client, engine)
        seen = []
        try:
            ws.send_json({"type": "start_game", "payload": {"rounds": 1}})
            state = _until(ws, "game_state")["payload"]
            assert state["mode"] == "owner"
            payload = _until(ws, "round_started")["payload"]
            assert payload["title"] == SECRET_TITLE
            assert payload["artist"] == SECRET_ARTIST
            assert "durationSeconds" not in payload

            _answer(ws, payload["trackId"], SECRET_TITLE)
            ws.send_json({"type": "video_error", "payload": {"track_id": payload["trackId"]}})
            reveal = _until(ws, "reveal", seen)["payload"]
            assert reveal["owner_pseudos"] == ["Alice"]
            assert reveal["deltas"] == {"Alice": main_blindtest.OWNER_ROUND_BONUS}
            assert not [msg for msg in seen if msg["type"] in ("answer_result", "scores_updated", "round_voided")]
        finally:
            ws.__exit__(None, None, None)

    def test_small_owner_pool_still_starts(self, client, engine):
        code, ws = self._seed_owner_game(client, engine)
        try:
            ws.send_json({"type": "start_game", "payload": {}})
            assert _until(ws, "round_started")["payload"]["trackId"]
            _until(ws, "reveal")
        finally:
            ws.__exit__(None, None, None)
