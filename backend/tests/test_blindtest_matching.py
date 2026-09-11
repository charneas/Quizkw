"""Tests de la Story 1.2 (matching automatique vers YouTube) — matrice I/O de
`spec-1-2-matching-automatique-youtube.md`.

Couvre : `resolve_via_idonthavespotify`, `resolve_via_youtube_search`,
`resolve_track_video_id`, `match_playlist_tracks`, et une intégration
POST->GET via `TestClient` (les `BackgroundTasks` s'exécutent
synchrones dans `TestClient`, pas besoin de sleep/poll).

Point critique (cf. Spec Change Log de la story) : `resolve_track_video_id`
doit utiliser `track.source_url` — jamais `track.playlist.source_url`. Un
test dédié vérifie explicitement quelle valeur est transmise à
`resolve_via_idonthavespotify`.
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blindtest import matching
from app.blindtest.database import Base, get_db
from app.blindtest.extraction_types import ExtractedTrack
from app.blindtest.models import Playlist, Track
from main import app as main_app


# ---------------------------------------------------------------------------
# resolve_via_idonthavespotify
# ---------------------------------------------------------------------------

class TestResolveViaIdonthavespotify:
    def test_no_base_url_configured_returns_none_no_network_call(self, monkeypatch):
        monkeypatch.delenv("IDONTHAVESPOTIFY_BASE_URL", raising=False)
        with patch("httpx.Client") as client_cls:
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result is None
        client_cls.assert_not_called()

    def test_success_extracts_video_id(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "links": [
                {"type": "youTube", "url": "https://www.youtube.com/watch?v=abc123", "notAvailable": False},
            ]
        }
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = fake_resp
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result == "abc123"

    def test_not_available_link_falls_back_to_none(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "links": [{"type": "youTube", "url": "https://www.youtube.com/watch?v=xxx", "notAvailable": True}]
        }
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = fake_resp
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result is None

    def test_no_youtube_link_in_response(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"links": []}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = fake_resp
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result is None

    def test_http_error_status_returns_none(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        fake_resp = MagicMock(status_code=500)
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = fake_resp
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result is None

    def test_connection_error_returns_none_no_exception(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("boom")
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result is None

    def test_request_body_uses_given_source_url(self, monkeypatch):
        monkeypatch.setenv("IDONTHAVESPOTIFY_BASE_URL", "http://localhost:9999")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"links": []}
        with patch("httpx.Client") as client_cls:
            post_mock = client_cls.return_value.__enter__.return_value.post
            post_mock.return_value = fake_resp
            matching.resolve_via_idonthavespotify("https://open.spotify.com/track/THE_TRACK")

        _, kwargs = post_mock.call_args
        assert kwargs["json"]["link"] == "https://open.spotify.com/track/THE_TRACK"
        assert kwargs["json"]["adapters"] == ["youTube"]


# ---------------------------------------------------------------------------
# resolve_via_youtube_search
# ---------------------------------------------------------------------------

class TestResolveViaYoutubeSearch:
    def test_no_api_key_returns_none_no_network_call(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        with patch("httpx.Client") as client_cls:
            result = matching.resolve_via_youtube_search("Title", "Artist")
        assert result is None
        client_cls.assert_not_called()

    def test_success_extracts_video_id(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"items": [{"id": {"videoId": "vid999"}}]}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.resolve_via_youtube_search("Title", "Artist")
        assert result == "vid999"

    def test_empty_results_returns_none(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"items": []}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.resolve_via_youtube_search("Title", "Artist")
        assert result is None

    def test_api_error_returns_none_no_exception(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("boom")
            result = matching.resolve_via_youtube_search("Title", "Artist")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_track_video_id
# ---------------------------------------------------------------------------

class _FakePlaylist:
    def __init__(self, source_url):
        self.source_url = source_url


class _FakeTrack:
    def __init__(self, title="T", artist="A", source_url=None, playlist_source_url="PLAYLIST_URL"):
        self.title = title
        self.artist = artist
        self.source_url = source_url
        self.playlist = _FakePlaylist(playlist_source_url)


class TestResolveTrackVideoId:
    def test_primary_success_skips_fallback(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value="vidA") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search") as fallback:
            result = matching.resolve_track_video_id(track)
        assert result == "vidA"
        primary.assert_called_once_with("TRACK_URL")
        fallback.assert_not_called()

    def test_primary_miss_falls_back(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value=None), \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value="vidB") as fallback:
            result = matching.resolve_track_video_id(track)
        assert result == "vidB"
        fallback.assert_called_once_with(track.title, track.artist)

    def test_no_source_url_skips_primary_goes_straight_to_fallback(self):
        track = _FakeTrack(source_url=None, playlist_source_url="PLAYLIST_URL_SHOULD_NOT_BE_USED")
        with patch("app.blindtest.matching.resolve_via_idonthavespotify") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value="vidC") as fallback:
            result = matching.resolve_track_video_id(track)
        assert result == "vidC"
        primary.assert_not_called()

    def test_uses_track_source_url_never_playlist_source_url(self):
        """Régression du bug corrigé (Spec Change Log) : le lien envoyé à
        idonthavespotify doit être celui du MORCEAU, pas de la playlist."""
        track = _FakeTrack(source_url="TRACK_OWN_URL", playlist_source_url="PLAYLIST_URL")
        with patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value="vid") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search"):
            matching.resolve_track_video_id(track)
        primary.assert_called_once_with("TRACK_OWN_URL")
        called_arg = primary.call_args[0][0]
        assert called_arg != "PLAYLIST_URL"

    def test_both_fail_returns_none(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value=None), \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value=None):
            result = matching.resolve_track_video_id(track)
        assert result is None


# ---------------------------------------------------------------------------
# match_playlist_tracks (orchestration, own SessionLocal)
# ---------------------------------------------------------------------------

@pytest.fixture
def matching_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def matching_session_factory(matching_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=matching_engine)


class TestMatchPlaylistTracks:
    def test_resolves_via_primary_then_fallback_skips_already_resolved(self, matching_session_factory):
        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="spotify")
        db.add(playlist)
        db.flush()
        already_resolved = Track(playlist_id=playlist.id, title="Already", artist="A", youtube_video_id="existing")
        primary_hit = Track(playlist_id=playlist.id, title="PrimaryHit", artist="A", source_url="url1")
        fallback_hit = Track(playlist_id=playlist.id, title="FallbackHit", artist="A", source_url="url2")
        unresolved = Track(playlist_id=playlist.id, title="Unresolved", artist="A", source_url="url3")
        db.add_all([already_resolved, primary_hit, fallback_hit, unresolved])
        db.commit()
        playlist_id = playlist.id
        db.close()

        def fake_resolve(track):
            if track.title == "PrimaryHit":
                return "vid1"
            if track.title == "FallbackHit":
                return "vid2"
            if track.title == "Already":
                raise AssertionError("already-resolved tracks must never be re-queried")
            return None

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", side_effect=fake_resolve):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        tracks_by_title = {t.title: t for t in db2.query(Track).filter(Track.playlist_id == playlist_id).all()}
        db2.close()

        assert tracks_by_title["Already"].youtube_video_id == "existing"
        assert tracks_by_title["PrimaryHit"].youtube_video_id == "vid1"
        assert tracks_by_title["FallbackHit"].youtube_video_id == "vid2"
        assert tracks_by_title["Unresolved"].youtube_video_id is None

    def test_one_track_exception_does_not_abort_the_others(self, matching_session_factory):
        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="spotify")
        db.add(playlist)
        db.flush()
        first = Track(playlist_id=playlist.id, title="First", artist="A", source_url="url1")
        crashing = Track(playlist_id=playlist.id, title="Crashing", artist="A", source_url="url2")
        third = Track(playlist_id=playlist.id, title="Third", artist="A", source_url="url3")
        db.add_all([first, crashing, third])
        db.commit()
        playlist_id = playlist.id
        db.close()

        def fake_resolve(track):
            if track.title == "Crashing":
                raise RuntimeError("boom")
            return f"vid-{track.title}"

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", side_effect=fake_resolve):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        tracks_by_title = {t.title: t for t in db2.query(Track).filter(Track.playlist_id == playlist_id).all()}
        db2.close()

        assert tracks_by_title["First"].youtube_video_id == "vid-First"
        assert tracks_by_title["Crashing"].youtube_video_id is None
        assert tracks_by_title["Third"].youtube_video_id == "vid-Third"


# ---------------------------------------------------------------------------
# Intégration HTTP : POST import (planifie le matching) + GET polling
# ---------------------------------------------------------------------------

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
def blindtest_session_factory(blindtest_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=blindtest_engine)


@pytest.fixture
def blindtest_client(blindtest_engine, blindtest_session_factory):
    def override_get_db():
        db = blindtest_session_factory()
        try:
            yield db
        finally:
            db.close()

    main_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main_app)
    yield client
    main_app.dependency_overrides.clear()


SPOTIFY_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


class TestImportThenPollIntegration:
    def test_post_then_get_reflects_matching_result(self, blindtest_client, blindtest_session_factory):
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", source_url="https://open.spotify.com/track/aaa"),
        ]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.SessionLocal", blindtest_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", return_value="resolved-vid"):
            post_resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert post_resp.status_code == 201
        playlist_id = post_resp.json()["id"]

        get_resp = blindtest_client.get(f"/blindtest/playlists/{playlist_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["tracks"][0]["youtube_video_id"] == "resolved-vid"

    def test_get_unknown_playlist_returns_404(self, blindtest_client):
        resp = blindtest_client.get("/blindtest/playlists/999999")
        assert resp.status_code == 404
