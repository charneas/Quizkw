"""Modèles SQLAlchemy du module blindtest — Story 1.1/1.2/1.3/2.1.

`MatchCache` (Story 1.3) persiste les résolutions déjà réussies (par ISRC ou
par `(title, artist)` normalisé) pour éviter de re-solliciter les providers
sur un morceau déjà connu. `Game` (Story 2.1) ne porte que le strict
nécessaire au lobby (code, phase) — `Round`/`Score` restent hors scope ici,
voir spec-2-1-lobby-connexion-partie.md § Design Notes.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.blindtest.database import Base


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String, nullable=False)
    provider = Column(String, nullable=False)  # "deezer" | "youtube" (anciennes lignes : "spotify", provider retiré)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Story 2.2 : scoping optionnel à une partie. `game_id` nul == pot
    # anonyme d'Epic 1 (comportement inchangé) ; renseigné == playlist
    # apportée par `owner_pseudo` dans le lobby de cette partie. Les deux
    # colonnes sont toujours ensemble nulles ou toutes deux renseignées
    # (validé côté requête, pas en contrainte DB — cf. spec Design Notes).
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True)
    owner_pseudo = Column(String, nullable=True)

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
    # Story 2.3 : durée de la vidéo YouTube résolue (`videos.list`), en
    # secondes. `NULL` tant qu'elle n'a pas encore été récupérée (ou en cas
    # d'échec `videos.list` — jamais retenté automatiquement) ; un morceau
    # avec `youtube_video_id` renseigné mais `duration_seconds` nul reste
    # inéligible au tirage de round (Story 2.4).
    duration_seconds = Column(Integer, nullable=True)
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
    # Story 2.3 : durée en secondes, mémorisée aux côtés du `youtube_video_id`
    # pour qu'un cache-hit serve aussi la durée sans nouvel appel
    # `videos.list`. Peut rester `NULL` sur une ligne dont le `videos.list`
    # a échoué au moment de la résolution (pas de retry automatique).
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Game(Base):
    """Une partie de blind test (Story 2.1) : juste un code + une phase.

    Pas de FK vers `Playlist`/`Track` ni de colonne joueurs ici — la
    présence est dérivée des sockets ouverts (voir `game_connections.py`),
    aucun `Player` DB table tant que rien ne nécessite un état survivant à
    une connexion (cf. Design Notes de la spec).

    Story 2.4 : `host_pseudo` (le premier pseudo à rejoindre le lobby WS de
    cette partie, jamais réassigné ensuite — survit à une reconnexion sous
    le même pseudo puisque c'est une colonne DB, pas un état lié à un
    socket) et `current_track_id` (morceau tiré au dernier `start_game`).
    """
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    phase = Column(String, nullable=False, default="lobby")
    host_pseudo = Column(String, nullable=True)
    current_track_id = Column(Integer, ForeignKey("tracks.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
