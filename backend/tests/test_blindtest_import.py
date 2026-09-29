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
from app.blindtest.errors import PrivatePlaylistError, ProviderUnavailableError
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


YOUTUBE_URL = "https://www.youtube.com/playlist?list=PLxyz123"
DEEZER_URL = "https://www.deezer.com/playlist/908622995"


class TestDeezerImport:
    def test_valid_deezer_playlist_persists_playlist_and_tracks(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1", source_url="https://www.deezer.com/track/111"),
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

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text("SELECT source_url FROM tracks ORDER BY id")).fetchall()
        assert row[0][0] == "https://www.deezer.com/track/111"
        assert row[1][0] is None

    def test_deezer_private_playlist_returns_422_no_partial_write(self, blindtest_client, blindtest_engine):
        with patch(
            "app.blindtest.providers.deezer.fetch_tracks",
            side_effect=PrivatePlaylistError("Playlist Deezer introuvable ou privée"),
        ):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

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
        with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock, \
             patch("app.blindtest.providers.youtube.fetch_tracks") as youtube_mock:
            resp = blindtest_client.post("/blindtest/playlists", json={"url": "not-a-url-at-all"})

        assert resp.status_code == 400
        deezer_mock.assert_not_called()
        youtube_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_track_link_not_playlist_returns_400(self, blindtest_client):
        resp = blindtest_client.post(
            "/blindtest/playlists",
            json={"url": "https://www.deezer.com/track/abc123"},
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
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

        data = resp.json()
        assert len(data["tracks"]) == 3
        assert data["not_found_count"] == 3  # matching mocké : rien n'a encore été résolu

    def test_mixed_resolved_and_unresolved_counts_only_unresolved(self, blindtest_client, blindtest_engine):
        fake_tracks = [
            ExtractedTrack(title="Resolved A", artist="Artist A", youtube_video_id="vid-a"),
            ExtractedTrack(title="Unresolved B", artist="Artist B", isrc="ISRC-B"),
            ExtractedTrack(title="Unresolved C", artist="Artist C", isrc="ISRC-C"),
        ]
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

        data = resp.json()
        assert len(data["tracks"]) == 3
        assert data["not_found_count"] == 2

    def test_empty_playlist_gives_zero_not_found_count(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=[]), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

        assert resp.status_code == 201
        data = resp.json()
        assert data["tracks"] == []
        assert data["not_found_count"] == 0

    def test_all_unresolved_returns_200_with_full_count_no_fatal_error(self, blindtest_client, blindtest_engine):
        fake_tracks = [ExtractedTrack(title="Ghost Song", artist="Nobody")]
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

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
        with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.match_playlist_tracks"):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": DEEZER_URL})

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
            with patch("app.blindtest.providers.deezer.fetch_tracks", return_value=fake_tracks), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": DEEZER_URL, "game_code": "ABCDEF", "pseudo": "Alice"},
                )

            assert resp.status_code == 201
            data = resp.json()
            assert data["game_id"] is not None
            assert data["owner_pseudo"] == "Alice"
        finally:
            connection_manager._games.pop("ABCDEF", None)

    def test_scoped_import_unknown_game_code_returns_404_no_partial_write(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": DEEZER_URL, "game_code": "ZZZZZZ", "pseudo": "Alice"},
            )

        assert resp.status_code == 404
        deezer_mock.assert_not_called()
        playlists, tracks = _count_rows(blindtest_engine)
        assert playlists == 0
        assert tracks == 0

    def test_scoped_import_game_not_in_lobby_phase_returns_400_no_partial_write(self, blindtest_client, blindtest_engine):
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="round_started", code="INPLAY")
        connection_manager._games["INPLAY"] = {"Alice": object()}
        try:
            with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock:
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": DEEZER_URL, "game_code": "INPLAY", "pseudo": "Alice"},
                )

            assert resp.status_code == 400
            deezer_mock.assert_not_called()
            playlists, tracks = _count_rows(blindtest_engine)
            assert playlists == 0
            assert tracks == 0
        finally:
            connection_manager._games.pop("INPLAY", None)

    def test_scoped_import_pseudo_not_connected_returns_400_no_partial_write(self, blindtest_client, blindtest_engine):
        self._make_game(blindtest_engine, phase="lobby", code="GHOSTG")
        with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": DEEZER_URL, "game_code": "GHOSTG", "pseudo": "Ghost"},
            )

        assert resp.status_code == 400
        deezer_mock.assert_not_called()
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
            with patch("app.blindtest.providers.deezer.fetch_tracks", side_effect=fetch_then_disconnect), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": DEEZER_URL, "game_code": "RACEGO", "pseudo": "Alice"},
                )

            assert resp.status_code == 400
            playlists, tracks = _count_rows(blindtest_engine)
            assert playlists == 0
            assert tracks == 0
        finally:
            connection_manager._games.pop("RACEGO", None)

    def test_only_game_code_provided_returns_400(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": DEEZER_URL, "game_code": "ABCDEF"},
            )

        assert resp.status_code == 400
        deezer_mock.assert_not_called()

    def test_only_pseudo_provided_returns_400(self, blindtest_client, blindtest_engine):
        with patch("app.blindtest.providers.deezer.fetch_tracks") as deezer_mock:
            resp = blindtest_client.post(
                "/blindtest/playlists",
                json={"url": DEEZER_URL, "pseudo": "Alice"},
            )

        assert resp.status_code == 400
        deezer_mock.assert_not_called()

    def test_two_players_two_playlists_same_game_distinct_owner_pseudo(self, blindtest_client, blindtest_engine):
        from app.blindtest.game_connections import manager as connection_manager

        self._make_game(blindtest_engine, phase="lobby", code="SHARED")
        connection_manager._games["SHARED"] = {"Alice": object(), "Bob": object()}
        try:
            fake_tracks_a = [ExtractedTrack(title="Song A", artist="Artist A", isrc="ISRC1")]
            fake_tracks_b = [ExtractedTrack(title="Song B", artist="Artist B", isrc="ISRC2")]
            with patch("app.blindtest.providers.deezer.fetch_tracks", side_effect=[fake_tracks_a, fake_tracks_b]), \
                 patch("app.blindtest.matching.match_playlist_tracks"):
                resp_a = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": DEEZER_URL, "game_code": "SHARED", "pseudo": "Alice"},
                )
                resp_b = blindtest_client.post(
                    "/blindtest/playlists",
                    json={"url": DEEZER_URL, "game_code": "SHARED", "pseudo": "Bob"},
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


class TestDeezerProvider:
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


DEEZER_SHORT_URL = "https://link.deezer.com/s/34wXl3NonleLhvFum28Fu"


class TestDeezerShortLink:
    """spec-deezer-short-links : `link.deezer.com/s/{code}` résolu en UNE
    requête (301 dont `Location` porte `dest=` l'URL canonique), sans suivre
    de redirection. Réponses calquées sur le comportement observé en live."""

    @staticmethod
    def _redirect(status, location):
        resp = MagicMock(status_code=status)
        resp.headers = {"location": location} if location else {}
        return resp

    @staticmethod
    def _api_page():
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [{"title": "Song A", "artist": {"name": "Artist A"}}]}
        return resp

    def _fetch(self, short_resp=None, short_side_effect=None):
        from app.blindtest.providers import deezer

        calls = []

        def get(url, **kwargs):
            calls.append((url, kwargs))
            if url.startswith("https://link.deezer.com/"):
                if short_side_effect is not None:
                    raise short_side_effect
                return short_resp
            return self._api_page()

        with patch("httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.side_effect = get
            tracks = deezer.fetch_tracks(DEEZER_SHORT_URL)
        return tracks, calls

    def test_matches_short_link(self):
        from app.blindtest.providers import deezer
        from app.blindtest.import_pipeline import detect_provider

        assert deezer.matches(DEEZER_SHORT_URL)
        assert detect_provider(DEEZER_SHORT_URL) == "deezer"
        assert not deezer.matches("https://link.deezer.com/other/abc")

    def test_resolves_dest_param_without_following_redirects(self):
        dest = "https%3A%2F%2Fwww.deezer.com%2Fplaylist%2F53362031%3Fhost%3D0%26utm_source%3Duser_sharing"
        location = f"https://link.deezer.com/?awf={dest}&dest={dest}"
        tracks, calls = self._fetch(self._redirect(301, location))

        assert [t.title for t in tracks] == ["Song A"]
        assert calls[0] == (DEEZER_SHORT_URL, {"follow_redirects": False})
        assert calls[1][0] == "https://api.deezer.com/playlist/53362031/tracks"
        assert len(calls) == 2  # aucune autre URL (hôte de redirection) contactée

    @pytest.mark.parametrize("location", [
        "https://www.deezer.com/fr/playlist/42",
        "https://www.deezer.com:443/playlist/42",
        "https://link.deezer.com/?dest=&x=1&dest=https%3A%2F%2Fwww.deezer.com%2Fplaylist%2F42",
    ])
    def test_location_variants_resolving_to_playlist_are_accepted(self, location):
        tracks, calls = self._fetch(self._redirect(302, location))
        assert [t.title for t in tracks] == ["Song A"]
        assert calls[1][0] == "https://api.deezer.com/playlist/42/tracks"

    @pytest.mark.parametrize("status,location", [
        (302, "https://www.deezer.com/deezer-links-404"),
        (302, "https://www.deezer.com/fr/deezer-links-404"),
        (404, None),
    ])
    def test_unknown_code_is_private_not_found(self, status, location):
        with pytest.raises(PrivatePlaylistError):
            self._fetch(self._redirect(status, location))

    @pytest.mark.parametrize("location", [
        "https://www.deezer.com/fr/track/123",
        "https://evil.example.com/playlist/42",
        "https://link.deezer.com/?dest=https%3A%2F%2Fevil.example.com%2Fplaylist%2F42",
        "https://www.deezer.com@evil.example.com/playlist/42",
        "javascript://www.deezer.com/playlist/42",
        "/s/other",
    ])
    def test_non_playlist_or_foreign_destination_is_unrecognized(self, location):
        from app.blindtest.errors import UnrecognizedUrlError

        with pytest.raises(UnrecognizedUrlError):
            self._fetch(self._redirect(301, location))

    def test_network_error_is_unavailable(self):
        with pytest.raises(ProviderUnavailableError):
            self._fetch(short_side_effect=httpx.ConnectError("boom"))

    @pytest.mark.parametrize("status", [200, 301, 429, 500])
    def test_answer_without_redirect_location_is_unavailable(self, status):
        with pytest.raises(ProviderUnavailableError):
            self._fetch(self._redirect(status, None))

    def test_fetch_tracks_on_non_short_link_path_makes_no_resolution_call(self):
        from app.blindtest.errors import UnrecognizedUrlError
        from app.blindtest.providers import deezer

        with patch("httpx.Client") as client_cls:
            with pytest.raises(UnrecognizedUrlError):
                deezer.fetch_tracks("https://link.deezer.com/other/abc")
            client_cls.return_value.__enter__.return_value.get.assert_not_called()


class TestProviderUnavailable:
    """spec-blindtest-provider-unavailable : une panne côté provider (réseau,
    5xx, 429, 400, quota épuisé, corps non-JSON) lève ProviderUnavailableError
    -> 502 explicite, jamais un 500 brut ni un "playlist privée" trompeur."""

    @staticmethod
    def _youtube_fetch_with(resp=None, side_effect=None):
        from app.blindtest.providers import youtube

        with patch("httpx.Client") as client_cls,              patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            get = client_cls.return_value.__enter__.return_value.get
            if side_effect is not None:
                get.side_effect = side_effect
            else:
                get.return_value = resp
            return youtube.fetch_tracks(YOUTUBE_URL)

    @staticmethod
    def _deezer_fetch_with(resp=None, side_effect=None):
        from app.blindtest.providers import deezer

        with patch("httpx.Client") as client_cls:
            get = client_cls.return_value.__enter__.return_value.get
            if side_effect is not None:
                get.side_effect = side_effect
            else:
                get.return_value = resp
            return deezer.fetch_tracks(DEEZER_URL)

    @pytest.mark.parametrize("status", [400, 429, 500, 503])
    def test_youtube_non_2xx_other_than_403_404_is_unavailable(self, status):
        resp = MagicMock(status_code=status)
        resp.json.return_value = {"error": {"code": status}}
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(resp)

    def test_youtube_network_error_is_unavailable(self):
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(side_effect=httpx.ConnectError("boom"))

    @pytest.mark.parametrize("reason", ["quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"])
    def test_youtube_403_quota_reason_is_unavailable_not_private(self, reason):
        resp = MagicMock(status_code=403)
        resp.json.return_value = {"error": {"code": 403, "errors": [{"reason": reason}]}}
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(resp)

    @pytest.mark.parametrize("status,body", [
        (403, {"error": {"code": 403, "errors": [{"reason": "playlistItemsNotAccessible"}]}}),
        (403, ValueError("not json")),
        (404, {"error": {"code": 404, "errors": [{"reason": "playlistNotFound"}]}}),
    ])
    def test_youtube_private_or_missing_playlist_still_private(self, status, body):
        resp = MagicMock(status_code=status)
        if isinstance(body, Exception):
            resp.json.side_effect = body
        else:
            resp.json.return_value = body
        with pytest.raises(PrivatePlaylistError):
            self._youtube_fetch_with(resp)

    def test_youtube_non_json_body_is_unavailable(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("not json")
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(resp)

    def test_youtube_non_object_body_is_unavailable(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = ["unexpected"]
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(resp)

    @pytest.mark.parametrize("reason", [["quotaExceeded"], {"x": 1}])
    def test_youtube_403_non_string_reason_does_not_crash(self, reason):
        resp = MagicMock(status_code=403)
        resp.json.return_value = {"error": {"errors": [{"reason": reason}]}}
        with pytest.raises(PrivatePlaylistError):
            self._youtube_fetch_with(resp)

    @pytest.mark.parametrize("items", [{"not": "a list"}, "str"])
    def test_youtube_non_list_items_is_unavailable(self, items):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"items": items}
        with pytest.raises(ProviderUnavailableError):
            self._youtube_fetch_with(resp)

    def test_youtube_malformed_items_are_skipped_not_crashing(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"items": [
            None,
            {"snippet": None},
            {"snippet": {"title": "T", "resourceId": "not-a-dict"}},
            {"snippet": {"title": "Ok", "videoOwnerChannelTitle": "A", "resourceId": {"videoId": "v1"}}},
        ]}
        tracks = self._youtube_fetch_with(resp)
        assert [t.youtube_video_id for t in tracks] == ["v1"]

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_deezer_non_2xx_is_unavailable(self, status):
        resp = MagicMock(status_code=status)
        resp.json.return_value = {"data": []}
        with pytest.raises(ProviderUnavailableError):
            self._deezer_fetch_with(resp)

    @pytest.mark.parametrize("code", [4, 700])
    def test_deezer_quota_or_busy_error_body_is_unavailable(self, code):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"error": {"type": "Exception", "message": "x", "code": code}}
        with pytest.raises(ProviderUnavailableError):
            self._deezer_fetch_with(resp)

    def test_deezer_not_found_error_body_is_still_private(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"error": {"type": "DataException", "message": "no data", "code": 800}}
        with pytest.raises(PrivatePlaylistError):
            self._deezer_fetch_with(resp)

    def test_deezer_network_error_is_unavailable(self):
        with pytest.raises(ProviderUnavailableError):
            self._deezer_fetch_with(side_effect=httpx.ReadTimeout("slow"))

    def test_deezer_non_json_body_is_unavailable(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("not json")
        with pytest.raises(ProviderUnavailableError):
            self._deezer_fetch_with(resp)

    def test_deezer_non_object_body_is_unavailable(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = ["unexpected"]
        with pytest.raises(ProviderUnavailableError):
            self._deezer_fetch_with(resp)

    @pytest.mark.parametrize("provider,url,label", [
        ("youtube", YOUTUBE_URL, "YouTube"),
        ("deezer", DEEZER_URL, "Deezer"),
    ])
    def test_import_endpoint_maps_unavailable_to_502_no_partial_write(
        self, blindtest_client, blindtest_engine, provider, url, label
    ):
        with patch(
            f"app.blindtest.providers.{provider}.fetch_tracks",
            side_effect=ProviderUnavailableError(provider, "HTTP 503"),
        ):
            resp = blindtest_client.post("/blindtest/playlists", json={"url": url})

        assert resp.status_code == 502
        assert resp.json()["detail"] == f"Service {label} indisponible, réessayez plus tard"
        assert _count_rows(blindtest_engine) == (0, 0)


class TestDbIsolation:
    def test_blindtest_db_url_distinct_from_main_db(self):
        from app import database as main_database
        from app.blindtest import database as blindtest_database

        assert blindtest_database.DATABASE_URL != main_database.DATABASE_URL
