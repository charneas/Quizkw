"""Provider Deezer — extraction de playlist publique, sans authentification
(l'API Deezer expose les playlists publiques anonymement).

Détection : host `deezer.com` (ou `www.deezer.com`), chemin
`/playlist/{id}` ou `/{locale}/playlist/{id}` (ex. `/fr/playlist/{id}`).

Spécificité Deezer : l'API répond toujours HTTP 200, y compris en erreur
(playlist introuvable/privée) — l'erreur se détecte via la clé top-level
`"error"` du corps JSON, jamais via le status code.
"""
import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from app.blindtest.errors import PrivatePlaylistError, ProviderUnavailableError, UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack

_PLAYLIST_PATH_RE = re.compile(r"^/(?:[a-z]{2}/)?playlist/(\d+)/?$")

_API_BASE = "https://api.deezer.com"
_MAX_PAGES = 50


def matches(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    if not (host == "deezer.com" or host.endswith(".deezer.com")):
        return False
    return bool(_PLAYLIST_PATH_RE.match(parsed.path))


def _extract_playlist_id(url: str) -> str:
    parsed = urlparse(url)
    m = _PLAYLIST_PATH_RE.match(parsed.path)
    if not m:
        raise UnrecognizedUrlError("URL Deezer reconnue mais ce n'est pas un lien de playlist")
    return m.group(1)


# Codes d'erreur (dans le corps) de l'API Deezer qui signalent une panne ou un
# quota côté service, pas une playlist introuvable/privée : 4 = quota,
# 700 = service occupé.
_UNAVAILABLE_ERROR_CODES = {4, 700}


def fetch_tracks(url: str) -> List[ExtractedTrack]:
    playlist_id = _extract_playlist_id(url)

    with httpx.Client(timeout=10.0) as client:
        tracks: List[ExtractedTrack] = []
        next_url: Optional[str] = f"{_API_BASE}/playlist/{playlist_id}/tracks"

        page_count = 0
        while next_url:
            page_count += 1
            if page_count > _MAX_PAGES:
                raise PrivatePlaylistError("Playlist Deezer : trop de pages, extraction interrompue")

            try:
                resp = client.get(next_url)
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError("deezer", f"erreur réseau ({type(exc).__name__})") from exc

            # Deezer répond normalement toujours 200 (erreurs dans le corps),
            # mais un 5xx/429 de son frontal reste une panne côté service.
            if not 200 <= resp.status_code < 300:
                raise ProviderUnavailableError("deezer", f"HTTP {resp.status_code}")

            try:
                payload = resp.json()
            except ValueError as exc:
                raise ProviderUnavailableError("deezer", "réponse non JSON") from exc

            # Deezer répond toujours HTTP 200 — l'erreur se lit dans le corps.
            if not isinstance(payload, dict):
                raise ProviderUnavailableError("deezer", "réponse invalide")
            if "error" in payload:
                error = payload["error"]
                code = error.get("code") if isinstance(error, dict) else None
                if code in _UNAVAILABLE_ERROR_CODES:
                    raise ProviderUnavailableError("deezer", f"erreur API {code}")
                raise PrivatePlaylistError("Playlist Deezer introuvable ou privée")

            for item in payload.get("data", []):
                if not isinstance(item, dict):
                    continue
                title = item.get("title")
                raw_artist = item.get("artist")
                artist = raw_artist.get("name") if isinstance(raw_artist, dict) else None
                if not title or not artist:
                    continue
                tracks.append(ExtractedTrack(
                    title=title,
                    artist=artist,
                    isrc=item.get("isrc"),
                    source_url=item.get("link"),
                ))

            next_url = payload.get("next")

        if not tracks:
            raise PrivatePlaylistError("Playlist Deezer introuvable, privée ou vide")

        return tracks
