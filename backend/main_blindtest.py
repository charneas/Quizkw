"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1). Mirroir de `main_games.py` pour la forme (APIRouter, Depends(get_db),
limiter) mais branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.blindtest import matching, schemas
from app.blindtest.database import get_db
from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.import_pipeline import extract_tracks
from app.blindtest.models import Playlist, Track
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


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
