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
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import httpx
from sqlalchemy import or_

from app.blindtest import cache
from app.blindtest.database import SessionLocal
from app.blindtest.models import Track

logger = logging.getLogger(__name__)

_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# Durée ISO-8601 renvoyée par `videos.list` (`contentDetails.duration`),
# forme `PT#H#M#S` — chaque groupe est optionnel (ex: "PT4M13S", "PT1H2M",
# "PT45S"), jamais de jours/semaines/mois/années pour une vidéo YouTube.
_ISO8601_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

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


def _parse_iso8601_duration(duration: str) -> Optional[int]:
    """Convertit une durée ISO-8601 `PT#H#M#S` (format
    `contentDetails.duration` de `videos.list`) en secondes. Renvoie `None`
    sur tout format inattendu — ne lève jamais."""
    if not duration:
        return None
    match = _ISO8601_DURATION_RE.match(duration.strip())
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    if hours == 0 and minutes == 0 and seconds == 0 and not any(match.groups()):
        # Aucun groupe présent du tout ("PT" nu) : pas une durée valide.
        return None
    return hours * 3600 + minutes * 60 + seconds


def fetch_video_duration(video_id: str) -> Optional[int]:
    """Récupère la durée (en secondes) d'une vidéo YouTube déjà résolue, via
    `videos.list?part=contentDetails` (quota général ~10000/jour, distinct
    du quota restreint de `search.list`, NFR2). Ne lève jamais — toute
    erreur (config manquante, réseau, HTTP, JSON, format inattendu) renvoie
    `None`."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return None

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                _YOUTUBE_VIDEOS_URL,
                params={
                    "part": "contentDetails",
                    "id": video_id,
                    "key": api_key,
                },
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("videos.list: échec de résolution de durée pour %r (%s)", video_id, exc)
        return None

    if not isinstance(payload, dict):
        return None
    items = payload.get("items") or []
    if not items or not isinstance(items[0], dict):
        return None
    content_details = items[0].get("contentDetails")
    if not isinstance(content_details, dict):
        return None
    duration = content_details.get("duration")
    if not isinstance(duration, str):
        return None
    return _parse_iso8601_duration(duration)


def resolve_track_video_id(db, track: Track) -> Tuple[Optional[str], Optional[int]]:
    """Résout un `(youtube_video_id, duration_seconds)` pour `track` : cache
    (`cache.lookup`) en tout premier lieu — renvoyé tel quel, durée
    éventuellement `None` si jamais résolue avant cette story — puis
    `idonthavespotify` en primaire (uniquement si `track.source_url` est
    renseigné — jamais `track.playlist.source_url`), puis `search.list` en
    repli. Une résolution fraîche (hors cache) déclenche un unique appel
    `fetch_video_duration` une fois le `video_id` connu (Story 2.3)."""
    cached = cache.lookup(db, track.isrc, track.title, track.artist)
    if cached:
        return cached

    video_id = None
    if track.source_url:
        video_id = resolve_via_idonthavespotify(track.source_url)

    if not video_id:
        video_id = resolve_via_youtube_search(track.title, track.artist)

    if not video_id:
        return (None, None)

    duration = fetch_video_duration(video_id)
    return (video_id, duration)


def resolve_track_duration_only(db, track: Track) -> Optional[int]:
    """Résout uniquement la durée d'un morceau qui a déjà un
    `youtube_video_id` (import YouTube direct) : consulte le cache d'abord
    (même clé ISRC/normalisée que `resolve_track_video_id`), sinon appelle
    `fetch_video_duration` directement sur le `video_id` déjà connu."""
    cached = cache.lookup(db, track.isrc, track.title, track.artist)
    if cached and cached[1] is not None and cached[0] == track.youtube_video_id:
        return cached[1]

    return fetch_video_duration(track.youtube_video_id)


def match_playlist_tracks(playlist_id: int) -> None:
    """Résout tous les morceaux d'une playlist qui n'ont pas encore un
    `youtube_video_id` OU pas encore de `duration_seconds` (Story 2.3 :
    couvre aussi les imports YouTube directs, qui arrivent déjà avec un
    `youtube_video_id` mais sans durée). Ouvre sa propre session DB, itère
    et commit morceau par morceau ; l'échec d'un morceau n'interrompt
    jamais les suivants."""
    db = SessionLocal()
    try:
        tracks = (
            db.query(Track)
            .filter(
                Track.playlist_id == playlist_id,
                or_(Track.youtube_video_id.is_(None), Track.duration_seconds.is_(None)),
            )
            .all()
        )
        for track in tracks:
            try:
                if track.youtube_video_id is None:
                    video_id, duration = resolve_track_video_id(db, track)
                    if video_id:
                        track.youtube_video_id = video_id
                        if duration is not None:
                            track.duration_seconds = duration
                        cache.store(db, track.isrc, track.title, track.artist, video_id, duration_seconds=duration)
                        db.commit()
                else:
                    duration = resolve_track_duration_only(db, track)
                    if duration is not None:
                        track.duration_seconds = duration
                        cache.store(
                            db, track.isrc, track.title, track.artist, track.youtube_video_id,
                            duration_seconds=duration, overwrite=True,
                        )
                        db.commit()
            except Exception:
                logger.exception("Matching: échec inattendu pour le morceau %s (playlist %s)", track.id, playlist_id)
                db.rollback()
    finally:
        db.close()
