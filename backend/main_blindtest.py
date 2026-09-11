"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1). Mirroir de `main_games.py` pour la forme (APIRouter, Depends(get_db),
limiter) mais branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.blindtest import schemas
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
        ))

    db.commit()
    db.refresh(playlist)
    return playlist
