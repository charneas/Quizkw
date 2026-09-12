"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1). Mirroir de `main_games.py` pour la forme (APIRouter, Depends(get_db),
limiter) mais branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin_session
from app.blindtest import cache, matching, schemas
from app.blindtest.database import get_db
from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.import_pipeline import extract_tracks
from app.blindtest.models import Playlist, Track
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Réconciliation manuelle admin des morceaux non trouvés (spec
# spec-blindtest-admin-reconciliation.md) : même garde `require_admin_session`
# que les autres routes `/admin/*` (AD-17), branché sur la DB isolée
# blindtest (jamais de jointure/lecture croisée avec la DB principale).
admin_router = APIRouter(
    prefix="/admin/blindtest",
    tags=["Admin"],
    dependencies=[Depends(require_admin_session)],
)


@router.post("/blindtest/playlists", response_model=schemas.PlaylistResponse, status_code=201)
@limiter.limit("10/minute")
def import_playlist(
    request: Request,
    body: schemas.PlaylistImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Extrait une playlist publique (Spotify/YouTube/Apple Music) et
    persiste `Playlist` + `Track`. Échec propre sans écriture partielle :
    l'extraction complète a lieu avant tout `db.add`/`db.commit`."""
    try:
        provider, extracted = extract_tracks(body.url)
    except UnrecognizedUrlError:
        raise HTTPException(status_code=400, detail="URL de playlist non reconnue")
    except PrivatePlaylistError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProviderConfigError as exc:
        logger.error("Configuration provider manquante: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    playlist = Playlist(source_url=body.url, provider=provider)
    db.add(playlist)
    db.flush()  # obtenir playlist.id pour les FK des tracks, avant commit

    for item in extracted:
        db.add(Track(
            playlist_id=playlist.id,
            title=item.title,
            artist=item.artist,
            isrc=item.isrc,
            youtube_video_id=item.youtube_video_id,
            source_url=item.source_url,
        ))
        if item.youtube_video_id:
            # Import direct YouTube : le morceau est déjà résolu, on
            # alimente le cache tout de suite pour qu'un futur import
            # Spotify/Apple Music du même morceau tape le cache (Story 1.3).
            cache.store(db, item.isrc, item.title, item.artist, item.youtube_video_id)

    db.commit()
    db.refresh(playlist)

    background_tasks.add_task(matching.match_playlist_tracks, playlist.id)

    return playlist


@router.get("/blindtest/playlists/{playlist_id}", response_model=schemas.PlaylistResponse)
def get_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Permet au client de poller l'état de résolution (matching en tâche de
    fond) d'une playlist déjà importée."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    return playlist


@admin_router.get("/tracks/unresolved", response_model=List[schemas.UnresolvedTrackResponse])
def list_unresolved_tracks(db: Session = Depends(get_db)):
    """Liste, toutes playlists confondues, les morceaux jamais résolus par
    le matching automatique (`youtube_video_id IS NULL`) — pas de
    pagination (hors scope, cf. spec, pattern `AdminPropositions`)."""
    tracks = (
        db.query(Track)
        .join(Playlist, Track.playlist_id == Playlist.id)
        .options(joinedload(Track.playlist))
        .filter(Track.youtube_video_id.is_(None))
        .order_by(Track.id)
        .all()
    )
    return [
        schemas.UnresolvedTrackResponse(
            id=track.id,
            title=track.title,
            artist=track.artist,
            isrc=track.isrc,
            source_url=track.source_url,
            playlist_id=track.playlist_id,
            playlist_provider=track.playlist.provider,
        )
        for track in tracks
    ]


@admin_router.put("/tracks/{track_id}", response_model=schemas.TrackResponse)
def resolve_track(track_id: int, body: schemas.ResolveTrackRequest, db: Session = Depends(get_db)):
    """Résolution manuelle : accepte un lien YouTube complet (`watch?v=`,
    `youtu.be/`) ou un videoId nu (`extract_video_id`, partagé avec le
    matching automatique). Écrase toute valeur déjà présente (cas de
    correction — pas de restriction "null uniquement", cf. matrice I/O).
    Écrit aussi `MatchCache` (même priorité isrc puis clé normalisée que
    `cache.store`) pour que les imports futurs du même morceau bénéficient
    de cette résolution (FR3)."""
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Morceau introuvable")

    video_id = matching.extract_video_id(body.youtube_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Lien YouTube ou identifiant de vidéo invalide")

    track.youtube_video_id = video_id
    cache.store(db, track.isrc, track.title, track.artist, video_id, overwrite=True)
    db.commit()
    db.refresh(track)
    return track
