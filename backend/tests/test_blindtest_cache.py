"""Tests de la Story 1.3 (cache de matching entre imports) — matrice I/O de
`spec-1-3-cache-matching-imports.md`.

Couvre `normalize_key` (casing/accents/ponctuation/feat.) et `lookup`/`store`
(priorité ISRC, dédup, upsert-safe) sur une DB SQLite en mémoire dédiée.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blindtest import cache
from app.blindtest.database import Base
from app.blindtest.models import MatchCache


class TestNormalizeKey:
    def test_case_insensitive(self):
        assert cache.normalize_key("Song Title", "Some Artist") == cache.normalize_key("song title", "SOME ARTIST")

    def test_accents_stripped(self):
        assert cache.normalize_key("Éphémère", "Beyoncé") == cache.normalize_key("Ephemere", "Beyonce")

    def test_punctuation_stripped(self):
        assert cache.normalize_key("Don't Stop!", "AC/DC") == cache.normalize_key("Don t Stop", "AC DC")

    def test_feat_mention_dropped(self):
        assert cache.normalize_key("Song (feat. Other Artist)", "Main Artist") == cache.normalize_key("Song", "Main Artist")
        assert cache.normalize_key("Song ft. Other", "Main Artist") == cache.normalize_key("Song", "Main Artist")

    def test_different_songs_produce_different_keys(self):
        assert cache.normalize_key("Song A", "Artist") != cache.normalize_key("Song B", "Artist")


@pytest.fixture
def cache_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


class TestLookupAndStore:
    def test_store_then_lookup_by_isrc(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-1", "Title", "Artist", "vid1")
        result = cache.lookup(db, "ISRC-1", "Title", "Artist")
        assert result == ("vid1", None)

    def test_store_then_lookup_by_normalized_title_artist(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, None, "Song Title", "Some Artist", "vid2")
        result = cache.lookup(db, None, "SONG TITLE", "some artist")
        assert result == ("vid2", None)

    def test_isrc_takes_priority_over_normalized_key(self, cache_session_factory):
        db = cache_session_factory()
        # Deux entrées distinctes : une par ISRC, une par clé normalisée
        # différente. Un lookup avec l'ISRC ET un title/artist qui NE
        # matcherait PAS la ligne ISRC doit quand même renvoyer la valeur ISRC.
        cache.store(db, "ISRC-X", "Ignored Title", "Ignored Artist", "vid-isrc")
        cache.store(db, None, "Other Song", "Other Artist", "vid-normalized")
        result = cache.lookup(db, "ISRC-X", "Other Song", "Other Artist")
        assert result == ("vid-isrc", None)

    def test_store_with_duration_then_lookup_returns_duration(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-DUR", "Title", "Artist", "vid-dur", duration_seconds=210)
        result = cache.lookup(db, "ISRC-DUR", "Title", "Artist")
        assert result == ("vid-dur", 210)

    def test_store_without_duration_then_lookup_returns_none_duration(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-NO-DUR", "Title", "Artist", "vid-no-dur")
        result = cache.lookup(db, "ISRC-NO-DUR", "Title", "Artist")
        assert result == ("vid-no-dur", None)

    def test_store_existing_row_missing_duration_gets_duration_backfilled_without_overwrite(self, cache_session_factory):
        """Chemin `match_playlist_tracks` : ligne existante avec
        `youtube_video_id` déjà connu mais durée manquante — `store` doit
        pouvoir compléter juste la durée sans passer par `overwrite=True`."""
        db = cache_session_factory()
        cache.store(db, "ISRC-BACKFILL", "Title", "Artist", "vid-x")
        cache.store(db, "ISRC-BACKFILL", "Title", "Artist", "vid-x", duration_seconds=333)
        result = cache.lookup(db, "ISRC-BACKFILL", "Title", "Artist")
        assert result == ("vid-x", 333)

    def test_store_none_duration_does_not_erase_existing_duration(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-KEEP", "Title", "Artist", "vid-y", duration_seconds=400)
        cache.store(db, "ISRC-KEEP", "Title", "Artist", "vid-y", duration_seconds=None)
        result = cache.lookup(db, "ISRC-KEEP", "Title", "Artist")
        assert result == ("vid-y", 400)

    def test_store_existing_row_missing_duration_gets_duration_backfilled_without_overwrite_normalized_key(
        self, cache_session_factory
    ):
        """Même comportement que le test isrc, mais sur la branche clé
        normalisée (pas d'isrc) — `store` doit pouvoir compléter juste la
        durée sans `overwrite=True`."""
        db = cache_session_factory()
        cache.store(db, None, "Title Norm", "Artist Norm", "vid-x-norm")
        cache.store(db, None, "Title Norm", "Artist Norm", "vid-x-norm", duration_seconds=333)
        result = cache.lookup(db, None, "Title Norm", "Artist Norm")
        assert result == ("vid-x-norm", 333)

    def test_store_none_duration_does_not_erase_existing_duration_normalized_key(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, None, "Title Keep", "Artist Keep", "vid-y-norm", duration_seconds=400)
        cache.store(db, None, "Title Keep", "Artist Keep", "vid-y-norm", duration_seconds=None)
        result = cache.lookup(db, None, "Title Keep", "Artist Keep")
        assert result == ("vid-y-norm", 400)

    def test_lookup_miss_returns_none(self, cache_session_factory):
        db = cache_session_factory()
        assert cache.lookup(db, "UNKNOWN", "Nope", "Nobody") is None

    def test_spelling_variants_share_same_cache_key(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, None, "Café del Mar", "Énergie!", "vid3")
        result = cache.lookup(db, None, "cafe del mar", "energie")
        assert result == ("vid3", None)

    def test_store_does_not_duplicate_existing_isrc_row(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-DUP", "Title", "Artist", "vid-first")
        cache.store(db, "ISRC-DUP", "Title", "Artist", "vid-second")
        rows = db.query(MatchCache).filter(MatchCache.isrc == "ISRC-DUP").all()
        assert len(rows) == 1
        assert rows[0].youtube_video_id == "vid-first"

    def test_store_does_not_duplicate_existing_normalized_row(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, None, "Title", "Artist", "vid-first")
        cache.store(db, None, "TITLE", "artist", "vid-second")
        rows = db.query(MatchCache).filter(MatchCache.normalized_key == cache.normalize_key("Title", "Artist")).all()
        assert len(rows) == 1
        assert rows[0].youtube_video_id == "vid-first"

    def test_store_with_falsy_video_id_is_noop(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, "ISRC-Y", "Title", "Artist", "")
        assert db.query(MatchCache).count() == 0

    def test_store_does_not_commit(self, cache_session_factory):
        """`store` doit seulement `add`/`flush`, jamais `commit` — c'est aux
        appelants (`matching.py`, `main_blindtest.py`) de commiter, pour ne
        pas casser l'invariant "pas d'écriture partielle" de
        `import_playlist` (voir spec-1-3, section Implementation Notes)."""
        db = cache_session_factory()
        with patch.object(db, "commit", wraps=db.commit) as commit_spy:
            cache.store(db, "ISRC-NO-COMMIT", "Title", "Artist", "vid1")
            commit_spy.assert_not_called()
        # La ligne existe bien dans la session (add + flush), mais reste
        # dans la transaction ouverte tant que personne n'a commité.
        assert db.query(MatchCache).filter(MatchCache.isrc == "ISRC-NO-COMMIT").first() is not None
        assert db.in_transaction()

    def test_store_overwrite_true_updates_existing_isrc_row(self, cache_session_factory):
        """`overwrite=True` (chemin correction admin `resolve_track`) doit
        écraser la valeur existante, contrairement au défaut no-op."""
        db = cache_session_factory()
        cache.store(db, "ISRC-OVERWRITE", "Title", "Artist", "vid-old")
        cache.store(db, "ISRC-OVERWRITE", "Title", "Artist", "vid-new", overwrite=True)
        rows = db.query(MatchCache).filter(MatchCache.isrc == "ISRC-OVERWRITE").all()
        assert len(rows) == 1
        assert rows[0].youtube_video_id == "vid-new"

    def test_store_overwrite_true_updates_existing_normalized_row(self, cache_session_factory):
        db = cache_session_factory()
        cache.store(db, None, "Title", "Artist", "vid-old")
        cache.store(db, None, "TITLE", "artist", "vid-new", overwrite=True)
        rows = db.query(MatchCache).filter(MatchCache.normalized_key == cache.normalize_key("Title", "Artist")).all()
        assert len(rows) == 1
        assert rows[0].youtube_video_id == "vid-new"

    def test_store_race_condition_is_absorbed_as_noop(self, cache_session_factory):
        """Deux résolutions concurrentes du même morceau peuvent toutes deux
        passer le check d'existence avant qu'aucune n'ait été persistée,
        puis entrer en conflit sur la contrainte unique au flush. `store`
        doit absorber l'`IntegrityError` (rollback du seul savepoint de
        l'insert) sans propager d'exception ni dupliquer la ligne, et sans
        casser le reste de la session appelante."""
        db = cache_session_factory()

        # Un autre writer a déjà gagné la course : sa ligne est déjà
        # persistée en base directement (bypass du check d'existence de
        # `store`, pour simuler le TOCTOU entre deux sessions).
        db.execute(
            MatchCache.__table__.insert().values(
                isrc="ISRC-RACE", normalized_key=None, youtube_video_id="vid-winner"
            )
        )
        db.commit()

        class _AlwaysMissQuery:
            """Simule le check d'existence de `store` qui rate la ligne déjà
            commitée par l'autre writer (fenêtre de course)."""

            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return None

        with patch.object(db, "query", return_value=_AlwaysMissQuery()):
            cache.store(db, "ISRC-RACE", "Title", "Artist", "vid-loser")

        # La session reste utilisable après l'absorption de l'IntegrityError
        # (rollback du savepoint uniquement, pas de toute la transaction).
        rows = db.query(MatchCache).filter(MatchCache.isrc == "ISRC-RACE").all()
        assert len(rows) == 1
        assert rows[0].youtube_video_id == "vid-winner"
