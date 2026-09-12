"""Modèles SQLAlchemy du module blindtest — Story 1.1/1.2/1.3.

`MatchCache` (Story 1.3) persiste les résolutions déjà réussies (par ISRC ou
par `(title, artist)` normalisé) pour éviter de re-solliciter les providers
sur un morceau déjà connu. `Game`/`Round`/`Score` restent hors scope ici.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.blindtest.database import Base


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String, nullable=False)
    provider = Column(String, nullable=False)  # "spotify" | "youtube" | "apple_music"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tracks = relationship("Track", back_populates="playlist", cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    isrc = Column(String, nullable=True)
    youtube_video_id = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    playlist = relationship("Playlist", back_populates="tracks")


class MatchCache(Base):
    """Cache de résolution (Story 1.3) : une ligne par morceau déjà résolu,
    clé par ISRC (priorité) ou par `(title, artist)` normalisé (repli). Ne
    stocke que le `youtube_video_id` — ce n'est pas un registre de morceaux,
    juste un cache de résolution (cf. Design Notes de la spec)."""
    __tablename__ = "match_cache"

    id = Column(Integer, primary_key=True, index=True)
    isrc = Column(String, nullable=True, unique=True)
    normalized_key = Column(String, nullable=True, unique=True)
    youtube_video_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
