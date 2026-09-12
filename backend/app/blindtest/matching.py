"""Matching automatique vers YouTube (Story 1.2) — résout, pour chaque
`Track` non-YouTube d'une playlist (`youtube_video_id IS NULL`), un
`youtube_video_id` jouable en blind-test.

Ordre : cache (`cache.lookup`, Story 1.3) en tout premier lieu, puis
`idonthavespotify` (self-hosted, pas de quota) en primaire, puis YouTube Data
API `search.list` (quota ~100/jour) en dernier repli, uniquement si le cache
et le primaire échouent/ratent/ne renvoient rien d'exploitable. Toute
résolution réussie est écrite dans `MatchCache` (`cache.store`) pour que les
imports suivants du même morceau ne rappellent plus jamais un provider (FR3).

Tourne en `BackgroundTasks` (planifié par `main_blindtest.py` juste après le
commit de l'import) — ouvre sa PROPRE session (`SessionLocal()`), jamais la
session request-scoped de l'endpoint, dont la durée de vie n'est pas garantie
après l'envoi de la réponse.

IMPORTANT (cf. Spec Change Log — bug corrigé) : `resolve_track_video_id` lit
`track.source_url` (le lien du morceau lui-même) — JAMAIS
`track.playlist.source_url` (le lien de la playlist), qui donnerait le même
lien à tous les morceaux et ne peut pas résoudre correctement.
"""
import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

from app.blindtest import cache
from app.blindtest.database import SessionLocal
from app.blindtest.models import Track

logger = logging.getLogger(__name__)

_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

# Un videoId YouTube fait toujours exactement 11 caractères
# alphanumériques/`-`/`_` (cf. admin de réconciliation manuelle, qui accepte
# un videoId nu en plus d'un lien complet).
_BARE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(youtube_url: str) -> Optional[str]:
    """Extrait un `videoId` YouTube depuis, dans l'ordre : un lien
    `?v=<id>` (`watch?v=`), un lien court `youtu.be/<id>`, ou un `videoId`
    nu (11 caractères, aucun schéma/host) — ce dernier cas sert à la
    réconciliation manuelle admin (Story de reconciliation), qui accepte de
    coller directement l'identifiant sans lien complet."""
    youtube_url = youtube_url.strip()
    try:
        parsed = urlparse(youtube_url)
        qs = parse_qs(parsed.query)
    except ValueError:
        return None
    values = qs.get("v")
    if values and values[0]:
        candidate = values[0]
        return candidate if _BARE_VIDEO_ID_RE.match(candidate) else None
    if parsed.hostname == "youtu.be":
        candidate = parsed.path.lstrip("/")
        return candidate if _BARE_VIDEO_ID_RE.match(candidate) else None
    if not parsed.scheme and not parsed.netloc and _BARE_VIDEO_ID_RE.match(youtube_url):
        return youtube_url
    return None


def resolve_via_idonthavespotify(source_url: str) -> Optional[str]:
    """Tente de résoudre `source_url` (lien Spotify/Apple Music du morceau)
    en `youtube_video_id` via le service self-hosted `idonthavespotify`.
    Ne lève jamais — toute erreur (config manquante, réseau, HTTP, JSON)
    renvoie `None`."""
    base_url = os.getenv("IDONTHAVESPOTIFY_BASE_URL")
    if not base_url:
        return None

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{base_url}/api/search",
                # "v": "1" est le paramètre de version de l'API idonthavespotify (pas lié à YouTube).
                params={"v": "1"},
                json={"link": source_url, "adapters": ["youTube"]},
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("idonthavespotify: échec de résolution pour %r (%s)", source_url, exc)
        return None

    if not isinstance(payload, dict):
        return None
    links = payload.get("links") or []
    for link in links:
        if not isinstance(link, dict):
            continue
        if link.get("type") == "youTube" and not link.get("notAvailable"):
            url = link.get("url")
            if url:
                video_id = extract_video_id(url)
                if video_id:
                    return video_id
    return None


def resolve_via_youtube_search(title: str, artist: str) -> Optional[str]:
    """Repli : `YouTube Data API` `search.list` sur `{artist} {title}`.
    Ne lève jamais — renvoie `None` si non configuré ou en cas d'échec."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return None

    query = f"{artist} {title}".strip()
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                _YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 1,
                    "q": query,
                    "key": api_key,
                },
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("search.list: échec de résolution pour %r (%s)", query, exc)
        return None

    if not isinstance(payload, dict):
        return None
    items = payload.get("items") or []
    if not items or not isinstance(items[0], dict):
        return None
    id_obj = items[0].get("id")
    if not isinstance(id_obj, dict):
        return None
    video_id = id_obj.get("videoId")
    return video_id or None


def resolve_track_video_id(db, track: Track) -> Optional[str]:
    """Résout un `youtube_video_id` pour `track` : cache (`cache.lookup`) en
    tout premier lieu, puis `idonthavespotify` en primaire (uniquement si
    `track.source_url` est renseigné — jamais `track.playlist.source_url`),
    puis `search.list` en repli."""
    cached = cache.lookup(db, track.isrc, track.title, track.artist)
    if cached:
        return cached

    if track.source_url:
        video_id = resolve_via_idonthavespotify(track.source_url)
        if video_id:
            return video_id

    return resolve_via_youtube_search(track.title, track.artist)


def match_playlist_tracks(playlist_id: int) -> None:
    """Résout tous les morceaux non-YouTube (`youtube_video_id IS NULL`)
    d'une playlist. Ouvre sa propre session DB, itère et commit morceau par
    morceau ; l'échec d'un morceau n'interrompt jamais les suivants."""
    db = SessionLocal()
    try:
        tracks = (
            db.query(Track)
            .filter(Track.playlist_id == playlist_id, Track.youtube_video_id.is_(None))
            .all()
        )
        for track in tracks:
            try:
                video_id = resolve_track_video_id(db, track)
                if video_id:
                    track.youtube_video_id = video_id
                    cache.store(db, track.isrc, track.title, track.artist, video_id)
                    db.commit()
            except Exception:
                logger.exception("Matching: échec inattendu pour le morceau %s (playlist %s)", track.id, playlist_id)
                db.rollback()
    finally:
        db.close()
