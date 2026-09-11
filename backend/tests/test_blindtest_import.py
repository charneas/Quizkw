"""Tests de la Story 1.1 (import de playlist publique) — matrice I/O de
`spec-1-1-import-playlist-publique.md`. Chaque provider est mocké au niveau
de son module `fetch_tracks`/`matches` réel n'appelle jamais le réseau : on
patch directement le client httpx via `unittest.mock`.

Utilise sa propre DB SQLite en mémoire (distincte de `conftest.py`, qui ne
couvre que `app.database`) pour exercer l'isolation AD-7 de bout en bout.
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blindtest.database import Base, get_db
from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError
from app.blindtest.extraction_types import ExtractedTrack
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


def _count_rows(blindtest_engine):
    with blindtest_engine.connect() as conn:
        from sqlalchemy import text
        playlists = conn.execute(text("SELECT COUNT(*) FROM playlists")).scalar()
        tracks = conn.execute(text("SELECT COUNT(*) FROM tracks")).scalar()
    return playlists, tracks


SPOTIFY_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
YOUTUBE_URL = "https://www.youtube.com/playlist?list=PLxyz123"
APPLE_URL = "https://music.apple.com/us/playlist/todays-hits/pl.abc123"


class TestSpotifyImport:
    def test_valid_spotify_playlist_persists_playlist_and_tracks(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1", source_url="https://open.spotify.com/track/aaa"),
            ExtractedTrack(title="Song B", artist="Artist B", isrc=None),
        ]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "spotify"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["title"] == "Song A"
        assert data["tracks"][0]["isrc"] == "ISRC1"

        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 1
        assert tracks == 2

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text("SELECT source_url FROM tracks ORDER BY id")).fetchall()
        assert row[0][0] == "https://open.spotify.com/track/aaa"
        assert row[1][0] is None

    def test_spotify_missing_credentials_returns_503_no_partial_write(self, blindtest_client, blindtest_engine):
        with patch(
            "app.blindtest.providers.spotify.fetch_tracks",
            side_effect=ProviderConfigError("spotify", "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET"),
        ):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 503
        assert "SPOTIFY_CLIENT_ID" in resp.json()["detail"]
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_spotify_private_playlist_returns_422_no_partial_write(self, blindtest_client, blindtest_engine):
        with patch(
            "app.blindtest.providers.spotify.fetch_tracks",
            side_effect=PrivatePlaylistError("Playlist Spotify privée, introuvable ou supprimée"),
        ):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 422
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0


class TestYoutubeImport:
    def test_valid_youtube_playlist_tracks_already_have_video_id(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Vid A", artist="Channel A", youtube_video_id="vid123"),
        ]
        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": YOUTUBE_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "youtube"
        assert data["tracks"][0]["youtube_video_id"] == "vid123"


class TestAppleMusicImport:
    def test_valid_apple_music_playlist_persists(self, blindtest_client, blindtest_engine):
        fake_tracks = [ExtractedTrack(title="Song C", artist="Artist C")]
        with patch("app.blindtest.providers.apple_music.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": APPLE_URL})

        assert resp.status_code == 201
        assert resp.json()["provider"] == "apple_music"


class TestMalformedUrl:
    def test_unrecognized_url_returns_400_no_provider_call(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock, \
             patch("app.blindtest.providers.youtube.fetch_tracks") as youtube_mock, \
             patch("app.blindtest.providers.apple_music.fetch_tracks") as apple_mock:
            resp = blindtest_client.post("/blindtest/playlists", json={"url": "not-a-url-at-all"})

        assert resp.status_code == 400
        spotify_mock.assert_not_called()
        youtube_mock.assert_not_called()
        apple_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_track_link_not_playlist_returns_400(self, blindtest_client):
        resp = blindtest_client.post(
            "/blindtest/playlists",
            json={"url": "https://open.spotify.com/track/abc123"},
        )
        assert resp.status_code == 400


class TestDbIsolation:
    def test_blindtest_db_url_distinct_from_main_db(self):
        from app import database as main_database
        from app.blindtest import database as blindtest_database

        assert blindtest_database.DATABASE_URL != main_database.DATABASE_URL
