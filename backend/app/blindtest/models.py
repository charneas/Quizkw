"""Modèles SQLAlchemy du module blindtest — Story 1.1 seulement.

`MatchCache`/`Game`/`Round`/`Score` (mentionnés dans l'epic context) sont hors
scope ici : ajoutés par Story 1.2+.
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
