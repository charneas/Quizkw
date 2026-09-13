"""Tests de la Story 1.1 (import de playlist publique) — matrice I/O de
`spec-1-1-import-playlist-publique.md`. Chaque provider est mocké au niveau
de son module `fetch_tracks`/`matches` réel n'appelle jamais le réseau : on
patch directement le client httpx via `unittest.mock`.

Utilise sa propre DB SQLite en mémoire (distincte de `conftest.py`, qui ne
couvre que `app.database`) pour exercer l'isolation AD-7 de bout en bout.
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

    def test_spotify_premium_required_403_is_config_error_not_private_playlist(self):
        """Régression : Spotify répond 403 avec un corps mentionnant
        "premium subscription" quand le compte propriétaire de l'app n'a pas
        Premium — rien à voir avec la playlist ciblée (peut être publique et
        valide). Doit lever ProviderConfigError (503, message actionnable),
        jamais PrivatePlaylistError (422, message trompeur "privée/introuvable")."""
        from app.blindtest.providers import spotify

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        premium_resp = MagicMock(status_code=403)
        premium_resp.text = "Active premium subscription required for the owner of the app."

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "id", "SPOTIFY_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = premium_resp

            with pytest.raises(ProviderConfigError) as exc_info:
                spotify.fetch_tracks(SPOTIFY_URL)

        assert "Premium" in str(exc_info.value)


SOUNDCLOUD_SET_URL = "https://soundcloud.com/someuser/sets/some-set"
SOUNDCLOUD_TRACK_URL = "https://soundcloud.com/someuser/some-track"


class TestSoundCloudImport:
    def test_matches_set_url_true(self):
        from app.blindtest.providers import soundcloud

        assert soundcloud.matches(SOUNDCLOUD_SET_URL) is True

    def test_matches_isolated_track_url_false(self):
        from app.blindtest.providers import soundcloud

        assert soundcloud.matches(SOUNDCLOUD_TRACK_URL) is False

    def test_happy_path_single_page(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=200)
        resolve_resp.json.return_value = {
            "tracks": [
                {
                    "title": "Song A",
                    "publisher_metadata": {"artist": "Artist A"},
                    "user": {"username": "uploader-a"},
                    "permalink_url": "https://soundcloud.com/someuser/song-a",
                },
                {
                    "title": "Song B",
                    "publisher_metadata": None,
                    "user": {"username": "Uploader B"},
                    "permalink_url": "https://soundcloud.com/someuser/song-b",
                },
            ],
            "next_href": None,
        }

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            tracks = soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

        assert len(tracks) == 2
        assert tracks[0].title == "Song A"
        assert tracks[0].artist == "Artist A"
        assert tracks[0].source_url == "https://soundcloud.com/someuser/song-a"
        assert tracks[1].artist == "Uploader B"

    def test_pagination_aggregates_all_pages(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=200)
        resolve_resp.json.return_value = {
            "tracks": [
                {
                    "title": "Song A",
                    "publisher_metadata": {"artist": "Artist A"},
                    "user": {"username": "uploader-a"},
                    "permalink_url": "https://soundcloud.com/someuser/song-a",
                },
            ],
            "next_href": "https://api-v2.soundcloud.com/resolve?url=x&offset=1",
        }

        page2_resp = MagicMock(status_code=200)
        page2_resp.json.return_value = {
            "collection": [
                {
                    "title": "Song B",
                    "publisher_metadata": {"artist": "Artist B"},
                    "user": {"username": "uploader-b"},
                    "permalink_url": "https://soundcloud.com/someuser/song-b",
                },
            ],
            "next_href": None,
        }

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.side_effect = [resolve_resp, page2_resp]

            tracks = soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

        assert len(tracks) == 2
        assert tracks[0].title == "Song A"
        assert tracks[1].title == "Song B"

    def test_missing_credentials_raises_config_error_before_network_resolve(self):
        from app.blindtest.providers import soundcloud

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {}, clear=True):
            mock_client = client_cls.return_value.__enter__.return_value

            with pytest.raises(ProviderConfigError) as exc_info:
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

            mock_client.get.assert_not_called()

        assert "SOUNDCLOUD_CLIENT_ID" in str(exc_info.value)

    def test_rejected_credentials_raises_config_error(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=401)

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp

            with pytest.raises(ProviderConfigError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

    def test_private_or_not_found_set_raises_private_playlist_error(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=404)

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            with pytest.raises(PrivatePlaylistError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

    def test_empty_set_raises_private_playlist_error(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=200)
        resolve_resp.json.return_value = {"tracks": [], "next_href": None}

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            with pytest.raises(PrivatePlaylistError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

    def test_track_missing_artist_is_skipped(self):
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=200)
        resolve_resp.json.return_value = {
            "tracks": [
                {
                    "title": "No Artist Song",
                    "publisher_metadata": None,
                    "user": {},
                    "permalink_url": "https://soundcloud.com/someuser/no-artist",
                },
                {
                    "title": "Valid Song",
                    "publisher_metadata": {"artist": "Real Artist"},
                    "user": {"username": "uploader"},
                    "permalink_url": "https://soundcloud.com/someuser/valid-song",
                },
            ],
            "next_href": None,
        }

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            tracks = soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

        assert len(tracks) == 1
        assert tracks[0].title == "Valid Song"

    def test_none_track_entry_is_skipped(self):
        """SoundCloud renvoie des placeholders `null` pour les morceaux
        inaccessibles dans un set par ailleurs public — doit être ignoré
        comme un morceau sans titre/artiste, pas planter en AttributeError."""
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=200)
        resolve_resp.json.return_value = {
            "tracks": [
                None,
                {
                    "title": "Valid Song",
                    "publisher_metadata": {"artist": "Real Artist"},
                    "user": {"username": "uploader"},
                    "permalink_url": "https://soundcloud.com/someuser/valid-song",
                },
            ],
            "next_href": None,
        }

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            tracks = soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

        assert len(tracks) == 1
        assert tracks[0].title == "Valid Song"

    def test_resolve_non_403_404_error_status_raises_private_playlist_error(self):
        """Un statut d'erreur autre que 403/404 (ex. 401/500) ne doit pas
        laisser fuir `httpx.HTTPStatusError` via `raise_for_status()` — traité
        comme 403/404 (`PrivatePlaylistError`), conformément à la règle
        "jamais d'exception httpx brute qui fuit"."""
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "fake-token"}

        resolve_resp = MagicMock(status_code=500)
        resolve_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=resolve_resp
        )

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp
            mock_client.get.return_value = resolve_resp

            with pytest.raises(PrivatePlaylistError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

    def test_token_network_error_raises_config_error(self):
        """Une erreur réseau (timeout/connect) sur l'appel de token ne doit
        pas fuir en tant qu'exception httpx brute."""
        from app.blindtest.providers import soundcloud

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.side_effect = httpx.ConnectError("connection refused")

            with pytest.raises(ProviderConfigError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)

    def test_import_pipeline_detects_soundcloud_and_routes_extraction(self):
        """Story 2 : `import_pipeline.detect_provider`/`extract_tracks`
        doivent router une URL de set SoundCloud vers le provider
        `soundcloud` enregistré dans `_PROVIDERS` — sans ça une URL
        SoundCloud réelle échoue en `UnrecognizedUrlError` malgré un
        provider fonctionnel et testé isolément (Story 1)."""
        from app.blindtest import import_pipeline

        assert import_pipeline.detect_provider(SOUNDCLOUD_SET_URL) == "soundcloud"

        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", source_url="https://soundcloud.com/someuser/song-a"),
        ]
        with patch("app.blindtest.providers.soundcloud.fetch_tracks", return_value=fake_tracks) as fetch_mock:
            provider, tracks = import_pipeline.extract_tracks(SOUNDCLOUD_SET_URL)

        assert provider == "soundcloud"
        assert tracks == fake_tracks
        fetch_mock.assert_called_once_with(SOUNDCLOUD_SET_URL)

    def test_valid_soundcloud_set_persists_playlist_and_tracks(self, blindtest_client, blindtest_engine):
        """Bout-en-bout via le router `/blindtest/playlists` : preuve que le
        provider SoundCloud enregistré dans `_PROVIDERS` est bien atteignable
        depuis l'endpoint d'import public, pas seulement depuis
        `import_pipeline` directement."""
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", source_url="https://soundcloud.com/someuser/song-a"),
            ExtractedTrack(title="Song B", artist="Artist B"),
        ]
        with patch("app.blindtest.providers.soundcloud.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SOUNDCLOUD_SET_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "soundcloud"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["title"] == "Song A"

        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 1
        assert tracks == 2

    def test_token_malformed_json_raises_config_error(self):
        """Un JSON malformé (ou absence de `access_token`) dans la réponse
        de token ne doit pas fuir en `ValueError`/`KeyError` brut."""
        from app.blindtest.providers import soundcloud

        token_resp = MagicMock(status_code=200)
        token_resp.json.side_effect = ValueError("not json")

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"SOUNDCLOUD_CLIENT_ID": "id", "SOUNDCLOUD_CLIENT_SECRET": "secret"}):
            mock_client = client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = token_resp

            with pytest.raises(ProviderConfigError):
                soundcloud.fetch_tracks(SOUNDCLOUD_SET_URL)


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
        assert data["truncated"] is False

    def test_truncated_true_when_track_count_hits_max_tracks(self, blindtest_client, blindtest_engine):
        """`PlaylistResponse.truncated` doit signaler au client qu'une
        playlist YouTube a probablement été coupée par le garde-fou de
        pagination (`providers.youtube.MAX_TRACKS`), pour que l'UI en
        informe l'utilisateur plutôt que de laisser l'import paraître
        complet silencieusement."""
        from app.blindtest.providers import youtube

        fake_tracks = [
            ExtractedTrack(title=f"Vid {i}", artist="Channel", youtube_video_id=f"vid{i}")
            for i in range(youtube.MAX_TRACKS)
        ]
        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": YOUTUBE_URL})

        assert resp.status_code == 201
        assert resp.json()["truncated"] is True

    def test_music_youtube_com_playlist_is_recognized(self, blindtest_client, blindtest_engine):
        """`music.youtube.com` (YouTube Music) partage le même identifiant de
        playlist et la même API `playlistItems.list` qu'une playlist YouTube
        classique — doit être détecté comme provider `youtube`, pas rejeté
        en `UnrecognizedUrlError` (bug corrigé : host absent de
        `_YOUTUBE_HOSTS`)."""
        fake_tracks = [
            ExtractedTrack(title="Vid A", artist="Channel A", youtube_video_id="vid123"),
        ]
        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": "https://music.youtube.com/playlist?list=PLxyz123"},
            )

        assert resp.status_code == 201
        assert resp.json()["provider"] == "youtube"

    def test_topic_channel_suffix_stripped_from_artist(self):
        """Retour utilisateur (2026-09-13) : les chaînes auto-générées
        "Topic" de YouTube Music (uploads officiels sans clip) ont pour
        `videoOwnerChannelTitle` littéralement "{Artiste} - Topic" -- doit
        être nettoyé, un nom de chaîne sans ce suffixe reste inchangé."""
        from app.blindtest.providers import youtube

        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "items": [
                {
                    "snippet": {
                        "title": "Song A",
                        "videoOwnerChannelTitle": "Real Artist - Topic",
                        "resourceId": {"videoId": "vid-a"},
                    }
                },
                {
                    "snippet": {
                        "title": "Song B",
                        "videoOwnerChannelTitle": "Some Channel",
                        "resourceId": {"videoId": "vid-b"},
                    }
                },
            ],
            "nextPageToken": None,
        }

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            client_cls.return_value.__enter__.return_value.get.return_value = resp
            tracks = youtube.fetch_tracks(YOUTUBE_URL)

        assert tracks[0].artist == "Real Artist"
        assert tracks[1].artist == "Some Channel"

    def test_pagination_beyond_max_pages_truncates_instead_of_failing(self):
        """Une playlist dépassant `_MAX_PAGES` (ex. "Titres likés" avec des
        milliers d'entrées) doit être tronquée à ce qu'on a déjà collecté,
        pas rejetée entièrement — bug corrigé : `fetch_tracks` levait
        `PrivatePlaylistError` dans ce cas, pénalisant les grosses
        bibliothèques légitimes pour un morceau de blind test qui n'a de
        toute façon besoin que d'une quinzaine de pistes."""
        from app.blindtest.providers import youtube

        def fake_page(page_number: int) -> MagicMock:
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                "items": [
                    {
                        "snippet": {
                            "title": f"Track {page_number}",
                            "videoOwnerChannelTitle": "Channel",
                            "resourceId": {"videoId": f"vid-{page_number}"},
                        }
                    }
                ],
                # Toujours un nextPageToken : la pagination ne se termine
                # jamais d'elle-même, seul le garde-fou `_MAX_PAGES` doit
                # l'arrêter.
                "nextPageToken": f"token-{page_number + 1}",
            }
            return resp

        pages = [fake_page(i) for i in range(1, youtube._MAX_PAGES + 5)]

        with patch("httpx.Client") as client_cls, \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            client_cls.return_value.__enter__.return_value.get.side_effect = pages
            tracks = youtube.fetch_tracks("https://www.youtube.com/playlist?list=PLxyz123")

        assert len(tracks) == youtube._MAX_PAGES

    def test_failure_after_first_track_cache_store_leaves_no_partial_write(self, blindtest_client, blindtest_engine):
        """`cache.store()` (appelé pour le premier morceau, déjà résolu en
        YouTube direct) ne doit plus commiter en interne : si la boucle
        d'import échoue plus tard (ici sur la construction du 2e `Track`),
        ni la `Playlist` ni les `Track`/`MatchCache` déjà `add`és ne doivent
        être persistés — c'était le bug corrigé (regression pour
        spec-1-3-cache-matching-imports.md, section "no partial write")."""
        fake_tracks = [
            ExtractedTrack(title="Vid A", artist="Channel A", youtube_video_id="vid-a"),
            ExtractedTrack(title="Vid B", artist="Channel B", youtube_video_id="vid-b"),
        ]

        from app.blindtest.models import Track as RealTrack

        call_count = {"n": 0}

        def track_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom after first track's cache.store()")
            return RealTrack(*args, **kwargs)

        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=fake_tracks), \
             patch("main_blindtest.Track", side_effect=track_side_effect), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            with pytest.raises(RuntimeError):
                blindtest_client.post("/blindtest/playlists", json={"url": YOUTUBE_URL})

        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            cache_rows = conn.execute(text("SELECT COUNT(*) FROM match_cache")).scalar()
        assert cache_rows == 0


class TestMalformedUrl:
    def test_unrecognized_url_returns_400_no_provider_call(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock, \
             patch("app.blindtest.providers.youtube.fetch_tracks") as youtube_mock:
            resp = blindtest_client.post("/blindtest/playlists", json={"url": "not-a-url-at-all"})

        assert resp.status_code == 400
        spotify_mock.assert_not_called()
        youtube_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_track_link_not_playlist_returns_400(self, blindtest_client):
        resp = blindtest_client.post(
            "/blindtest/playlists",
            json={"url": "https://open.spotify.com/track/abc123"},
        )
        assert resp.status_code == 400


class TestNotFoundCount:
    """Tests de la Story 1.4 (signalement des morceaux non trouvés)."""

    def test_all_resolved_gives_zero_not_found_count(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Vid A", artist="Channel A", youtube_video_id="vid-a"),
            ExtractedTrack(title="Vid B", artist="Channel B", youtube_video_id="vid-b"),
        ]
        with patch("app.blindtest.providers.youtube.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": YOUTUBE_URL})

        assert resp.json()["not_found_count"] == 0

    def test_some_unresolved_counts_only_null_video_id_tracks(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1"),
            ExtractedTrack(title="Song B", artist="Artist B", isrc="ISRC2"),
            ExtractedTrack(title="Song C", artist="Artist C", isrc="ISRC3"),
        ]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        data = resp.json()
        assert len(data["tracks"]) == 3
        assert data["not_found_count"] == 3  # matching mocké : rien n'a encore été résolu

    def test_mixed_resolved_and_unresolved_counts_only_unresolved(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Resolved A", artist="Artist A", youtube_video_id="vid-a"),
            ExtractedTrack(title="Unresolved B", artist="Artist B", isrc="ISRC-B"),
            ExtractedTrack(title="Unresolved C", artist="Artist C", isrc="ISRC-C"),
        ]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        data = resp.json()
        assert len(data["tracks"]) == 3
        assert data["not_found_count"] == 2

    def test_empty_playlist_gives_zero_not_found_count(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=[]), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["tracks"] == []
        assert data["not_found_count"] == 0

    def test_all_unresolved_returns_200_with_full_count_no_fatal_error(self, blindtest_client, blindtest_engine):
        fake_tracks = [ExtractedTrack(title="Ghost Song", artist="Nobody")]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["not_found_count"] == len(data["tracks"]) == 1

        get_resp = blindtest_client.get(f"/blindtest/playlists/{data['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["not_found_count"] == 1


class TestScopedImport:
    """Tests de la Story 2.2 (import scopé à une partie) — matrice I/O de
    spec-2-2-import-scope-partie.md. Utilise directement `Game` (table
    isolée blindtest) et le `connection_manager` en mémoire de Story 2.1
    pour simuler un pseudo connecté au lobby, sans ouvrir de vrai socket."""

    def _make_game(self, blindtest_engine, phase="lobby", code="ABCDEF"):
        from sqlalchemy.orm import sessionmaker

        from app.blindtest.models import Game

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=blindtest_engine)
        db = SessionLocal()
        game = Game(code=code, phase=phase)
        db.add(game)
        db.commit()
        db.refresh(game)
        game_id = game.id
        db.close()
        return game_id

    def test_unscoped_import_unaffected_game_id_and_owner_pseudo_none(self, blindtest_client, blindtest_engine):
        """Regression guard : import sans game_code/pseudo reste identique à
        Epic 1 — game_id/owner_pseudo restent None."""
        fake_tracks = [ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1")]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": SPOTIFY_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["game_id"] is None
        assert data["owner_pseudo"] is None

    def test_scoped_import_valid_persists_game_id_and_owner_pseudo(self, blindtest_client, blindtest_engine):
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="lobby", code="ABCDEF")
        connection_manager._games["ABCDEF"] = {"Alice": object()}
        try:
            fake_tracks = [ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1")]
            with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": SPOTIFY_URL, "game_code": "ABCDEF", "pseudo": "Alice"},
                )

            assert resp.status_code == 201
            data = resp.json()
            assert data["game_id"] is not None
            assert data["owner_pseudo"] == "Alice"
        finally:
            connection_manager._games.pop("ABCDEF", None)

    def test_scoped_import_unknown_game_code_returns_404_no_partial_write(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": SPOTIFY_URL, "game_code": "ZZZZZZ", "pseudo": "Alice"},
            )

        assert resp.status_code == 404
        spotify_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_scoped_import_game_not_in_lobby_phase_returns_400_no_partial_write(self, blindtest_client, blindtest_engine):
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="round_started", code="INPLAY")
        connection_manager._games["INPLAY"] = {"Alice": object()}
        try:
            with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock:
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": SPOTIFY_URL, "game_code": "INPLAY", "pseudo": "Alice"},
                )

            assert resp.status_code == 400
            spotify_mock.assert_not_called()
            playlists, tracks = _count_rows(blindtest_engine)
            assert playlists == 0
            assert tracks == 0
        finally:
            connection_manager._games.pop("INPLAY", None)

    def test_scoped_import_pseudo_not_connected_returns_400_no_partial_write(self, blindtest_client, blindtest_engine):
        self._make_game(blindtest_engine, phase="lobby", code="GHOSTG")
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": SPOTIFY_URL, "game_code": "GHOSTG", "pseudo": "Ghost"},
            )

        assert resp.status_code == 400
        spotify_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_scoped_import_pseudo_disconnects_during_extraction_returns_400_no_partial_write(
        self, blindtest_client, blindtest_engine
    ):
        """`extract_tracks` est un aller-retour réseau qui peut prendre
        plusieurs secondes ; si le pseudo se déconnecte du lobby pendant ce
        délai, la re-vérification juste avant `db.add(playlist)` doit
        rejeter l'import au lieu de committer une playlist scopée à un
        pseudo qui n'est plus connecté (revue de code)."""
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="lobby", code="RACEGO")
        connection_manager._games["RACEGO"] = {"Alice": object()}

        def fetch_then_disconnect(*args, **kwargs):
            # Simule la déconnexion du pseudo pendant l'appel réseau au
            # provider, avant que le résultat ne soit renvoyé.
            connection_manager._games.pop("RACEGO", None)
            fake_tracks = [ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1")]
            return fake_tracks

        try:
            with patch("app.blindtest.providers.spotify.fetch_tracks", side_effect=fetch_then_disconnect), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": SPOTIFY_URL, "game_code": "RACEGO", "pseudo": "Alice"},
                )

            assert resp.status_code == 400
            playlists, tracks = _count_rows(blindtest_engine)
            assert playlists == 0
            assert tracks == 0
        finally:
            connection_manager._games.pop("RACEGO", None)

    def test_only_game_code_provided_returns_400(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": SPOTIFY_URL, "game_code": "ABCDEF"},
            )

        assert resp.status_code == 400
        spotify_mock.assert_not_called()

    def test_only_pseudo_provided_returns_400(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.spotify.fetch_tracks") as spotify_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": SPOTIFY_URL, "pseudo": "Alice"},
            )

        assert resp.status_code == 400
        spotify_mock.assert_not_called()

    def test_two_players_two_playlists_same_game_distinct_owner_pseudo(self, blindtest_client, blindtest_engine):
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="lobby", code="SHARED")
        connection_manager._games["SHARED"] = {"Alice": object(), "Bob": object()}
        try:
            fake_tracks_a = [ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1")]
            fake_tracks_b = [ExtractedTrack(title="Song B", artist="Artist B", isrc="ISRC2")]
            with patch("app.blindtest.providers.spotify.fetch_tracks", side_effect=[fake_tracks_a, fake_tracks_b]), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp_a = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": SPOTIFY_URL, "game_code": "SHARED", "pseudo": "Alice"},
                )
                resp_b = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": SPOTIFY_URL, "game_code": "SHARED", "pseudo": "Bob"},
                )

            assert resp_a.status_code == 201
            assert resp_b.status_code == 201
            data_a, data_b = resp_a.json(), resp_b.json()
            assert data_a["game_id"] == data_b["game_id"]
            assert data_a["owner_pseudo"] == "Alice"
            assert data_b["owner_pseudo"] == "Bob"

            playlists, _ = _count_rows(blindtest_engine)
            assert playlists == 2
        finally:
            connection_manager._games.pop("SHARED", None)


class TestDbIsolation:
    def test_blindtest_db_url_distinct_from_main_db(self):
        from app import database as main_database
        from app.blindtest import database as blindtest_database

        assert blindtest_database.DATABASE_URL != main_database.DATABASE_URL
