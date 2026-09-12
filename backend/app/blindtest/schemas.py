"""Schémas Pydantic du module blindtest — Story 1.1/1.4."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, computed_field


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

    @computed_field
    @property
    def not_found_count(self) -> int:
        """Nombre de morceaux non résolus (Story 1.4) : `youtube_video_id`
        encore `None` au moment de la réponse. Valeur "live" — peut encore
        baisser tant que le matching en arrière-plan (Story 1.2) tourne."""
        return sum(1 for track in self.tracks if track.youtube_video_id is None)
