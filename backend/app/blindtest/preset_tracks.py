"""Lecture en direct d'une playlist préparée du blind test classique.

Les listes `RDCLAK...` de YouTube Music évoluent : chaque sélection relit la
liste du moment. Les noms relus dans `presets/<slug>.json` restent prioritaires
pour les vidéos qu'il contient ; une vidéo nouvelle passe par `build_reference`.
"""
import os
from typing import Dict, List, Optional

import httpx

from app.blindtest.classic import build_reference
from app.blindtest.errors import ProviderConfigError
from app.blindtest.matching import _YOUTUBE_VIDEOS_URL, _parse_iso8601_duration
from app.blindtest.presets import Preset, load_tracks
from app.blindtest.providers import youtube
from app.blindtest.song_identity import SongTrack, group_songs

VIDEOS_PER_REQUEST = 50
PLAYABLE_PRIVACY = {"public", "unlisted"}
AUDIENCE_COUNTRY = "FR"


def playable_duration(video: dict) -> Optional[int]:
    """Durée en secondes si la vidéo est jouable dans le lecteur caché, sinon
    `None`. Un `videos.list` sans durée exploitable (live, "P0D") est écarté."""
    status = video.get("status") or {}
    details = video.get("contentDetails") or {}
    if not status.get("embeddable") or status.get("privacyStatus") not in PLAYABLE_PRIVACY:
        return None
    region = details.get("regionRestriction") or {}
    if AUDIENCE_COUNTRY in region.get("blocked", []):
        return None
    if "allowed" in region and AUDIENCE_COUNTRY not in region["allowed"]:
        return None
    return _parse_iso8601_duration(details.get("duration") or "") or None


def fetch_videos(video_ids: List[str], api_key: str) -> Dict[str, dict]:
    videos: Dict[str, dict] = {}
    with httpx.Client(timeout=10.0) as client:
        for start in range(0, len(video_ids), VIDEOS_PER_REQUEST):
            resp = client.get(
                _YOUTUBE_VIDEOS_URL,
                params={
                    "part": "contentDetails,status",
                    "id": ",".join(video_ids[start:start + VIDEOS_PER_REQUEST]),
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            videos.update({item["id"]: item for item in resp.json().get("items", [])})
    return videos


def live_tracks(preset: Preset) -> List[dict]:
    """Morceaux jouables de la liste du moment, avec leurs noms relus quand ils
    existent, une seule fois par chanson : leur nombre est celui d'une partie.
    Lève les erreurs du provider : à l'appelant de se replier."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ProviderConfigError("youtube", "YOUTUBE_API_KEY")

    extracted = youtube.fetch_tracks(f"https://www.youtube.com/playlist?list={preset.playlist_id}")
    videos = fetch_videos([item.youtube_video_id for item in extracted], api_key)
    reviewed = {track["youtube_video_id"]: track for track in load_tracks(preset)} if preset.path.exists() else {}

    tracks = []
    for item in extracted:
        duration = playable_duration(videos.get(item.youtube_video_id, {}))
        if duration is None:
            continue
        known = reviewed.get(item.youtube_video_id)
        reference = None if known else build_reference(item.title, item.artist)
        tracks.append({
            "youtube_video_id": item.youtube_video_id,
            "title": known["title"] if known else reference.title,
            "artist": known["artist"] if known else reference.artist,
            "duration_seconds": duration,
            "raw_title": item.title,
            "raw_channel": item.artist,
        })
    return _one_per_song(_answerable(tracks))


def _answerable(tracks: List[dict]) -> List[dict]:
    references = (build_reference(track["title"], track["artist"], structured=True) for track in tracks)
    return [track for track, reference in zip(tracks, references) if reference.titles and reference.artists]


def _one_per_song(tracks: List[dict]) -> List[dict]:
    songs = group_songs(
        SongTrack(
            id=index,
            title=track["title"],
            artist=track["artist"],
            isrc=None,
            youtube_video_id=track["youtube_video_id"],
            duration_seconds=track["duration_seconds"],
            structured=True,
        )
        for index, track in enumerate(tracks)
    )
    first_of_song = {}
    for index in range(len(tracks)):
        first_of_song.setdefault(songs[index], index)
    return [tracks[index] for index in sorted(first_of_song.values())]
