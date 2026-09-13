"""Schémas Pydantic du module blindtest — Story 1.1/1.4."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.blindtest.providers import youtube


class PlaylistImportRequest(BaseModel):
    url: str
    # Story 2.2 : scoping optionnel à une partie. Toujours ensemble présents
    # ou ensemble absents (validé dans `main_blindtest.import_playlist`, pas
    # ici — la validation dépend de l'état DB/WS, pas juste de la forme).
    game_code: Optional[str] = None
    pseudo: Optional[str] = None


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    isrc: Optional[str] = None
    youtube_video_id: Optional[str] = None
    duration_seconds: Optional[int] = None


class PlaylistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    source_url: str
    tracks: List[TrackResponse]
    game_id: Optional[int] = None
    owner_pseudo: Optional[str] = None

    @computed_field
    @property
    def not_found_count(self) -> int:
        """Nombre de morceaux non résolus (Story 1.4) : `youtube_video_id`
        encore `None` au moment de la réponse. Valeur "live" — peut encore
        baisser tant que le matching en arrière-plan (Story 1.2) tourne."""
        return sum(1 for track in self.tracks if track.youtube_video_id is None)

    @computed_field
    @property
    def truncated(self) -> bool:
        """True si l'import a probablement été tronqué par le garde-fou de
        pagination YouTube (`providers.youtube.MAX_TRACKS`) — playlist trop
        grosse (ex. "Titres likés") pour être importée en entier. Approximé
        par le nombre de morceaux atteignant exactement cette limite : une
        playlist coïncidant pile avec `MAX_TRACKS` sans être réellement
        tronquée donnerait un faux positif, jugé acceptable (rarissime) pour
        éviter de faire remonter ce détail depuis `fetch_tracks` jusqu'ici.
        Toujours `False` pour Deezer, qui n'a pas cette limite."""
        return self.provider == "youtube" and len(self.tracks) >= youtube.MAX_TRACKS


# === Admin — réconciliation manuelle des morceaux non trouvés ===

class UnresolvedTrackResponse(BaseModel):
    """Un morceau sans `youtube_video_id`, avec assez de contexte pour
    qu'un admin le retrouve manuellement (titre/artiste/isrc, lien du
    morceau lui-même, et la playlist d'origine)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    isrc: Optional[str] = None
    source_url: Optional[str] = None
    playlist_id: int
    playlist_provider: str


class ResolveTrackRequest(BaseModel):
    """Corps de `PUT /admin/blindtest/tracks/{track_id}` — lien YouTube
    complet (`watch?v=`/`youtu.be/`) ou videoId nu (11 caractères)."""
    youtube_url: str


# === Lobby / connexion à une partie (Story 2.1) ===

class GameCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
