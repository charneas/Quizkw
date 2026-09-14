"""Retour utilisateur (2026-09-15) : "les playlists non utilisées ça ne sert
à rien, par contre garder les chansons [MatchCache] a une utilité pour
éviter un réimport" — tests de
`scripts/prune_stale_blindtest_playlists.py`."""
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blindtest.database import Base
from app.blindtest.models import Game, MatchCache, Playlist, Track

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "prune_stale_blindtest_playlists.py",
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("prune_stale_blindtest_playlists", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prune_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def prune_module(prune_engine, monkeypatch):
    module = _load_script_module()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
    monkeypatch.setattr(module, "SessionLocal", SessionLocal)
    return module


def _make_playlist_with_track(session, *, created_at, game_id=None, video_id="v1"):
    playlist = Playlist(source_url="https://example.com", provider="youtube", created_at=created_at, game_id=game_id)
    session.add(playlist)
    session.flush()
    track = Track(
        playlist_id=playlist.id,
        title="Titre",
        artist="Artiste",
        youtube_video_id=video_id,
        duration_seconds=100,
    )
    session.add(track)
    session.commit()
    session.refresh(playlist)
    session.refresh(track)
    return playlist, track


class TestPruneStalePlaylists:
    def test_deletes_playlist_older_than_retention(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        old_date = datetime.now(timezone.utc) - timedelta(days=45)
        playlist, _ = _make_playlist_with_track(db, created_at=old_date)
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py"]
        prune_module.main()

        db = SessionLocal()
        assert db.query(Playlist).filter(Playlist.id == playlist.id).first() is None
        assert db.query(Track).count() == 0
        db.close()

    def test_keeps_playlist_within_retention_window(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        recent_date = datetime.now(timezone.utc) - timedelta(days=5)
        playlist, _ = _make_playlist_with_track(db, created_at=recent_date)
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py"]
        prune_module.main()

        db = SessionLocal()
        assert db.query(Playlist).filter(Playlist.id == playlist.id).first() is not None
        db.close()

    def test_dry_run_deletes_nothing(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        old_date = datetime.now(timezone.utc) - timedelta(days=45)
        playlist, _ = _make_playlist_with_track(db, created_at=old_date)
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py", "--dry-run"]
        prune_module.main()

        db = SessionLocal()
        assert db.query(Playlist).filter(Playlist.id == playlist.id).first() is not None
        db.close()

    def test_never_touches_match_cache(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        old_date = datetime.now(timezone.utc) - timedelta(days=45)
        _make_playlist_with_track(db, created_at=old_date)
        db.add(MatchCache(isrc="ISRC1", youtube_video_id="v1", duration_seconds=100))
        db.commit()
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py"]
        prune_module.main()

        db = SessionLocal()
        assert db.query(MatchCache).filter(MatchCache.isrc == "ISRC1").first() is not None
        db.close()

    def test_nulls_current_track_id_before_deleting_referenced_track(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        old_date = datetime.now(timezone.utc) - timedelta(days=45)
        playlist, track = _make_playlist_with_track(db, created_at=old_date)
        playlist_id = playlist.id
        game = Game(code="ABCDEF", phase="ended", current_track_id=track.id)
        db.add(game)
        db.commit()
        game_id = game.id
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py"]
        prune_module.main()

        db = SessionLocal()
        refreshed_game = db.query(Game).filter(Game.id == game_id).first()
        assert refreshed_game.current_track_id is None
        assert db.query(Playlist).filter(Playlist.id == playlist_id).first() is None
        db.close()

    def test_custom_days_threshold(self, prune_engine, prune_module):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prune_engine)
        db = SessionLocal()
        ten_days_old = datetime.now(timezone.utc) - timedelta(days=10)
        playlist, _ = _make_playlist_with_track(db, created_at=ten_days_old)
        db.close()

        sys.argv = ["prune_stale_blindtest_playlists.py", "--days", "7"]
        prune_module.main()

        db = SessionLocal()
        assert db.query(Playlist).filter(Playlist.id == playlist.id).first() is None
        db.close()
