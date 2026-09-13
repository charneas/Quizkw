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
# extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    def test_non_youtube_host_with_v_param_is_rejected(self):
        # Le paramètre `?v=x` extrait ("x") ne fait pas 11 caractères
        # alphanumériques/`-`/`_` : rejeté par le format-check, peu importe
        # l'hôte non-YouTube.
        assert matching.extract_video_id("https://example.com/foo?v=x") is None

    def test_v_param_too_short_is_rejected(self):
        assert matching.extract_video_id("https://www.youtube.com/watch?v=short") is None

    def test_v_param_too_long_is_rejected(self):
        assert matching.extract_video_id("https://www.youtube.com/watch?v=wayTooLongVideoId123") is None

    def test_v_param_valid_length_is_accepted(self):
        assert matching.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_youtu_be_too_short_is_rejected(self):
        assert matching.extract_video_id("https://youtu.be/short") is None

    def test_bare_video_id_with_surrounding_whitespace_is_accepted(self):
        assert matching.extract_video_id("  dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"


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
                {"type": "youTube", "url": "https://www.youtube.com/watch?v=abc123defgh", "notAvailable": False},
            ]
        }
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = fake_resp
            result = matching.resolve_via_idonthavespotify("https://open.spotify.com/track/abc")
        assert result == "abc123defgh"

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
    def __init__(self, title="T", artist="A", source_url=None, playlist_source_url="PLAYLIST_URL", isrc=None):
        self.title = title
        self.artist = artist
        self.source_url = source_url
        self.isrc = isrc
        self.playlist = _FakePlaylist(playlist_source_url)


class TestResolveTrackVideoId:
    def test_primary_success_skips_fallback(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value="vidA") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search") as fallback, \
             patch("app.blindtest.matching.fetch_video_duration", return_value=120) as duration_fetch:
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == ("vidA", 120)
        primary.assert_called_once_with("TRACK_URL")
        fallback.assert_not_called()
        duration_fetch.assert_called_once_with("vidA")

    def test_primary_miss_falls_back(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value=None), \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value="vidB") as fallback, \
             patch("app.blindtest.matching.fetch_video_duration", return_value=90):
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == ("vidB", 90)
        fallback.assert_called_once_with(track.title, track.artist)

    def test_no_source_url_skips_primary_goes_straight_to_fallback(self):
        track = _FakeTrack(source_url=None, playlist_source_url="PLAYLIST_URL_SHOULD_NOT_BE_USED")
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value="vidC") as fallback, \
             patch("app.blindtest.matching.fetch_video_duration", return_value=60):
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == ("vidC", 60)
        primary.assert_not_called()

    def test_uses_track_source_url_never_playlist_source_url(self):
        """Régression du bug corrigé (Spec Change Log) : le lien envoyé à
        idonthavespotify doit être celui du MORCEAU, pas de la playlist."""
        track = _FakeTrack(source_url="TRACK_OWN_URL", playlist_source_url="PLAYLIST_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value="vid") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search"), \
             patch("app.blindtest.matching.fetch_video_duration", return_value=None):
            matching.resolve_track_video_id(MagicMock(), track)
        primary.assert_called_once_with("TRACK_OWN_URL")
        called_arg = primary.call_args[0][0]
        assert called_arg != "PLAYLIST_URL"

    def test_both_fail_returns_none_none(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify", return_value=None), \
             patch("app.blindtest.matching.resolve_via_youtube_search", return_value=None), \
             patch("app.blindtest.matching.fetch_video_duration") as duration_fetch:
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == (None, None)
        duration_fetch.assert_not_called()

    def test_cache_hit_skips_both_providers_and_duration_fetch(self):
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=("cached-vid", 42)), \
             patch("app.blindtest.matching.resolve_via_idonthavespotify") as primary, \
             patch("app.blindtest.matching.resolve_via_youtube_search") as fallback, \
             patch("app.blindtest.matching.fetch_video_duration") as duration_fetch:
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == ("cached-vid", 42)
        primary.assert_not_called()
        fallback.assert_not_called()
        duration_fetch.assert_not_called()

    def test_cache_hit_with_unknown_duration_returns_none_duration_no_retry(self):
        """Cache-hit, durée encore inconnue (matrice I/O) : la durée reste
        `None` telle quelle, aucun appel `fetch_video_duration` (pas de
        retry automatique)."""
        track = _FakeTrack(source_url="TRACK_URL")
        with patch("app.blindtest.matching.cache.lookup", return_value=("cached-vid", None)), \
             patch("app.blindtest.matching.fetch_video_duration") as duration_fetch:
            result = matching.resolve_track_video_id(MagicMock(), track)
        assert result == ("cached-vid", None)
        duration_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_video_duration / _parse_iso8601_duration
# ---------------------------------------------------------------------------

class TestParseIso8601Duration:
    def test_minutes_and_seconds(self):
        assert matching._parse_iso8601_duration("PT4M13S") == 4 * 60 + 13

    def test_hours_minutes_seconds(self):
        assert matching._parse_iso8601_duration("PT1H2M3S") == 3600 + 120 + 3

    def test_seconds_only(self):
        assert matching._parse_iso8601_duration("PT45S") == 45

    def test_hours_only(self):
        assert matching._parse_iso8601_duration("PT2H") == 7200

    def test_malformed_returns_none(self):
        assert matching._parse_iso8601_duration("not-a-duration") is None

    def test_empty_returns_none(self):
        assert matching._parse_iso8601_duration("") is None

    def test_bare_pt_returns_none(self):
        assert matching._parse_iso8601_duration("PT") is None


class TestFetchVideoDuration:
    def test_no_api_key_returns_none_no_network_call(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        with patch("httpx.Client") as client_cls:
            result = matching.fetch_video_duration("vid1")
        assert result is None
        client_cls.assert_not_called()

    def test_success_extracts_duration_seconds(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"items": [{"contentDetails": {"duration": "PT3M30S"}}]}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.fetch_video_duration("vid1")
        assert result == 210

    def test_empty_items_returns_none(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"items": []}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.fetch_video_duration("vid1")
        assert result is None

    def test_non_200_returns_none(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=404)
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.fetch_video_duration("unknown-vid")
        assert result is None

    def test_network_error_returns_none_no_exception(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("boom")
            result = matching.fetch_video_duration("vid1")
        assert result is None

    def test_malformed_payload_returns_none(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"unexpected": "shape"}
        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = fake_resp
            result = matching.fetch_video_duration("vid1")
        assert result is None

    def test_uses_videos_list_endpoint_with_content_details_part(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"items": []}
        with patch("httpx.Client") as client_cls:
            get_mock = client_cls.return_value.__enter__.return_value.get
            get_mock.return_value = fake_resp
            matching.fetch_video_duration("vid1")
        args, kwargs = get_mock.call_args
        assert args[0] == matching._YOUTUBE_VIDEOS_URL
        assert kwargs["params"]["part"] == "contentDetails"
        assert kwargs["params"]["id"] == "vid1"


class TestResolveTrackDurationOnly:
    def test_cache_hit_with_duration_skips_fetch(self):
        track = _FakeTrack(source_url=None)
        track.youtube_video_id = "vid-existing"
        with patch("app.blindtest.matching.cache.lookup", return_value=("vid-existing", 55)), \
             patch("app.blindtest.matching.fetch_video_duration") as duration_fetch:
            result = matching.resolve_track_duration_only(MagicMock(), track)
        assert result == 55
        duration_fetch.assert_not_called()

    def test_cache_hit_without_duration_calls_fetch(self):
        track = _FakeTrack(source_url=None)
        track.youtube_video_id = "vid-existing"
        with patch("app.blindtest.matching.cache.lookup", return_value=("vid-existing", None)), \
             patch("app.blindtest.matching.fetch_video_duration", return_value=77) as duration_fetch:
            result = matching.resolve_track_duration_only(MagicMock(), track)
        assert result == 77
        duration_fetch.assert_called_once_with("vid-existing")

    def test_no_cache_hit_calls_fetch_directly(self):
        track = _FakeTrack(source_url=None)
        track.youtube_video_id = "vid-existing"
        with patch("app.blindtest.matching.cache.lookup", return_value=None), \
             patch("app.blindtest.matching.fetch_video_duration", return_value=99) as duration_fetch:
            result = matching.resolve_track_duration_only(MagicMock(), track)
        assert result == 99
        duration_fetch.assert_called_once_with("vid-existing")

    def test_cache_hit_for_different_video_id_falls_through_to_fresh_fetch(self):
        """Le cache peut pointer, sous la même clé isrc/normalisée, vers un
        `video_id` différent de celui du morceau (ex : correction admin
        divergente) — ne jamais renvoyer une durée qui appartient à une
        autre vidéo, refaire un `fetch_video_duration` frais sur le bon id."""
        track = _FakeTrack(source_url=None)
        track.youtube_video_id = "vid-existing"
        with patch("app.blindtest.matching.cache.lookup", return_value=("vid-other", 55)), \
             patch("app.blindtest.matching.fetch_video_duration", return_value=123) as duration_fetch:
            result = matching.resolve_track_duration_only(MagicMock(), track)
        assert result == 123
        duration_fetch.assert_called_once_with("vid-existing")


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

        def fake_resolve(db, track):
            if track.title == "PrimaryHit":
                return ("vid1", 100)
            if track.title == "FallbackHit":
                return ("vid2", 200)
            if track.title == "Already":
                raise AssertionError("already-resolved tracks must never be re-queried")
            return (None, None)

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", side_effect=fake_resolve), \
             patch("app.blindtest.matching.resolve_track_duration_only", return_value=None):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        tracks_by_title = {t.title: t for t in db2.query(Track).filter(Track.playlist_id == playlist_id).all()}
        db2.close()

        assert tracks_by_title["Already"].youtube_video_id == "existing"
        assert tracks_by_title["PrimaryHit"].youtube_video_id == "vid1"
        assert tracks_by_title["PrimaryHit"].duration_seconds == 100
        assert tracks_by_title["FallbackHit"].youtube_video_id == "vid2"
        assert tracks_by_title["FallbackHit"].duration_seconds == 200
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

        def fake_resolve(db, track):
            if track.title == "Crashing":
                raise RuntimeError("boom")
            return (f"vid-{track.title}", None)

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", side_effect=fake_resolve):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        tracks_by_title = {t.title: t for t in db2.query(Track).filter(Track.playlist_id == playlist_id).all()}
        db2.close()

        assert tracks_by_title["First"].youtube_video_id == "vid-First"
        assert tracks_by_title["Crashing"].youtube_video_id is None
        assert tracks_by_title["Third"].youtube_video_id == "vid-Third"

    def test_cache_hit_skips_provider_http_calls_entirely(self, matching_session_factory):
        """Acceptance criteria (spec 1.3) : une ligne MatchCache pré-existante
        pour l'ISRC d'un morceau doit empêcher tout appel HTTP provider."""
        from app.blindtest.models import MatchCache

        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="spotify")
        db.add(playlist)
        db.flush()
        track = Track(playlist_id=playlist.id, title="Cached Song", artist="A", isrc="ISRC-1", source_url="url1")
        db.add(track)
        db.add(MatchCache(isrc="ISRC-1", normalized_key=None, youtube_video_id="cached-vid"))
        db.commit()
        playlist_id = playlist.id
        db.close()

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("httpx.Client") as client_cls:
            matching.match_playlist_tracks(playlist_id)

        client_cls.assert_not_called()

        db2 = matching_session_factory()
        resolved = db2.query(Track).filter(Track.playlist_id == playlist_id).first()
        db2.close()
        assert resolved.youtube_video_id == "cached-vid"

    def test_direct_youtube_track_with_video_id_gets_duration_fetched(self, matching_session_factory):
        """Matrice I/O : import YouTube direct — `youtube_video_id` déjà
        présent, `duration_seconds` encore `NULL` — doit maintenant être
        repris par la tâche de fond (auparavant complètement ignoré par le
        filtre de requête)."""
        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="youtube")
        db.add(playlist)
        db.flush()
        track = Track(playlist_id=playlist.id, title="Direct", artist="A", youtube_video_id="already-known-vid")
        db.add(track)
        db.commit()
        playlist_id = playlist.id
        db.close()

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id") as video_id_resolver, \
             patch("app.blindtest.matching.resolve_track_duration_only", return_value=150) as duration_resolver:
            matching.match_playlist_tracks(playlist_id)

        video_id_resolver.assert_not_called()
        duration_resolver.assert_called_once()

        db2 = matching_session_factory()
        resolved = db2.query(Track).filter(Track.playlist_id == playlist_id).first()
        db2.close()
        assert resolved.youtube_video_id == "already-known-vid"
        assert resolved.duration_seconds == 150

    def test_videos_list_failure_keeps_video_id_duration_stays_null_no_exception(self, matching_session_factory):
        """Matrice I/O : échec `videos.list` — le `youtube_video_id` déjà
        résolu reste intact, `duration_seconds` reste `NULL`, rien ne
        propage."""
        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="youtube")
        db.add(playlist)
        db.flush()
        track = Track(playlist_id=playlist.id, title="Direct", artist="A", youtube_video_id="already-known-vid")
        db.add(track)
        db.commit()
        playlist_id = playlist.id
        db.close()

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_duration_only", return_value=None):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        resolved = db2.query(Track).filter(Track.playlist_id == playlist_id).first()
        db2.close()
        assert resolved.youtube_video_id == "already-known-vid"
        assert resolved.duration_seconds is None

    def test_fresh_resolution_videos_list_failure_video_id_kept_duration_null(self, matching_session_factory):
        """Matrice I/O : une résolution fraîche (pas de youtube_video_id au
        départ) dont `videos.list` échoue garde tout de même le
        `youtube_video_id` obtenu, `duration_seconds` reste `NULL`."""
        db = matching_session_factory()
        playlist = Playlist(source_url="PLAYLIST_URL", provider="spotify")
        db.add(playlist)
        db.flush()
        track = Track(playlist_id=playlist.id, title="Song", artist="A", source_url="url1")
        db.add(track)
        db.commit()
        playlist_id = playlist.id
        db.close()

        with patch("app.blindtest.matching.SessionLocal", matching_session_factory), \
             patch("app.blindtest.matching.resolve_track_video_id", return_value=("fresh-vid", None)):
            matching.match_playlist_tracks(playlist_id)

        db2 = matching_session_factory()
        resolved = db2.query(Track).filter(Track.playlist_id == playlist_id).first()
        db2.close()
        assert resolved.youtube_video_id == "fresh-vid"
        assert resolved.duration_seconds is None


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
             patch("app.blindtest.matching.resolve_track_video_id", return_value=("resolved-vid", 180)):
            post_resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert post_resp.status_code == 201
        playlist_id = post_resp.json()["id"]

        get_resp = blindtest_client.get(f"/blindtest/playlists/{playlist_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["tracks"][0]["youtube_video_id"] == "resolved-vid"
        assert data["tracks"][0]["duration_seconds"] == 180

    def test_get_unknown_playlist_returns_404(self, blindtest_client):
        resp = blindtest_client.get("/blindtest/playlists/999999")
        assert resp.status_code == 404

    def test_soundcloud_import_resolves_youtube_video_id_via_generic_matching(
        self, blindtest_client, blindtest_session_factory
    ):
        """Story 2 : preuve bout-en-bout que le pipeline générique de
        matching (`matching.match_playlist_tracks`), déjà exercé pour
        Spotify/YouTube, fonctionne aussi pour un morceau importé depuis
        SoundCloud — sans aucune modification de `matching.py`. Le provider
        SoundCloud est mocké (Story 1 le couvre déjà isolément) ; seule la
        résolution `source_url` -> `youtube_video_id` du morceau importé
        est vérifiée ici."""
        soundcloud_set_url = "https://soundcloud.com/someuser/sets/some-set"
        fake_tracks = [
            ExtractedTrack(
                title="Song A",
                artist="Artist A",
                source_url="https://soundcloud.com/someuser/song-a",
            ),
        ]
        with patch("app.blindtest.providers.soundcloud.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.SessionLocal", blindtest_session_factory), \
             patch(
                 "app.blindtest.matching.resolve_via_idonthavespotify",
                 return_value="resolved-vid",
             ) as idonthavespotify_mock, \
             patch("app.blindtest.matching.fetch_video_duration", return_value=180):
            post_resp = blindtest_client.post("/blindtest/playlists", json={"url": soundcloud_set_url})

        assert post_resp.status_code == 201
        assert post_resp.json()["provider"] == "soundcloud"
        playlist_id = post_resp.json()["id"]

        # Preuve que le morceau SoundCloud est bien passé par le chemin
        # `resolve_via_idonthavespotify` avec son PROPRE `source_url` (pas
        # celui de la playlist) — coeur du pipeline générique de matching.
        idonthavespotify_mock.assert_called_once_with("https://soundcloud.com/someuser/song-a")

        get_resp = blindtest_client.get(f"/blindtest/playlists/{playlist_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["tracks"][0]["youtube_video_id"] == "resolved-vid"
        assert data["tracks"][0]["duration_seconds"] == 180
