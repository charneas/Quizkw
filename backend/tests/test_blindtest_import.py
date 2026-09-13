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
DEEZER_URL = "https://www.deezer.com/playlist/908622995"


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


class TestDeezerImport:
    def test_matches_playlist_url(self):
        from app.blindtest.providers import deezer

        assert deezer.matches(DEEZER_URL) is True

    def test_matches_playlist_url_with_locale_prefix(self):
        from app.blindtest.providers import deezer

        assert deezer.matches("https://www.deezer.com/fr/playlist/908622995") is True

    def test_matches_returns_false_for_artist_url(self):
        from app.blindtest.providers import deezer

        assert deezer.matches("https://www.deezer.com/artist/27") is False

    def test_matches_returns_false_for_album_url(self):
        from app.blindtest.providers import deezer

        assert deezer.matches("https://www.deezer.com/album/302127") is False

    def test_fetch_tracks_happy_path_single_page(self):
        from app.blindtest.providers import deezer

        page = MagicMock(status_code=200)
        page.json.return_value = {
            "data": [
                {
                    "title": "Song A",
                    "artist": {"name": "Artist A"},
                    "isrc": "ISRC1",
                    "link": "https://www.deezer.com/track/1",
                },
                {
                    "title": "Song B",
                    "artist": {"name": "Artist B"},
                    "isrc": "ISRC2",
                    "link": "https://www.deezer.com/track/2",
                },
            ],
            "total": 2,
        }

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = page
            tracks = deezer.fetch_tracks(DEEZER_URL)

        assert len(tracks) == 2
        assert tracks[0].title == "Song A"
        assert tracks[0].artist == "Artist A"
        assert tracks[0].isrc == "ISRC1"
        assert tracks[0].source_url == "https://www.deezer.com/track/1"

    def test_fetch_tracks_follows_pagination_until_next_absent(self):
        from app.blindtest.providers import deezer

        page1 = MagicMock(status_code=200)
        page1.json.return_value = {
            "data": [{"title": "Song A", "artist": {"name": "Artist A"}, "isrc": None, "link": None}],
            "total": 2,
            "next": "https://api.deezer.com/playlist/908622995/tracks?index=1",
        }
        page2 = MagicMock(status_code=200)
        page2.json.return_value = {
            "data": [{"title": "Song B", "artist": {"name": "Artist B"}, "isrc": None, "link": None}],
            "total": 2,
        }

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.side_effect = [page1, page2]
            tracks = deezer.fetch_tracks(DEEZER_URL)

        assert [t.title for t in tracks] == ["Song A", "Song B"]

    def test_error_body_with_http_200_raises_private_playlist_error(self):
        """Deezer répond toujours HTTP 200, y compris en erreur — la clé
        top-level `"error"` du corps JSON est le seul signal fiable."""
        from app.blindtest.providers import deezer

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"error": {"type": "DataException", "message": "no data", "code": 800}}

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = resp

            with pytest.raises(PrivatePlaylistError):
                deezer.fetch_tracks(DEEZER_URL)

    def test_fetch_tracks_skips_non_dict_item_in_data(self):
        """Un item non-dict (ex. `null`) dans `data` ne doit pas faire
        planter l'extraction avec un AttributeError — il est simplement
        ignoré, comme les items sans titre/artiste."""
        from app.blindtest.providers import deezer

        page = MagicMock(status_code=200)
        page.json.return_value = {
            "data": [
                None,
                {"title": "Song A", "artist": {"name": "Artist A"}, "isrc": "ISRC1", "link": "https://www.deezer.com/track/1"},
            ],
            "total": 2,
        }

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = page
            tracks = deezer.fetch_tracks(DEEZER_URL)

        assert len(tracks) == 1
        assert tracks[0].title == "Song A"

    def test_empty_tracks_raises_private_playlist_error(self):
        from app.blindtest.providers import deezer

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [], "total": 0}

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = resp

            with pytest.raises(PrivatePlaylistError):
                deezer.fetch_tracks(DEEZER_URL)

    def test_import_pipeline_detects_deezer(self):
        from app.blindtest import import_pipeline

        assert import_pipeline.detect_provider(DEEZER_URL) == "deezer"

    def test_valid_deezer_playlist_persists_playlist_and_tracks(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1", source_url="https://www.deezer.com/track/1"),
            ExtractedTrack(title="Song B", artist="Artist B", isrc=None),
        ]
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "deezer"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["title"] == "Song A"
        assert data["tracks"][0]["isrc"] == "ISRC1"

        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 1
        assert tracks == 2


class TestDbIsolation:
    def test_blindtest_db_url_distinct_from_main_db(self):
        from app import database as main_database
        from app.blindtest import database as blindtest_database

        assert blindtest_database.DATABASE_URL != main_database.DATABASE_URL
