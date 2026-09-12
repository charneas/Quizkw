"""Tests de la spec `spec-blindtest-admin-reconciliation.md` — réconciliation
manuelle admin des morceaux blind-test non trouvés.

Couvre la matrice I/O de la spec : garde d'authentification (401 identique
aux autres routes `/admin/*`), listing cross-playlist des morceaux
`youtube_video_id IS NULL`, résolution via lien complet/`youtu.be`/videoId
nu, entrée invalide (400), id inconnu (404), ré-résolution (écrasement),
et l'écriture `MatchCache` qui permet à un futur import du même morceau de
taper le cache sans rappeler aucun provider (AC de bout en bout).

DB isolée en mémoire, comme les autres tests blindtest (`test_blindtest_*`) —
jamais `conftest.py`/`app.database`, qui ne couvre que la DB principale.
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import sign_session, COOKIE_NAME
from app.blindtest.database import Base, get_db
from app.blindtest.models import MatchCache, Playlist, Track
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


@pytest.fixture
def admin_client(blindtest_client):
    """Même client que `blindtest_client`, mais avec le cookie de session
    admin déjà posé (signature directe via `sign_session`, comme
    `require_admin_session` — pas besoin d'une vraie table d'admins,
    stateless par conception, AD-17)."""
    blindtest_client.cookies.set(COOKIE_NAME, sign_session(admin_id=1))
    return blindtest_client


def _make_unresolved_track(session_factory, **overrides):
    db = session_factory()
    playlist = Playlist(source_url="https://open.spotify.com/playlist/abc", provider="spotify")
    db.add(playlist)
    db.flush()
    defaults = dict(
        playlist_id=playlist.id,
        title="Song",
        artist="Artist",
        isrc=None,
        youtube_video_id=None,
        source_url="https://open.spotify.com/track/xyz",
    )
    defaults.update(overrides)
    track = Track(**defaults)
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id, playlist_id = track.id, playlist.id
    db.close()
    return track_id, playlist_id


# ---------------------------------------------------------------------------
# Garde d'authentification
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_list_unresolved_without_cookie_returns_401(self, blindtest_client):
        resp = blindtest_client.get("/admin/blindtest/tracks/unresolved")
        assert resp.status_code == 401

    def test_resolve_without_cookie_returns_401(self, blindtest_client, blindtest_session_factory):
        track_id, _ = _make_unresolved_track(blindtest_session_factory)
        resp = blindtest_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/blindtest/tracks/unresolved
# ---------------------------------------------------------------------------

class TestListUnresolved:
    def test_empty_state_returns_empty_list_no_error(self, admin_client):
        resp = admin_client.get("/admin/blindtest/tracks/unresolved")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_only_unresolved_tracks_across_all_playlists(self, admin_client, blindtest_session_factory):
        db = blindtest_session_factory()
        playlist_a = Playlist(source_url="https://open.spotify.com/playlist/a", provider="spotify")
        playlist_b = Playlist(source_url="https://music.apple.com/playlist/b", provider="apple_music")
        db.add_all([playlist_a, playlist_b])
        db.flush()
        resolved = Track(playlist_id=playlist_a.id, title="Resolved", artist="A", youtube_video_id="vid-1")
        unresolved_a = Track(
            playlist_id=playlist_a.id, title="Unresolved A", artist="A", isrc="ISRC-A",
            source_url="https://open.spotify.com/track/a",
        )
        unresolved_b = Track(playlist_id=playlist_b.id, title="Unresolved B", artist="B")
        db.add_all([resolved, unresolved_a, unresolved_b])
        db.commit()
        playlist_a_id = playlist_a.id
        db.close()

        resp = admin_client.get("/admin/blindtest/tracks/unresolved")
        assert resp.status_code == 200
        body = resp.json()
        titles = {t["title"] for t in body}
        assert titles == {"Unresolved A", "Unresolved B"}

        by_title = {t["title"]: t for t in body}
        item_a = by_title["Unresolved A"]
        assert item_a["artist"] == "A"
        assert item_a["isrc"] == "ISRC-A"
        assert item_a["source_url"] == "https://open.spotify.com/track/a"
        assert item_a["playlist_id"] == playlist_a_id
        assert item_a["playlist_provider"] == "spotify"

        item_b = by_title["Unresolved B"]
        assert item_b["playlist_provider"] == "apple_music"
        assert item_b["source_url"] is None


# ---------------------------------------------------------------------------
# PUT /admin/blindtest/tracks/{track_id}
# ---------------------------------------------------------------------------

class TestResolveTrack:
    def test_full_youtube_url_resolves(self, admin_client, blindtest_session_factory, blindtest_engine):
        track_id, _ = _make_unresolved_track(blindtest_session_factory, isrc="ISRC-1")
        with patch("main_blindtest.matching.fetch_video_duration", return_value=None):
            resp = admin_client.put(
                f"/admin/blindtest/tracks/{track_id}",
                json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "dQw4w9WgXcQ"

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text("SELECT youtube_video_id FROM tracks WHERE id = :id"), {"id": track_id}).fetchone()
            cache_rows = conn.execute(text("SELECT COUNT(*) FROM match_cache WHERE isrc = 'ISRC-1'")).scalar()
        assert row[0] == "dQw4w9WgXcQ"
        assert cache_rows == 1

    def test_resolve_fetches_and_persists_duration_synchronously(
        self, admin_client, blindtest_session_factory, blindtest_engine
    ):
        """Matrice I/O : réconciliation admin — la durée est récupérée dans
        la même requête (synchrone) et persistée sur `Track` + `MatchCache`."""
        track_id, _ = _make_unresolved_track(blindtest_session_factory, isrc="ISRC-DUR-ADMIN")
        with patch("main_blindtest.matching.fetch_video_duration", return_value=222) as duration_fetch:
            resp = admin_client.put(
                f"/admin/blindtest/tracks/{track_id}",
                json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
        assert resp.status_code == 200
        assert resp.json()["duration_seconds"] == 222
        duration_fetch.assert_called_once_with("dQw4w9WgXcQ")

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(
                text("SELECT duration_seconds FROM tracks WHERE id = :id"), {"id": track_id}
            ).fetchone()
            cache_row = conn.execute(
                text("SELECT duration_seconds FROM match_cache WHERE isrc = 'ISRC-DUR-ADMIN'")
            ).fetchone()
        assert row[0] == 222
        assert cache_row[0] == 222

    def test_resolve_videos_list_failure_keeps_video_id_duration_stays_null(
        self, admin_client, blindtest_session_factory, blindtest_engine
    ):
        """Matrice I/O : échec `videos.list` pendant la réconciliation admin
        — le `youtube_video_id` reste appliqué, `duration_seconds` reste
        `NULL`, pas d'erreur 5xx."""
        track_id, _ = _make_unresolved_track(blindtest_session_factory, isrc="ISRC-DUR-FAIL")
        with patch("main_blindtest.matching.fetch_video_duration", return_value=None):
            resp = admin_client.put(
                f"/admin/blindtest/tracks/{track_id}",
                json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "dQw4w9WgXcQ"
        assert resp.json()["duration_seconds"] is None

    def test_reresolve_videos_list_failure_does_not_erase_existing_duration(
        self, admin_client, blindtest_session_factory
    ):
        """Ré-résolution (correction) d'un morceau qui a déjà une durée
        connue : si `videos.list` échoue silencieusement (`fetch_video_duration`
        renvoie `None`), la durée existante ne doit pas être écrasée à
        `NULL` — même principe que `cache.store` (un `None` n'efface jamais
        une valeur déjà connue)."""
        track_id, _ = _make_unresolved_track(
            blindtest_session_factory,
            isrc="ISRC-DUR-KEEP",
            youtube_video_id="vid-old",
            duration_seconds=222,
        )
        with patch("main_blindtest.matching.fetch_video_duration", return_value=None):
            resp = admin_client.put(
                f"/admin/blindtest/tracks/{track_id}",
                json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "dQw4w9WgXcQ"
        assert resp.json()["duration_seconds"] == 222

    def test_youtu_be_short_link_resolves(self, admin_client, blindtest_session_factory):
        track_id, _ = _make_unresolved_track(blindtest_session_factory)
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"},
        )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "dQw4w9WgXcQ"

    def test_bare_video_id_accepted_directly(self, admin_client, blindtest_session_factory):
        track_id, _ = _make_unresolved_track(blindtest_session_factory)
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "dQw4w9WgXcQ"},
        )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "dQw4w9WgXcQ"

    def test_unparseable_input_returns_400_no_mutation(self, admin_client, blindtest_session_factory, blindtest_engine):
        track_id, _ = _make_unresolved_track(blindtest_session_factory)
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "not a link"},
        )
        assert resp.status_code == 400

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(text("SELECT youtube_video_id FROM tracks WHERE id = :id"), {"id": track_id}).fetchone()
        assert row[0] is None

    def test_unknown_track_id_returns_404(self, admin_client):
        resp = admin_client.put(
            "/admin/blindtest/tracks/999999",
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert resp.status_code == 404

    def test_re_resolve_already_resolved_track_overwrites(self, admin_client, blindtest_session_factory):
        track_id, _ = _make_unresolved_track(blindtest_session_factory, youtube_video_id="old-vid-id")
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "https://www.youtube.com/watch?v=newVideoId1"},
        )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "newVideoId1"

    def test_resolve_overwrites_stale_match_cache_row_for_isrc(
        self, admin_client, blindtest_session_factory, blindtest_engine
    ):
        """Régression : corriger un morceau dont l'ISRC a déjà une ligne
        `MatchCache` (pointant vers l'ancienne, mauvaise vidéo) doit mettre à
        jour cette ligne — pas la laisser périmée, ce qui ferait qu'un futur
        import du même morceau relise la mauvaise valeur (défait le but même
        de l'endpoint de correction)."""
        db = blindtest_session_factory()
        db.add(MatchCache(isrc="ISRC-STALE", normalized_key=None, youtube_video_id="old-wrong-vid"))
        db.commit()
        db.close()

        track_id, _ = _make_unresolved_track(blindtest_session_factory, isrc="ISRC-STALE")
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "https://www.youtube.com/watch?v=correctedId"},
        )
        assert resp.status_code == 200
        assert resp.json()["youtube_video_id"] == "correctedId"

        with blindtest_engine.connect() as conn:
            from sqlalchemy import text
            row = conn.execute(
                text("SELECT youtube_video_id FROM match_cache WHERE isrc = 'ISRC-STALE'")
            ).fetchone()
        assert row[0] == "correctedId"

    def test_manual_resolution_cache_is_hit_by_later_import_no_provider_call(
        self, admin_client, blindtest_session_factory, blindtest_engine
    ):
        """AC de bout en bout : un morceau résolu manuellement (même
        titre/artiste/ISRC) importé plus tard dans une AUTRE playlist doit
        taper `MatchCache` sans jamais appeler un provider (Story 1.3)."""
        from app.blindtest.extraction_types import ExtractedTrack

        track_id, _ = _make_unresolved_track(
            blindtest_session_factory, title="Same Song", artist="Same Artist", isrc="ISRC-SHARED",
        )
        resp = admin_client.put(
            f"/admin/blindtest/tracks/{track_id}",
            json={"youtube_url": "https://www.youtube.com/watch?v=manualVideo"},
        )
        assert resp.status_code == 200

        fake_tracks = [
            ExtractedTrack(title="Same Song", artist="Same Artist", isrc="ISRC-SHARED", source_url="https://open.spotify.com/track/other"),
        ]
        with patch("app.blindtest.providers.spotify.fetch_tracks", return_value=fake_tracks), \
             patch("app.blindtest.matching.SessionLocal", blindtest_session_factory), \
             patch("httpx.Client") as client_cls:
            post_resp = admin_client.post(
                "/blindtest/playlists",
                json={"url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"},
            )

        assert post_resp.status_code == 201
        client_cls.assert_not_called()

        # La réponse du POST est sérialisée avant l'exécution des
        # `BackgroundTasks` (matching) — comme dans
        # `test_blindtest_matching.TestImportThenPollIntegration`, on relit
        # via GET pour observer le résultat du matching en tâche de fond.
        playlist_id = post_resp.json()["id"]
        get_resp = admin_client.get(f"/blindtest/playlists/{playlist_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["tracks"][0]["youtube_video_id"] == "manualVideo"
