"""Provider Apple Music — extraction de playlist publique via l'API Apple
Music, authentifiée par un developer token JWT (ES256), pas d'OAuth
utilisateur (FR1). Le JWT est signé une fois puis mis en cache en mémoire
process (valide jusqu'à 6 mois) — voir Design Notes de la spec.

Détection : host `music.apple.com`, chemin contenant `/playlist/`.
"""
import os
import re
import time
from typing import List, Optional
from urllib.parse import urlparse

import httpx
import jwt

from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack

_PLAYLIST_ID_RE = re.compile(r"/playlist/[^/]+/(pl\.[A-Za-z0-9]+)")
_API_BASE = "https://api.music.apple.com/v1/catalog/us/playlists"

# JWT valide jusqu'à 6 mois (limite Apple) ; on le régénère un peu avant par
# prudence plutôt que d'attendre un rejet 401 côté API.
_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 150

_cached_token: Optional[str] = None
_cached_token_expiry: float = 0.0


def matches(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("music.apple.com")


def _extract_playlist_id(url: str) -> str:
    parsed = urlparse(url)
    m = _PLAYLIST_ID_RE.search(parsed.path)
    if not m:
        raise UnrecognizedUrlError("URL Apple Music reconnue mais ce n'est pas un lien de playlist")
    return m.group(1)


def _get_developer_token() -> str:
    global _cached_token, _cached_token_expiry

    if _cached_token and time.time() < _cached_token_expiry:
        return _cached_token

    key_id = os.getenv("APPLE_MUSIC_KEY_ID")
    team_id = os.getenv("APPLE_MUSIC_TEAM_ID")
    private_key = os.getenv("APPLE_MUSIC_PRIVATE_KEY")
    if not key_id or not team_id or not private_key:
        raise ProviderConfigError(
            "apple_music",
            "APPLE_MUSIC_KEY_ID/APPLE_MUSIC_TEAM_ID/APPLE_MUSIC_PRIVATE_KEY",
        )

    # Le .p8 stocké en variable d'env perd souvent ses vrais retours à la
    # ligne (échappés en "\n" côté shell/plateforme de déploiement) — on les
    # restaure avant de passer la clé au signeur ES256.
    private_key = private_key.replace("\\n", "\n")

    now = int(time.time())
    try:
        token = jwt.encode(
            {"iss": team_id, "iat": now, "exp": now + _TOKEN_TTL_SECONDS},
            private_key,
            algorithm="ES256",
            headers={"kid": key_id},
        )
    except (ValueError, jwt.PyJWTError) as exc:
        raise ProviderConfigError(
            "apple_music",
            f"APPLE_MUSIC_PRIVATE_KEY invalide ({exc})",
        )

    _cached_token = token
    _cached_token_expiry = now + _TOKEN_TTL_SECONDS - 60
    return token


def fetch_tracks(url: str) -> List[ExtractedTrack]:
    playlist_id = _extract_playlist_id(url)
    token = _get_developer_token()

    headers = {"Authorization": f"Bearer {token}"}
    params = {"include": "tracks"}

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{_API_BASE}/{playlist_id}", headers=headers, params=params)
        if resp.status_code in (403, 404):
            raise PrivatePlaylistError("Playlist Apple Music privée, introuvable ou supprimée")
        resp.raise_for_status()
        payload = resp.json()

    data = payload.get("data") or []
    if not data:
        raise PrivatePlaylistError("Playlist Apple Music privée, introuvable ou vide")

    relationships = data[0].get("relationships") or {}
    items = (relationships.get("tracks") or {}).get("data") or []

    tracks: List[ExtractedTrack] = []
    for item in items:
        attrs = item.get("attributes") or {}
        title = attrs.get("name")
        artist = attrs.get("artistName")
        if not title or not artist:
            continue
        tracks.append(ExtractedTrack(
            title=title,
            artist=artist,
            isrc=attrs.get("isrc"),
        ))

    if not tracks:
        raise PrivatePlaylistError("Playlist Apple Music privée, introuvable ou vide")

    return tracks
