"""Provider SoundCloud — extraction de set public via Client Credentials
(app-level auth, pas d'OAuth utilisateur).

Détection : host `soundcloud.com` (ou `www.soundcloud.com`), chemin
`/{user}/sets/{slug}`.

Spécificité SoundCloud API v2 : l'en-tête d'autorisation est
`Authorization: OAuth <token>` (pas `Bearer` comme Spotify).
"""
import os
import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack

_SET_PATH_RE = re.compile(r"^/[^/]+/sets/[^/]+/?$")

_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"
_RESOLVE_URL = "https://api-v2.soundcloud.com/resolve"
_MAX_PAGES = 50


def matches(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    if not (host == "soundcloud.com" or host.endswith(".soundcloud.com")):
        return False
    return bool(_SET_PATH_RE.match(parsed.path))


def _get_app_token(client: httpx.Client) -> str:
    client_id = os.getenv("SOUNDCLOUD_CLIENT_ID")
    client_secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ProviderConfigError("soundcloud", "SOUNDCLOUD_CLIENT_ID/SOUNDCLOUD_CLIENT_SECRET")

    try:
        resp = client.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    except httpx.HTTPError as exc:
        raise ProviderConfigError(
            "soundcloud", "erreur réseau lors de l'authentification SoundCloud"
        ) from exc
    if resp.status_code != 200:
        raise ProviderConfigError(
            "soundcloud", "SOUNDCLOUD_CLIENT_ID/SOUNDCLOUD_CLIENT_SECRET (rejetés par SoundCloud)"
        )
    try:
        return resp.json()["access_token"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderConfigError(
            "soundcloud", "réponse SoundCloud invalide lors de l'authentification"
        ) from exc


def _track_from_item(item: Optional[dict]) -> Optional[ExtractedTrack]:
    if not item:
        return None
    title = item.get("title")
    publisher_metadata = item.get("publisher_metadata") or {}
    artist = publisher_metadata.get("artist")
    if not artist:
        user = item.get("user") or {}
        artist = user.get("username")
    if not title or not artist:
        return None
    return ExtractedTrack(
        title=title,
        artist=artist,
        source_url=item.get("permalink_url"),
    )


def fetch_tracks(url: str) -> List[ExtractedTrack]:
    with httpx.Client(timeout=10.0) as client:
        token = _get_app_token(client)
        headers = {"Authorization": f"OAuth {token}"}

        try:
            resp = client.get(_RESOLVE_URL, headers=headers, params={"url": url})
        except httpx.HTTPError as exc:
            raise ProviderConfigError(
                "soundcloud", "erreur réseau lors de la résolution du set SoundCloud"
            ) from exc
        if resp.status_code in (403, 404):
            raise PrivatePlaylistError("Set SoundCloud privé, introuvable ou supprimé")
        if resp.status_code < 200 or resp.status_code >= 300:
            raise PrivatePlaylistError("Set SoundCloud privé, introuvable ou supprimé")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderConfigError(
                "soundcloud", "réponse SoundCloud invalide lors de la résolution du set"
            ) from exc

        tracks: List[ExtractedTrack] = []
        items = payload.get("tracks") or []
        for item in items:
            track = _track_from_item(item)
            if track:
                tracks.append(track)

        next_href: Optional[str] = payload.get("next_href")
        page_count = 0
        while next_href:
            page_count += 1
            if page_count > _MAX_PAGES:
                raise PrivatePlaylistError("Set SoundCloud : trop de pages, extraction interrompue")

            try:
                resp = client.get(next_href, headers=headers)
            except httpx.HTTPError as exc:
                raise ProviderConfigError(
                    "soundcloud", "erreur réseau lors de la pagination du set SoundCloud"
                ) from exc
            if resp.status_code in (403, 404):
                raise PrivatePlaylistError("Set SoundCloud privé, introuvable ou supprimé")
            if resp.status_code < 200 or resp.status_code >= 300:
                raise PrivatePlaylistError("Set SoundCloud privé, introuvable ou supprimé")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ProviderConfigError(
                    "soundcloud", "réponse SoundCloud invalide lors de la pagination du set"
                ) from exc

            for item in payload.get("collection") or payload.get("tracks") or []:
                track = _track_from_item(item)
                if track:
                    tracks.append(track)

            next_href = payload.get("next_href")

        if not tracks:
            raise PrivatePlaylistError("Set SoundCloud privé, introuvable ou vide")

        return tracks
