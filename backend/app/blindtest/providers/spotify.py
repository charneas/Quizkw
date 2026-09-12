"""Provider Spotify — extraction de playlist publique via Client Credentials
(app-level auth, pas d'OAuth utilisateur — FR1/NFR3).

Détection : host `open.spotify.com` (ou `spotify.com`), chemin
`/playlist/{id}`.
"""
import os
import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack

_PLAYLIST_PATH_RE = re.compile(r"^/playlist/([A-Za-z0-9]+)")

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_MAX_PAGES = 50


def matches(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host == "spotify.com" or host.endswith(".spotify.com")


def _extract_playlist_id(url: str) -> str:
    parsed = urlparse(url)
    m = _PLAYLIST_PATH_RE.match(parsed.path)
    if not m:
        raise UnrecognizedUrlError("URL Spotify reconnue mais ce n'est pas un lien de playlist")
    return m.group(1)


def _get_app_token(client: httpx.Client) -> str:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ProviderConfigError("spotify", "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET")

    resp = client.post(
        _TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
    )
    if resp.status_code != 200:
        raise ProviderConfigError("spotify", "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET (rejetés par Spotify)")
    return resp.json()["access_token"]


def fetch_tracks(url: str) -> List[ExtractedTrack]:
    playlist_id = _extract_playlist_id(url)

    with httpx.Client(timeout=10.0) as client:
        token = _get_app_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        tracks: List[ExtractedTrack] = []
        next_url: Optional[str] = f"{_API_BASE}/playlists/{playlist_id}/tracks"

        page_count = 0
        while next_url:
            page_count += 1
            if page_count > _MAX_PAGES:
                raise PrivatePlaylistError("Playlist Spotify : trop de pages, extraction interrompue")

            resp = client.get(next_url, headers=headers)
            if resp.status_code in (403, 404):
                raise PrivatePlaylistError("Playlist Spotify privée, introuvable ou supprimée")
            resp.raise_for_status()
            payload = resp.json()

            for item in payload.get("items", []):
                track = item.get("track")
                if not track:
                    continue  # morceau local/indisponible, pas de metadata exploitable
                title = track.get("name")
                artists = track.get("artists") or []
                artist = ", ".join(a.get("name", "") for a in artists if a.get("name"))
                if not title or not artist:
                    continue
                external_ids = track.get("external_ids") or {}
                external_urls = track.get("external_urls") or {}
                tracks.append(ExtractedTrack(
                    title=title,
                    artist=artist,
                    isrc=external_ids.get("isrc"),
                    source_url=external_urls.get("spotify"),
                ))

            next_url = payload.get("next")

        if not tracks:
            raise PrivatePlaylistError("Playlist Spotify privée, introuvable ou vide")

        return tracks
