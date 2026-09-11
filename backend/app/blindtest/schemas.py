"""Schémas Pydantic du module blindtest — Story 1.1."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PlaylistImportRequest(BaseModel):
    url: str


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    isrc: Optional[str] = None
    youtube_video_id: Optional[str] = None


class PlaylistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    source_url: str
    tracks: List[TrackResponse]
