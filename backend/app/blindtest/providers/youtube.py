"""Provider YouTube — extraction de playlist publique via YouTube Data API
(clé API applicative — FR1). Chaque item de playlist EST déjà une vidéo
YouTube : `youtube_video_id` est peuplé directement, aucun matching requis
(contrairement à Spotify/Apple Music, résolus en Story 1.2).

Détection : host `youtube.com`/`www.youtube.com`/`m.youtube.com`/`youtu.be`/
`music.youtube.com` avec un paramètre `list=` — une playlist YouTube Music
partage le même identifiant de playlist et la même API `playlistItems.list`
qu'une playlist YouTube classique, aucune branche d'extraction distincte
n'est nécessaire.
"""
import os
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

import httpx

from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack

_API_BASE = "https://www.googleapis.com/youtube/v3/playlistItems"

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
_PAGE_SIZE = 50
_MAX_PAGES = 50

# Public : nombre max de morceaux réellement importés avant troncature
# silencieuse (cf. `fetch_tracks`). Exposé pour que le schéma de réponse
# (`PlaylistResponse.truncated`) puisse détecter ce cas sans dupliquer la
# constante.
MAX_TRACKS = _MAX_PAGES * _PAGE_SIZE


def matches(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    if host not in _YOUTUBE_HOSTS:
        return False
    return "list" in parse_qs(parsed.query)


def _extract_playlist_id(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    list_ids = qs.get("list")
    if not list_ids or not list_ids[0]:
        raise UnrecognizedUrlError("URL YouTube reconnue mais sans identifiant de playlist (`list=`)")
    return list_ids[0]


def fetch_tracks(url: str) -> List[ExtractedTrack]:
    playlist_id = _extract_playlist_id(url)

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ProviderConfigError("youtube", "YOUTUBE_API_KEY")

    tracks: List[ExtractedTrack] = []
    page_token: Optional[str] = None

    with httpx.Client(timeout=10.0) as client:
        page_count = 0
        while True:
            page_count += 1
            if page_count > _MAX_PAGES:
                # Garde-fou contre une pagination qui ne se termine jamais
                # (bug API, ou playlist réellement énorme type "Titres
                # likés" avec des milliers d'entrées) : tronquer plutôt
                # qu'échouer entièrement — 2500 morceaux (50 pages x 50) est
                # déjà largement suffisant pour alimenter des parties de
                # blind test, jeter tout l'import pour ce seul dépassement
                # pénalisait sans raison les grosses bibliothèques légitimes.
                break
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": _PAGE_SIZE,
                "key": api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = client.get(_API_BASE, params=params)
            if resp.status_code in (403, 404):
                raise PrivatePlaylistError("Playlist YouTube privée, introuvable ou supprimée")
            resp.raise_for_status()
            payload = resp.json()

            for item in payload.get("items", []):
                snippet = item.get("snippet") or {}
                title = snippet.get("title")
                video_id = (snippet.get("resourceId") or {}).get("videoId")
                if not title or not video_id:
                    continue
                if title in ("Private video", "Deleted video"):
                    continue  # item retiré/privé dans une playlist par ailleurs publique
                tracks.append(ExtractedTrack(
                    title=title,
                    artist=snippet.get("videoOwnerChannelTitle") or "",
                    youtube_video_id=video_id,
                ))

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        if not tracks:
            # Playlist vide OU playlist privée que l'API a quand même répondu
            # 200 pour (comportement observé de playlistItems.list) — on ne
            # peut pas distinguer les deux ici sans appel supplémentaire, donc
            # on traite prudemment "aucun morceau retourné" comme un échec
            # plutôt que de persister une Playlist vide silencieusement.
            raise PrivatePlaylistError("Playlist YouTube privée, introuvable ou vide")

        return tracks
